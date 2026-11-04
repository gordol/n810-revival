#!/usr/bin/env python3
"""Feed transport tests using local sockets only. Never opens Bluetooth."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('bridge', Path(__file__).with_name('n810-kiss-bridge.py'))
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)


class FramingTests(unittest.TestCase):
    def test_fragmented_binary_frames(self):
        payload = b'\0' + bytes(range(256))
        parser = b.Frames(); actual = []
        for byte in b.encode(payload): actual += parser.feed(bytes([byte]))
        self.assertEqual(actual, [payload])
        self.assertEqual(parser.feed(b.encode(b'\x01\x20')+b.encode(payload)), [b'\x01\x20', payload])

    def test_malformed_and_oversize(self):
        with self.assertRaises(ValueError): b.Frames().feed(b'\xc0\0\xdb\x01')
        with self.assertRaises(ValueError): b.Frames().feed(b'\xc0' + b'x'*(b.MAX_FRAME+1))


class BridgeTests(unittest.TestCase):
    def test_vendor_reassembly_reaches_raw_subscriber_without_transmitting(self):
        fixture=json.loads(Path(__file__).with_name('fixtures').joinpath('walk-mixed-vendor.json').read_text())
        frame=bytes.fromhex(fixture['complete_kiss_frame']);mixed=bytes.fromhex(fixture['captured_mixed_frame'])
        parts=[frame[1:][i:i+53] for i in range(0,len(frame)-1,53)]
        last=b'\xff\1\0'+bytes([len(parts[-1])+2])+b'\0\2\0\11\2\x82'+parts[-1]
        client=self.connect(self.rx);captured=[]
        self.bridge.capture=lambda direction,frame,**metadata:captured.append((direction,frame,metadata))
        self.peer.sendall(b'\xc0'+mixed+last);self.receive(client,b.encode(frame))
        self.assertEqual(len(captured),1)
        self.assertEqual(captured[0][2]['origin'],'vendor_reassembled')
        self.assertEqual(len(captured[0][2]['wire_frames']),3)
        self.peer.sendall(b.encode(frame));self.tick()
        with self.assertRaises(socket.timeout):client.recv(1)
        self.no_tx()

    def test_telemetry_shares_queue_without_kiss_tx_capture(self):
        captured=[];self.bridge.capture=lambda *row:captured.append(row)
        frame=b'\xff\1\0\0\0\2\0\x14'
        self.bridge.telemetry_request(frame);self.bridge.poll(.01)
        self.assertEqual(self.peer.recv(100),frame)
        self.assertEqual(captured,[])
        with self.assertRaises(ValueError):self.bridge.telemetry_request(b'\xff\1\0\0\0\2\0\x0b')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kiss-test-', dir='/tmp')
        self.raw = self.temp.name+'/tx.sock'; self.rx = self.temp.name+'/rx.sock'
        self.radio, self.peer = socket.socketpair(); self.peer.setblocking(False)
        self.status = []
        self.bridge = b.Bridge(self.radio, self.raw, self.rx, self.status.append)
        self.connections = []

    def tearDown(self):
        self.bridge.close(); self.radio.close(); self.peer.close()
        for c in self.connections: c.close()
        self.temp.cleanup()

    def tick(self, count=4):
        for _ in range(count): self.bridge.poll(.005)

    def connect(self, path):
        c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); c.connect(path)
        c.settimeout(.2); self.connections.append(c); self.tick(); return c

    def receive(self, c, expected):
        self.tick(); data=b''
        while len(data)<len(expected): data += c.recv(65536)
        self.assertEqual(data, expected)

    def no_tx(self):
        self.tick()
        with self.assertRaises(BlockingIOError): self.peer.recv(8192)

    def test_multiple_monitors_no_replay_no_echo(self):
        writer = self.connect(self.raw); first=self.connect(self.rx); second=self.connect(self.rx)
        frame = b.encode(b'\0'+bytes(range(256)))
        for chunk in (frame[:5], frame[5:]): self.peer.sendall(chunk); self.tick()
        for client in (writer,first,second): self.receive(client, frame)
        late=self.connect(self.rx)
        with self.assertRaises(socket.timeout): late.recv(1)
        # A monitor cannot transmit, even a syntactically valid KISS frame.
        first.sendall(frame); self.tick(); self.assertEqual(first.recv(1),b''); self.no_tx()

    def test_exclusive_writer_and_handover(self):
        first=self.connect(self.raw); second=self.connect(self.raw)
        self.assertEqual(second.recv(1),b'')
        frame=b.encode(b'\0binary\xc0\xdb\x00\xff')
        first.sendall(frame[:4]); self.no_tx()
        first.sendall(frame[4:] + b.encode(b'\x01\x20')); self.tick()
        self.receive(self.peer, frame+b.encode(b'\x01\x20'))
        first.close(); self.tick()
        third=self.connect(self.raw); third.sendall(frame); self.receive(self.peer,frame)

    def test_invalid_batch_and_partial_client_disconnect(self):
        writer=self.connect(self.raw)
        writer.sendall(b.encode(b'\0valid')+b.encode(b'\x0f'))
        self.tick(); self.assertEqual(writer.recv(1),b''); self.no_tx()
        writer=self.connect(self.raw);writer.sendall(b'\xc0\0unfinished');self.tick()
        writer.close();self.tick();self.no_tx()
        writer=self.connect(self.raw);writer.sendall(b.encode(b'\x10badport'));self.tick();self.no_tx()

    def test_slow_monitor_does_not_block_others(self):
        slow=self.connect(self.rx);fast=self.connect(self.rx)
        # Force the bound without depending on platform-specific socket buffer sizes.
        accepted=next(iter(self.bridge.clients))
        self.bridge.clients[accepted]['output'].extend(b'x'*b.LIMIT)
        self.bridge.broadcast(b.encode(b'\0hello'))
        self.assertNotIn(accepted,self.bridge.clients)
        self.receive(fast,b.encode(b'\0hello'))

    def test_shutdown_discards_queue_and_removes_sockets(self):
        writer=self.connect(self.raw)
        writer.sendall(b.encode(b'\0never-send'))
        self.bridge.poll(.1) # Reads request; no radio WRITE readiness in this snapshot.
        self.assertTrue(self.bridge.tx)
        self.bridge.close()
        self.assertFalse(os.path.exists(self.raw));self.assertFalse(os.path.exists(self.rx))
        self.assertEqual(writer.recv(1),b'');self.assertFalse(self.bridge.tx)
        with self.assertRaises(BlockingIOError):self.peer.recv(8192)
        # Reopen after loss; previous clients/queues/history do not carry over.
        self.bridge=b.Bridge(self.radio,self.raw,self.rx,self.status.append)
        self.no_tx()
        self.assertEqual(os.stat(self.raw).st_mode & 0o777,0o600)

    def test_writer_disconnect_finishes_only_started_frame(self):
        class PartialSocket:
            def fileno(inner): return self.radio.fileno()
            def setblocking(inner, value): self.radio.setblocking(value)
            def recv(inner, size): return self.radio.recv(size)
            def send(inner, data): return self.radio.send(data[:2])
        self.bridge.close()
        self.bridge=b.Bridge(PartialSocket(),self.raw,self.rx,self.status.append)
        writer=self.connect(self.raw)
        first=b.encode(b'\0first-frame-long-enough')
        second=b.encode(b'\0discard-this-one')
        writer.sendall(first+second)
        self.bridge.poll(.1) # queue
        self.bridge.poll(.1) # partial radio write
        self.assertGreater(self.bridge.tx[0][1],0)
        writer.close()
        self.tick(40)
        self.receive(self.peer,first)
        self.assertFalse(self.bridge.tx)
        self.no_tx()

    def test_capture_distinguishes_rx_and_completed_tx(self):
        events=[];self.bridge.capture=lambda direction,frame:events.append((direction,frame))
        writer=self.connect(self.raw);frame=b'\0outgoing'
        writer.sendall(b.encode(frame)[:-1]);self.tick()
        self.assertFalse(events)
        writer.sendall(b'\xc0');self.tick()
        self.assertEqual(events,[('host_to_radio_written',frame)])
        self.peer.sendall(b.encode(b'\0incoming'));self.tick()
        self.assertEqual(events[-1],('radio_to_host',b'\0incoming'))

    def test_radio_eof_is_reported(self):
        self.peer.close()
        with self.assertRaises(ConnectionError):self.bridge.poll(.1)

    def test_non_socket_path_is_preserved(self):
        p=self.temp.name+'/not-a-socket';Path(p).write_text('keep')
        with self.assertRaises(RuntimeError):b.listen(p)
        self.assertEqual(Path(p).read_text(),'keep')


if __name__ == '__main__': unittest.main(verbosity=2)
