"""Bounds and peer isolation for the read-only DMA snapshot decoder; no hardware."""
import ctypes as C
from pathlib import Path
import random
import subprocess
import tempfile
import unittest
from test_ccmp import Epoch,epoch

HERE=Path(__file__).resolve().parent
OWN=bytes.fromhex('020000000001');PEER=bytes.fromhex('0002eec0ffee');NET=bytes.fromhex('024e38313002')
FRAME=b'\x08\x40\0\0'+OWN+PEER+NET+b'\0\0'+bytes(range(80))
class Snapshot(C.Structure):
    _fields_=[('flags',C.c_uint32),('dma',C.c_uint16),('sig',C.c_uint16),
              ('length',C.c_uint16),('state',C.c_uint8),('filter',C.c_uint8),('frame',C.c_uint8*260)]
def packet(frame=FRAME,state=0,filter=1):
    data=bytearray(1600);data[3]=filter<<4;data[24:26]=len(frame).to_bytes(2,'little');data[27]=state
    data[28:28+len(frame)]=frame;return bytes(data)

class ObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='htit-dma-decode-')
        source=Path(cls.temp.name)/'test.cpp';lib=Path(cls.temp.name)/'test.dylib'
        source.write_text('#include "hw_ccmp.h"\nextern "C" bool decode(const uint8_t* p,size_t n,uint32_t f,const uint8_t* a,const uint8_t* b,const uint8_t* c,ProbeRawRx* o){return probe_dma_decode(p,n,f,a,b,c,o);}\nextern "C" int hwopen(CcmpEpoch* e,const ProbeRawRx* r,bool ready,uint8_t* o,size_t cap){return ccmp_open_hardware(e,*r,ready,o,cap);}\n')
        subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-O2','-shared','-fPIC','-I'+str(HERE),str(source),'-o',str(lib)],check=True)
        cls.lib=C.CDLL(str(lib));cls.lib.decode.argtypes=[C.c_char_p,C.c_size_t,C.c_uint32,C.c_char_p,C.c_char_p,C.c_char_p,C.POINTER(Snapshot)]
        cls.lib.decode.restype=C.c_bool
        cls.lib.hwopen.argtypes=[C.POINTER(Epoch),C.POINTER(Snapshot),C.c_bool,C.c_void_p,C.c_size_t]
        cls.lib.hwopen.restype=C.c_int
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def decode(self,data=None,length=132,own=OWN,peer=PEER,net=NET):
        out=Snapshot();ok=self.lib.decode(packet() if data is None else data,length,0x40084000,own,peer,net,C.byref(out));return ok,out
    def test_exact_bytes_metadata_and_dma_length(self):
        for state in (0,64,65,98,245,255):
            for filter in range(4):
                ok,out=self.decode(packet(state=state,filter=filter));self.assertTrue(ok)
                self.assertEqual((out.dma,out.sig,out.length,out.state,out.filter),(132,104,104,state,filter))
                self.assertEqual(bytes(out.frame[:out.length]),FRAME)
    def test_address_bssid_and_subtype_filter(self):
        for offset in (0,4,10,16):
            changed=bytearray(FRAME);changed[offset]^=1
            self.assertFalse(self.decode(packet(bytes(changed)))[0])
        self.assertFalse(self.decode(own=PEER)[0]);self.assertFalse(self.decode(peer=OWN)[0])
    def test_truncated_dma_never_copies_beyond_available_bytes(self):
        for length in range(1610):
            ok,out=self.decode(length=length)
            if 52<=length<=1600:
                self.assertTrue(ok);self.assertEqual(out.length,min(104,length-28))
                self.assertEqual(bytes(out.frame[:out.length]),FRAME[:out.length])
            else:self.assertFalse(ok)
    def test_sig_length_limits_and_null_inputs(self):
        for sig in (0,23,261,4095):
            data=bytearray(packet());data[24:26]=sig.to_bytes(2,'little')
            self.assertFalse(self.decode(bytes(data))[0])
        out=Snapshot()
        self.assertFalse(self.lib.decode(None,132,0,OWN,PEER,NET,C.byref(out)))
        self.assertFalse(self.lib.decode(packet(),132,0,None,PEER,NET,C.byref(out)))
        self.assertFalse(self.lib.decode(packet(),132,0,OWN,PEER,NET,None))
    def test_random_metadata_is_bounded(self):
        rng=random.Random(473)
        for _ in range(5000):
            data=bytearray(packet());data[:28]=rng.randbytes(28)
            n=rng.randrange(1601);ok,out=self.decode(bytes(data),n)
            if ok:self.assertLessEqual(out.length,min(260,n-28))
    def hardware(self,pn=1):
        plain=bytes(range(64));iv=pn.to_bytes(6,'little')
        frame=FRAME[:24]+iv[:2]+b'\0\x20'+iv[2:]+plain
        data=bytearray(packet(frame));data[24:26]=(108).to_bytes(2,'little')
        ok,raw=self.decode(bytes(data),124);self.assertTrue(ok)
        return raw,plain
    def hwopen(self,e,raw,ready=True,capacity=64):
        out=C.create_string_buffer(b'X'*capacity,capacity)
        result=self.lib.hwopen(C.byref(e),C.byref(raw),ready,out,capacity)
        return result,out.raw
    def test_hardware_plaintext_requires_key_readiness_and_valid_metadata(self):
        raw,plain=self.hardware();e=epoch(header=FRAME[:24])
        self.assertEqual(self.hwopen(e,raw,False),(-1,bytes(64)));self.assertEqual(e.rx_pn,0)
        for field,values in [('state',[1,64,65,98,255]),('filter',[0,2,3]),('dma',[123,125]),('length',[24,95,261]),('sig',[44,112,65535])]:
            for value in values:
                changed=Snapshot.from_buffer_copy(raw);setattr(changed,field,value)
                self.assertEqual(self.hwopen(e,changed),(-1,bytes(64)));self.assertEqual(e.rx_pn,0)
        self.assertEqual(self.hwopen(e,raw),(64,plain));self.assertEqual(e.rx_pn,1)
    def test_hardware_replay_and_header_binding(self):
        raw,plain=self.hardware();e=epoch(header=FRAME[:24])
        for offset,mask in [(0,1),(1,0x40),(1,1),(4,1),(10,1),(16,1),(22,1),(26,1),(27,0x40)]:
            changed=Snapshot.from_buffer_copy(raw);changed.frame[offset]^=mask
            self.assertEqual(self.hwopen(e,changed),(-1,bytes(64)));self.assertEqual(e.rx_pn,0)
        zero,_=self.hardware(0);self.assertEqual(self.hwopen(e,zero),(-1,bytes(64)))
        self.assertEqual(self.hwopen(e,raw),(64,plain))
        self.assertEqual(self.hwopen(e,raw),(-1,bytes(64)));self.assertEqual(e.rx_pn,1)
        newer,_=self.hardware(2);self.assertEqual(self.hwopen(e,newer),(64,plain))
        self.assertEqual(self.hwopen(e,raw),(-1,bytes(64)));self.assertEqual(e.rx_pn,2)
    def test_hardware_rejects_small_output_without_advancing_counter(self):
        raw,_=self.hardware();e=epoch(header=FRAME[:24])
        self.assertEqual(self.hwopen(e,raw,capacity=63),(-1,bytes(63)));self.assertEqual(e.rx_pn,0)

if __name__=='__main__':unittest.main(verbosity=2)
