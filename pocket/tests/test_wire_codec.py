"""Optional native acceleration preserves the existing portable binary protocol."""
from pathlib import Path
import importlib.util,struct,sys,unittest
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum'
sys.path.insert(0,str(root))
import wire
spec=importlib.util.spec_from_file_location('portable_messagepack',root/'_umsgpack.py')
portable=importlib.util.module_from_spec(spec);spec.loader.exec_module(portable)

class CodecTests(unittest.TestCase):
    def test_portable_and_selected_codec_interoperate(self):
        values=[dict(version=1,value=value) for value in (None,True,False,-2**63,2**64-1,1.5,'héllo',b'\x00\xff',[],{},dict(rows=[dict(name='radio',connected=True)]))]
        for value in values:
            selected=wire.encode(value)
            with patch.object(wire,'NATIVE_CODEC',False),patch.object(wire,'codec',portable):
                self.assertEqual(wire.decode(selected),value)
                fallback=wire.encode(value)
            self.assertEqual(wire.decode(fallback),value)

    def test_malformed_frames_are_rejected_by_both_backends(self):
        payloads=[b'\xc1',b'\x81',b'\x82\xa7version\x01\xa7version\x01',portable.packb(dict(version=True)),portable.packb(dict(version=1,value=float('nan'))),portable.packb(dict(version=1))+b'\x00',portable.packb(dict(version=1,value={1:'bad'}))]
        for native in (False,wire.NATIVE_CODEC):
            codec=wire.codec if native else portable
            with patch.object(wire,'NATIVE_CODEC',native),patch.object(wire,'codec',codec):
                for payload in payloads:
                    frame=wire.MAGIC+struct.pack('!I',len(payload))+payload
                    with self.subTest(native=native,payload=payload),self.assertRaises(ValueError):wire.decode(frame)
                valid=wire.encode(dict(version=1,value='radio'))
                for end in range(len(valid)):
                    with self.assertRaises((ValueError,ConnectionError)):wire.decode(valid[:end])
                value=None
                for _ in range(26):value=[value]
                with self.assertRaises(ValueError):wire.encode(dict(version=1,value=value))

    def test_native_socket_reader_handles_short_reads_and_truncation(self):
        value=dict(version=1,services=[dict(id='system',state='ready')])
        raw=wire.encode(value)
        class Fragmented:
            def __init__(self,data):self.data=data
            def recv(self,size):
                chunk=self.data[:min(size,2)];self.data=self.data[len(chunk):];return chunk
        self.assertEqual(wire.read_socket(Fragmented(raw)),value)
        for end in range(len(raw)):
            with self.subTest(end=end),self.assertRaises(ConnectionError):wire.read_socket(Fragmented(raw[:end]))
        oversized=wire.MAGIC+struct.pack('!I',wire.LIMIT)
        with self.assertRaises(ValueError):wire.read_socket(Fragmented(oversized))

if __name__=='__main__':unittest.main()
