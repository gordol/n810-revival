import importlib.util
from pathlib import Path
import struct
import unittest
import uuid
spec=importlib.util.spec_from_file_location('sdp',Path(__file__).with_name('n810-audio-sdp.py'));s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

def seq(value):return b'\x35'+bytes([len(value)])+value

def record(channel=2,service=None):
    service=uuid.UUID(service or s.AUDIO_UUID).bytes
    return seq(b'\x09\0\1'+seq(b'\x1c'+service)+b'\x09\0\4'+seq(seq(b'\x19\x01\0')+seq(b'\x19\0\3\x08'+bytes([channel]))))

class Tests(unittest.TestCase):
    def test_query_is_sdp_only_uuid128(self):
        raw=s.query();kind,transaction,size=struct.unpack('>BHH',raw[:5])
        self.assertEqual((kind,transaction,size),(6,1,len(raw)-5))
        self.assertIn(uuid.UUID(s.AUDIO_UUID).bytes,raw)
    def test_actual_service_class_and_rfcomm_channel_required(self):
        self.assertEqual(s.channels(seq(record())),[2])
        self.assertEqual(s.channels(seq(record(service='00001101-0000-1000-8000-00805f9b34fb'))),[])
        self.assertEqual(s.channels(seq(record(31))),[])
        self.assertEqual(s.channels(seq(record(4)+record(4))),[4])
    def test_bad_lengths_and_continuation_rejected(self):
        with self.assertRaises(ValueError):s.channels(seq(record())[:-1])
        with self.assertRaises(ValueError):s.query(1,b'x'*17)
        with self.assertRaises(ValueError):s.element(b'\x37\xff\xff\xff\xff')

if __name__=='__main__':unittest.main()
