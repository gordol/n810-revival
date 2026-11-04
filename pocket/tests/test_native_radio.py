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
from native_radio import Frames,RNode,hdlc
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

if __name__=='__main__':unittest.main()
