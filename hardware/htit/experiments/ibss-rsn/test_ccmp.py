"""Native CCMP implementation checked against IEEE data and a Python AESCCM oracle.

Compiles only into a temporary directory. Never opens a port or Wi-Fi interface.
"""
import ctypes as c
from pathlib import Path
import random
import shlex
import subprocess
import tempfile
import unittest
import zlib
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

ROOT=Path(__file__).resolve().parent
KEY=bytes.fromhex('c97c1f67ce371185514a8a19f2bdd52f')
HEADER=bytes.fromhex('0848c32c0fd2e128a57c5030f1844408abaea5b8fcba8033')
PLAIN=bytes.fromhex('f8ba1a55d02f85ae967bb62fb6cda8eb7e78a050')
PN=0xb5039776e70c
WIRE=HEADER+bytes.fromhex('0ce70020769703b5f3d0a2fe9a3dbf2342a643e43246e80c3c04d0197845ce0b16f97623')


class Epoch(c.Structure):
    _fields_=[('key',c.c_ubyte*16),('transmitter',c.c_ubyte*6),
              ('receiver',c.c_ubyte*6),('bssid',c.c_ubyte*6),
              ('tx_pn',c.c_uint64),('rx_pn',c.c_uint64),('key_id',c.c_ubyte),('key_valid',c.c_bool)]


def epoch(key=KEY,header=HEADER,key_id=0):
    e=Epoch()
    e.key[:]=key;e.transmitter[:]=header[10:16];e.receiver[:]=header[4:10]
    e.bssid[:]=header[16:22];e.key_id=key_id
    return e


class CcmpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='htit-ccmp-')
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','openssl'],text=True))
        library=Path(cls.temp.name)/'ccmp.dylib'
        subprocess.run(['c++','-std=c++17','-Wall','-Wextra','-Werror','-O2','-shared','-fPIC',
                        str(ROOT/'ccmp.cpp'),str(ROOT/'crypto_openssl.cpp'),'-o',str(library),*flags],check=True)
        cls.lib=c.CDLL(str(library))
        cls.lib.ccmp_seal.argtypes=[c.POINTER(Epoch),c.c_char_p,c.c_char_p,c.c_size_t,c.c_void_p,c.c_size_t]
        cls.lib.ccmp_open.argtypes=[c.POINTER(Epoch),c.c_char_p,c.c_size_t,c.c_void_p,c.c_size_t]
        cls.lib.ccmp_seal.restype=cls.lib.ccmp_open.restype=c.c_int
        cls.lib.ccmp_install_key.argtypes=[c.POINTER(Epoch),c.c_char_p,c.c_uint64]
        cls.lib.ccmp_valid_fcs.argtypes=[c.c_char_p,c.c_size_t]
        cls.lib.ccmp_valid_fcs.restype=c.c_bool

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def seal(self,e,plain=PLAIN,header=HEADER,cap=1440):
        out=c.create_string_buffer(b'X'*cap,cap)
        n=self.lib.ccmp_seal(c.byref(e),header,plain,len(plain),out,cap)
        return n,out.raw[:n] if n>=0 else out.raw

    def open(self,e,frame=WIRE,cap=1400):
        out=c.create_string_buffer(b'X'*cap,cap)
        n=self.lib.ccmp_open(c.byref(e),frame,len(frame),out,cap)
        return n,out.raw[:n] if n>=0 else out.raw

    def rejected(self,e,frame):
        self.assertEqual(self.open(e,frame),(-1,b'\0'*1400))

    def test_key_reinstallation_preserves_counters_and_raises_only_receive_floor(self):
        e=Epoch();self.lib.ccmp_install_key(c.byref(e),KEY,7)
        self.assertTrue(e.key_valid);self.assertEqual((e.tx_pn,e.rx_pn),(0,7))
        e.tx_pn=123;e.rx_pn=456
        self.lib.ccmp_install_key(c.byref(e),KEY,12)
        self.assertEqual((e.tx_pn,e.rx_pn),(123,456))
        self.lib.ccmp_install_key(c.byref(e),KEY,789)
        self.assertEqual((e.tx_pn,e.rx_pn),(123,789))
        self.lib.ccmp_install_key(c.byref(e),bytes([1])*16,3)
        self.assertEqual((e.tx_pn,e.rx_pn),(0,3))

    def test_ieee_known_answer_encrypt_and_decrypt(self):
        tx=epoch();tx.tx_pn=PN-1
        self.assertEqual(self.seal(tx),(len(WIRE),WIRE))
        rx=epoch();self.assertEqual(self.open(rx),(20,PLAIN));self.assertEqual(rx.rx_pn,PN)

    def test_fcs_checks_ieee_vector_random_payloads_and_corruption(self):
        self.assertTrue(self.lib.ccmp_valid_fcs(WIRE+bytes.fromhex('1d99f066'),len(WIRE)+4))
        for data in (b'',b'123456789',bytes(range(256)),WIRE):
            frame=data+zlib.crc32(data).to_bytes(4,'little')
            self.assertTrue(self.lib.ccmp_valid_fcs(frame,len(frame)))
            for offset in range(len(frame)):
                changed=bytearray(frame);changed[offset]^=1
                self.assertFalse(self.lib.ccmp_valid_fcs(bytes(changed),len(changed)))
        for length in range(4):self.assertFalse(self.lib.ccmp_valid_fcs(b'\0'*length,length))

    def test_random_frames_match_independent_aesccm_oracle(self):
        randomizer=random.Random(4913)
        for size in (1,15,16,17,254,500,1400):
            for key_id in range(4):
                key=randomizer.randbytes(16);plain=randomizer.randbytes(size)
                tx=epoch(key,key_id=key_id);tx.tx_pn=randomizer.randrange(1,1<<40)
                length,wire=self.seal(tx,plain)
                self.assertEqual(length,size+40)
                pn=tx.tx_pn;nonce=b'\0'+HEADER[10:16]+pn.to_bytes(6,'big')
                aad=bytes([HEADER[0]&0x8f,(HEADER[1]&0xc7)|0x40])+HEADER[4:22]+b'\0\0'
                self.assertEqual(wire[32:],AESCCM(key,tag_length=8).encrypt(nonce,plain,aad))
                self.assertEqual(self.open(epoch(key,key_id=key_id),wire),(size,plain))

    def test_duplicate_and_out_of_order_packets_are_rejected(self):
        tx=epoch();_,one=self.seal(tx);_,two=self.seal(tx);rx=epoch()
        self.assertEqual(self.open(rx,two),(20,PLAIN))
        self.rejected(rx,one);self.rejected(rx,two)

    def test_ciphertext_tag_and_packet_number_tampering_cannot_poison_replay_state(self):
        for offset in list(range(24,60)):
            for bit in range(8):
                altered=bytearray(WIRE);altered[offset]^=1<<bit;rx=epoch()
                self.rejected(rx,bytes(altered));self.assertEqual(rx.rx_pn,0)
                self.assertEqual(self.open(rx),(20,PLAIN))

    def test_addresses_bssid_and_key_binding(self):
        for offset in range(4,22):
            altered=bytearray(WIRE);altered[offset]^=1
            self.rejected(epoch(),bytes(altered))
        bad=epoch();bad.key[0]^=1;self.rejected(bad,WIRE)
        self.rejected(epoch(key_id=1),WIRE)

    def test_plaintext_management_qos_ds_and_fragment_frames_are_rejected(self):
        changes=[(0,0x80),(0,0x88),(1,0),(1,0x41),(1,0x42),(1,0x44),(1,0xc0),(22,1)]
        for offset,value in changes:
            altered=bytearray(WIRE);altered[offset]=value
            self.rejected(epoch(),bytes(altered))

    def test_mutable_duration_retry_and_sequence_fields_do_not_break_ccmp(self):
        altered=bytearray(WIRE);altered[1]^=0x08;altered[2:4]=b'\0\0';altered[22:24]=b'\x10\x02'
        self.assertEqual(self.open(epoch(),bytes(altered)),(20,PLAIN))

    def test_zero_packet_number_invalid_key_id_and_counter_exhaustion(self):
        altered=bytearray(WIRE)
        for offset in (24,25,28,29,30,31):altered[offset]=0
        self.rejected(epoch(),bytes(altered))
        tx=epoch();tx.tx_pn=(1<<48)-1
        self.assertEqual(self.seal(tx),(-1,b'\0'*1440));self.assertEqual(tx.tx_pn,(1<<48)-1)
        tx=epoch(key_id=4);self.assertEqual(self.seal(tx),(-1,b'\0'*1440))

    def test_truncation_oversize_empty_and_output_capacity(self):
        for size in range(len(WIRE)):self.rejected(epoch(),WIRE[:size])
        self.rejected(epoch(),WIRE+b'\0'*1400)
        for plain in (b'',b'x'*1401):self.assertEqual(self.seal(epoch(),plain),(-1,b'\0'*1440))
        self.assertEqual(self.open(epoch(),cap=19),(-1,b'\0'*19))
        self.assertEqual(self.seal(epoch(),cap=59),(-1,b'\0'*59))


if __name__=='__main__':unittest.main()
