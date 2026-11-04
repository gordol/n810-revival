"""Shared runtime codec keeps values typed and stream reads bounded."""
from pathlib import Path
import io,sys,unittest,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from runtime_codec import pack,unpack,frame,frame_size,read_frame,HEADER,atomic_write,copy_data
class RuntimeCodecTests(unittest.TestCase):
    def test_process_local_copy_preserves_types_and_detaches_nested_data(self):
        value={'rows':({'flag':True,'number':1,'float':1.,'big':2**100,'bytes':b'\x00'},), 'list':[None]}
        copied=copy_data(value)
        self.assertEqual(copied,value)
        self.assertIs(type(copied['rows']),tuple)
        for key in ('flag','number','float','big','bytes'):
            self.assertIs(type(copied['rows'][0][key]),type(value['rows'][0][key]))
        value['rows'][0]['number']=7;value['list'].append('later')
        self.assertEqual(copied['rows'][0]['number'],1)
        self.assertEqual(copied['list'],[None])
    def test_binary_round_trip_and_stream_frame(self):
        value=dict(a=True,b=1,c=1.5,text='Nokia café',data=b'\x00\xff',rows=[None,False])
        self.assertEqual(unpack(pack(value)),value)
        raw=frame(value);self.assertEqual(read_frame(io.BytesIO(raw)),value)
        for size in range(HEADER):self.assertIsNone(frame_size(raw[:size]))
    def test_private_atomic_state_replaces_complete_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'state.msgpack';atomic_write(path,{'a':1})
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            atomic_write(path,{'a':2});self.assertEqual(unpack(path.read_bytes()),{'a':2})
            self.assertEqual(list(Path(tmp).iterdir()),[path])

    def test_limits_truncation_and_trailing_data(self):
        with self.assertRaises(ValueError):frame({'x':'a'*40},8)
        with self.assertRaises(ValueError):unpack(pack({})+b'x')
        with self.assertRaises(ValueError):read_frame(io.BytesIO(frame({'x':1})[:-1]))
        with self.assertRaises(ValueError):frame_size(b'{"a":1}')
        with self.assertRaises(ValueError):unpack(b'x'*9,8)
if __name__=='__main__':unittest.main()
