"""RNode compatibility framing and reply-driven radio lifecycle, no RF."""
import importlib.util
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'shell'))
sys.path.insert(0,str(ROOT/'shell/vendor/apps/domains/reticulum'))
sys.path.insert(0,str(ROOT/'shell/vendor/apps/domains/meshcore'))
from rnode_adapter import Adapter,KissDecoder,kiss
from hub_transport import Frame
class FakeLink:
    def __init__(self):self.sent=[]
    def send(self,service,op,data=b''):
        self.sent.append((service,op,data));return len(self.sent)
class Tests(unittest.TestCase):
    def test_numeric_linux_pty_endpoint_only(self):
        spec=importlib.util.spec_from_file_location('htit_endpoint_test',ROOT/'shell/vendor/apps/domains/reticulum/endpoints.py')
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
        self.assertEqual(module.Endpoint('nokia','htit','usb','/dev/pts/123').port,'/dev/pts/123')
        endpoint=module.Endpoint(station='nokia',radio='htit',connection='usb',port='/dev/pts/123')
        with self.assertRaises(AttributeError):endpoint.port='/tmp/unsafe'
        settings=module.RadioSettings(912345000,500000,2,7,5)
        with self.assertRaises(AttributeError):settings.txpower=37
        for values in ((912345000,500000,True,7,5),(912345000,12345,2,7,5),(912345000,500000,2,6,5)):
            with self.assertRaises(ValueError):module.RadioSettings(*values)
        for bad in ('/dev/pts/foo','/dev/pts/1/2','/dev/pts/../1','/tmp/radio','/dev/pts/-1'):
            with self.assertRaises(ValueError):module.Endpoint('nokia','htit','usb',bad)

    def test_escape_boundaries_and_recover_after_oversize(self):
        for n in (1,254,255,500,508):
            data=bytes(i%256 for i in range(n));wire=kiss(0,data);decoder=KissDecoder();got=[]
            for byte in wire:got+=decoder.feed(bytes([byte]))
            self.assertEqual(got,[(0,data)])
        decoder=KissDecoder();self.assertEqual(decoder.feed(kiss(0,b'x'*509)),[])
        self.assertEqual(decoder.feed(kiss(8,b'\x73')),[(8,b'\x73')])
        self.assertEqual(decoder.feed(b'\xc0\x00\xdb\x01\xc0'),[])
    def make(self):
        out=[];link=FakeLink();return Adapter(link,SimpleNamespace(queue=out.append)),link,out
    def test_radio_not_ready_before_configuration_and_enable_ack(self):
        a,link,out=self.make()
        for cmd,val in ((1,912345000),(2,500000),(3,2),(4,7),(5,5)):
            a.command(cmd,val.to_bytes(4 if cmd<3 else 1,'big'))
        self.assertEqual(link.sent,[]);self.assertEqual(out,[])
        a.command(6,b'\1');self.assertFalse(a.online)
        self.assertEqual(link.sent[-1],(3,1,b''))
        a.frame(Frame(3,0x81,1,b'\0'));self.assertFalse(a.online)
        a.frame(Frame(3,0x82,2,b'\0'));self.assertFalse(a.online)
        self.assertEqual(link.sent[-1],(3,3,b'\1'))
        a.frame(Frame(3,0x83,3,b'\0'));self.assertTrue(a.online)
        self.assertIn(kiss(6,b'\1'),out)
        a.command(0,b'payload');a.tick();self.assertTrue(a.tx)
        self.assertEqual(link.sent[-1],(3,4,b'payload'))
        a.tick();self.assertEqual(len(link.sent),4)
        a.frame(Frame(3,0x84,4,b'\0'));self.assertFalse(a.tx)
        self.assertEqual(out[-1],kiss(0x0f,b'\1'))
    def test_rejected_config_never_enables_and_tx_failure_never_replays(self):
        a,link,out=self.make();a.values={1:912345000,2:500000,3:0,4:7,5:5}
        a.command(6,b'\1');a.frame(Frame(3,0x81,1,b'\0'));a.frame(Frame(3,0x82,2,b'\1'))
        self.assertFalse(a.online);self.assertEqual(len(link.sent),2)
        a.online=True;a.command(0,b'first');a.command(0,b'second');a.tick()
        a.frame(Frame(3,0x84,3,b'\4'));a.tick()
        self.assertFalse(a.tx);self.assertEqual(len(link.sent),3)
    def test_idle_adapter_does_not_claim_or_transmit(self):
        a,link,out=self.make();a.last_renew=0;a.tick()
        a.command(8,b'\x73');a.command(6,b'\0');a.command(0x0a,b'\xff')
        self.assertEqual(link.sent,[])

    def test_off_invalidates_inflight_configuration_and_tx(self):
        for phase in ('claim','configure','tx'):
            a,link,out=self.make();a.values={1:912345000,2:500000,3:2,4:7,5:5}
            a.command(6,b'\1')
            if phase!='claim':a.frame(Frame(3,0x81,1,b'\0'))
            if phase=='tx':
                a.frame(Frame(3,0x82,2,b'\0'));a.frame(Frame(3,0x83,3,b'\0'))
                a.command(0,b'packet');a.tick()
            old=list(a.pending.items());a.command(6,b'\0');release=len(link.sent)
            a.command(0x0a,b'\xff');self.assertEqual(len(link.sent),release)
            for ident,(op,_,_) in old:a.frame(Frame(3,op|128,ident,b'\0'))
            a.frame(Frame(3,0x86,release,b'\0'));a.last_renew=0;a.tick()
            self.assertFalse(a.online);self.assertFalse(a.claimed)
            self.assertEqual(a.pending,{});self.assertEqual(len(link.sent),release)

    def test_receive_payload_and_signal_metadata(self):
        a,link,out=self.make();a.frame(Frame(3,0x90,0,b'\x9c\xff\xfcdata'))
        self.assertEqual(out,[kiss(0x23,bytes([57])),kiss(0x24,b'\xfc'),kiss(0,b'data')])
    def test_unknown_commands_and_nonzero_airtime_limits_are_rejected(self):
        a,link,out=self.make();a.command(0x55,b'\xff');a.command(0x0b,b'\0\1')
        self.assertEqual(link.sent,[]);self.assertEqual(out,[kiss(0x90,b'\1')]*2)
if __name__=='__main__':unittest.main()
