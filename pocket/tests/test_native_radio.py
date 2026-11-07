"""Exercise native packet framing and the real descriptor-driven RNode handshake."""
import os
from pathlib import Path
import pty
import select
import sys
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum'))
from native_radio import Frames,RNode,TCPPackets,SerialPackets,KISSPackets,hdlc
from rnode_protocol import KISS

class NativeRadioTest(unittest.TestCase):
    def test_split_frames_and_bounded_input(self):
        payload=b'\x00\xc0\xdb\x7d\x7e'
        parser=Frames(0x7e,0x7d,0x20,limit=10)
        encoded=hdlc(payload)
        self.assertEqual([f for b in encoded for f in parser.feed(bytes([b]))],[payload])
        with self.assertRaises(ValueError):list(parser.feed(b'\x7e'+b'x'*11))

    def exercise(self,mismatch=False):
        master,slave=pty.openpty();received=[];events=[];sent=[];stop=threading.Event()
        def frame(command,data):return bytes([KISS.FEND,command])+KISS.escape(data)+bytes([KISS.FEND])
        def emulate():
            parser=Frames(KISS.FEND,KISS.FESC)
            while not stop.is_set():
                try:
                    if not select.select([master],[],[],.1)[0]:continue
                    raw=os.read(master,4096)
                except (OSError,TypeError):return
                for packet in parser.feed(raw):
                    number,data=packet[0],packet[1:]
                    if number==8:reply=frame(8,b'F')
                    elif number==0x50:reply=frame(number,b'\x01\x52')
                    elif number==0x48:reply=frame(number,b'\x80')
                    elif number in range(1,7):reply=frame(number,b'\x00' if mismatch and number==6 else data)
                    elif number==0:
                        sent.append(data);reply=frame(0,data)+frame(15,b'\x01')
                    else:continue
                    os.write(master,reply)
        worker=threading.Thread(target=emulate);worker.start()
        radio=None
        try:
            radio=RNode(dict(port=os.ttyname(slave),frequency=915000000,bandwidth=125000,txpower=5,spreadingfactor=7,codingrate=5,flow_control='True'),received.append,events.append)
            deadline=time.monotonic()+4
            while time.monotonic()<deadline and not any(e['phase'] in ('ready','failed') for e in events):time.sleep(.01)
            self.assertEqual(events[-1]['phase'],'failed' if mismatch else 'ready',events)
            if not mismatch:
                payloads=[b'\x01\xc0\xdb',b'\x02\x7e\x7d']
                for payload in payloads:self.assertTrue(radio.send(payload))
                while time.monotonic()<deadline and len(received)<2:time.sleep(.01)
                self.assertEqual(received,payloads);self.assertEqual(sent,payloads)
                os.close(master);master=None
                while time.monotonic()<deadline and events[-1]['phase']!='failed':time.sleep(.01)
                self.assertEqual(events[-1]['phase'],'failed')
        finally:
            if radio:radio.close()
            stop.set();worker.join(2)
            if master is not None:os.close(master)
            os.close(slave)
    def test_handshake_flow_control_and_disconnect(self):self.exercise()
    def test_mismatched_readback_never_ready(self):self.exercise(True)

class SerialPeerTests(unittest.TestCase):
    def test_bidirectional_framing_and_idle_close(self):
        master,slave=pty.openpty();received=[];events=[]
        self.addCleanup(os.close,slave)
        radio=SerialPackets(dict(port=os.ttyname(slave),speed=9600),received.append,events.append)
        self.addCleanup(radio.close)
        try:
            payload=b'hello\x7e\x7d\x00'
            for value in hdlc(payload):os.write(master,bytes([value]))
            deadline=time.monotonic()+3
            while not received and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(received,[payload])
            with self.assertRaises(ValueError):radio.send(b'x'*565)
            self.assertTrue(radio.send(payload))
            parser=Frames(0x7e,0x7d,0x20);frames=[]
            while not frames and time.monotonic()<deadline:
                if select.select([master],[],[],.1)[0]:frames.extend(parser.feed(os.read(master,4096)))
            self.assertEqual(frames,[payload])
            before=time.monotonic();radio.close()
            self.assertFalse(radio.thread.is_alive())
            self.assertLess(time.monotonic()-before,1)
            self.assertFalse(radio.send(b'closed'))
        finally:os.close(master)

    def test_invalid_configuration_fails_before_open(self):
        for options in (dict(speed=12345),dict(parity='even'),dict(databits=7),dict(stopbits=2)):
            with self.assertRaises(ValueError):SerialPackets(dict(port='/nonexistent',**options),lambda x:None,lambda x:None)


class KISSPeerTests(unittest.TestCase):
    def test_configuration_packets_filtering_and_shutdown(self):
        master,slave=pty.openpty();received=[];events=[]
        radio=None
        try:
            radio=KISSPackets(dict(port=os.ttyname(slave),preamble=150,txtail=10,persistence=200,slottime=20),received.append,events.append)
            parser=Frames(KISS.FEND,KISS.FESC);frames=[];until=time.monotonic()+3
            while len(frames)<4 and time.monotonic()<until:
                if select.select([master],[],[],.1)[0]:frames.extend(parser.feed(os.read(master,4096)))
            self.assertEqual(frames,[bytes([1,15]),bytes([4,1]),bytes([2,200]),bytes([3,2])])
            while not radio.online and time.monotonic()<until:time.sleep(.01)
            self.assertTrue(radio.online)
            payload=b'\xc0\xdb binary'
            def frame(command,data):return bytes([KISS.FEND,command])+KISS.escape(data)+bytes([KISS.FEND])
            os.write(master,frame(1,b'ignore')+frame(16,b'other port')+frame(0,payload))
            while not received and time.monotonic()<until:time.sleep(.01)
            self.assertEqual(received,[payload])
            self.assertTrue(radio.send(payload))
            frames=[]
            while not frames and time.monotonic()<until:
                if select.select([master],[],[],.1)[0]:frames.extend(parser.feed(os.read(master,4096)))
            self.assertEqual(frames,[b'\0'+payload])
            with self.assertRaises(ValueError):radio.send(b'x'*565)
            radio.close();self.assertFalse(radio.thread.is_alive())
            self.assertFalse(radio.send(b'closed'))
        finally:
            if radio:radio.close()
            os.close(master);os.close(slave)

    def test_unsupported_options_fail_before_open(self):
        for options in (dict(flow_control='True'),dict(id_callsign='TEST'),dict(preamble=-1),dict(persistence=256)):
            with self.assertRaises(ValueError):KISSPackets(dict(port='/nonexistent',**options),lambda x:None,lambda x:None)


class DirectPeerTests(unittest.TestCase):
    def wait(self,predicate,seconds=5):
        until=time.monotonic()+seconds
        while not predicate():
            if time.monotonic()>until:self.fail('Direct peer event did not arrive')
            time.sleep(.01)
    def test_listener_client_bidirectional_reconnect_and_close(self):
        import socket
        probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
        left=[];right=[];events=[]
        server=TCPPackets(dict(type='TCPServerInterface',listen_ip='127.0.0.1',listen_port=port),left.append,events.append)
        self.addCleanup(server.close)
        client=TCPPackets(dict(type='TCPClientInterface',target_host='127.0.0.1',target_port=port),right.append,events.append)
        self.addCleanup(client.close)
        self.wait(lambda:server.online and client.online)
        self.assertTrue(client.send(b'hello \x7e\x7d'));self.assertTrue(server.send(b'reply'))
        self.wait(lambda:len(left)==1 and len(right)==1)
        self.assertEqual(left,[b'hello \x7e\x7d']);self.assertEqual(right,[b'reply'])
        server.close();self.wait(lambda:not client.online)
        self.assertFalse(client.send(b'offline must not replay'))
        replacement=TCPPackets(dict(type='TCPServerInterface',listen_ip='127.0.0.1',listen_port=port),left.append,events.append)
        self.addCleanup(replacement.close)
        self.wait(lambda:replacement.online and client.online)
        self.assertTrue(client.send(b'after reconnect'))
        self.wait(lambda:len(left)==2)
        self.assertEqual(left[-1],b'after reconnect')
        before=time.monotonic();client.close();replacement.close()
        self.assertLess(time.monotonic()-before,1)
    def test_explicit_addresses_and_packet_bounds(self):
        for config in (dict(target_host='example.com',target_port=4242),dict(target_host='127.0.0.1',target_port=0)):
            with self.assertRaises(ValueError):TCPPackets(config,lambda x:None,lambda x:None)
        import socket
        probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
        server=TCPPackets(dict(type='TCPServerInterface',listen_ip='127.0.0.1',listen_port=port),lambda x:None,lambda x:None)
        self.addCleanup(server.close)
        client=TCPPackets(dict(target_host='127.0.0.1',target_port=port),lambda x:None,lambda x:None)
        self.addCleanup(client.close);self.wait(lambda:client.online and server.online)
        with self.assertRaises(ValueError):client.send(b'x'*(TCPPackets.MAX_PACKET+1))

if __name__=='__main__':unittest.main()
