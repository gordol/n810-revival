"""Run the host adapter with the real MeshCore client through OS serial PTYs.
The hub/BLE side is an emulator; this is not a hardware coexistence test.
"""
import asyncio
import importlib.util
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import threading
import time
import tty
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'host'))
from hub import Frame, Decoder

try:
    from meshcore import MeshCore, EventType
except ImportError:
    MeshCore = None


@unittest.skipIf(MeshCore is None or not os.environ.get('POCKET_SOURCE'), 'set POCKET_SOURCE and install its MeshCore requirements for the optional official client test')
class AdapterTest(unittest.TestCase):
    def test_official_client_and_peer_tunnel(self):
        master, slave = pty.openpty()
        tty.setraw(slave)
        stop = threading.Event()
        errors, commands, peer_packets = [], [], []
        def emulate():
            decoder = Decoder()
            def send(f):
                data = f.encode()
                for n in range(0, len(data), 7):
                    os.write(master, data[n:n+7])
            try:
                while not stop.is_set():
                    if not select.select([master], [], [], .05)[0]:
                        continue
                    for frame in decoder.feed(os.read(master, 4096)):
                        if frame.service == 0:
                            data = b'\x01\x00\x07' if frame.op == 1 else b''
                            send(Frame(0, frame.op | 0x80, frame.id, b'\x00'+data))
                            if frame.op == 4:
                                send(Frame(0, 0x93, data=b'MeshCore ready'))
                        elif frame.service == 1:
                            commands.append(frame.data)
                            send(Frame(1, 0x81, frame.id, b'\x00'))
                            op = frame.data[0]
                            if op == 1:
                                payload = b'\x05\x01\x0a\x14'+b'b'*32+b'\0'*12+struct.pack('<II',915000,125000)+b'\x07\x05Gordo fixture'
                            elif op == 22:
                                payload = b'\x0d\x03\x01\x01'+b'\0'*(4+12+40+20)
                            elif op == 4:
                                send(Frame(1, 0x90, data=b'\x02'+b'\0'*4))
                                payload = b'\x04'+b'\0'*4
                            else:
                                raise AssertionError('unexpected radio command '+str(op))
                            send(Frame(1, 0x90, data=payload))
                        elif frame.service == 2:
                            peer_packets.append(frame.data)
                            send(Frame(2, 0x81, frame.id, b'\x00'))
                            send(Frame(2, 0x90, data=frame.data))
            except Exception as exc:
                errors.append(repr(exc))
        thread = threading.Thread(target=emulate, daemon=True)
        thread.start()
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve().parents[1]/'host/hub.py'),
                                    '--port', os.ttyname(slave), 'bridge', '--ble', '01:02:03:04:05:06', '--peer', '1'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            ports = {}
            deadline = time.monotonic()+10
            # Unbuffered fd reading avoids TextIO buffering/select races.
            text = b''
            while len(ports)<2 and time.monotonic()<deadline:
                if process.poll() is not None:
                    self.fail(process.stderr.read())
                if select.select([process.stdout.fileno()], [], [], .1)[0]:
                    text += os.read(process.stdout.fileno(),4096)
                    while b'\n' in text:
                        line, text = text.split(b'\n',1)
                        if b'_PORT=' in line:
                            key,value=line.decode().split('=',1);ports[key]=value
            self.assertEqual(len(ports),2)
            async def exercise():
                spec = importlib.util.spec_from_file_location('serial_client', Path(os.environ['POCKET_SOURCE'])/'shell/vendor/apps/domains/meshcore/serial_client.py')
                adapter = importlib.util.module_from_spec(spec); spec.loader.exec_module(adapter)
                client = await adapter.create_serial_client(ports['MESHCORE_PORT'],115200,auto_reconnect=False,default_timeout=2)
                self.assertIsNotNone(client)
                try:
                    info = await client.commands.send_device_query()
                    self.assertEqual(info.type,EventType.DEVICE_INFO)
                    contacts = await client.commands.get_contacts()
                    self.assertEqual(contacts.type,EventType.CONTACTS)
                finally:
                    await client.disconnect()
            asyncio.run(exercise())
            fd = os.open(ports['PEER_PORT'], os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
            try:
                payload=b'laptop to N810\0~}\xff'
                os.write(fd,payload)
                self.assertTrue(select.select([fd],[],[],3)[0])
                self.assertEqual(os.read(fd,1024),payload)
            finally:
                os.close(fd)
            self.assertEqual([c[0] for c in commands], [1,22,4])
            self.assertEqual(peer_packets,[b'\x01'+payload])
            self.assertFalse(errors,errors)
        finally:
            process.send_signal(signal.SIGINT)
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            process.stdout.close();process.stderr.close()
            stop.set();thread.join(2);os.close(master);os.close(slave)


if __name__ == '__main__':
    unittest.main()
