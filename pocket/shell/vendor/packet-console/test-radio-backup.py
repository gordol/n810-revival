import importlib.util
from pathlib import Path
import json,unittest
spec=importlib.util.spec_from_file_location('backup',Path(__file__).with_name('n810-radio-backup.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
class Tests(unittest.TestCase):
 def test_read_framing_and_write_guard(self):
  self.assertEqual(b.frame(4,b'\3').hex(),'ff0100010002000403')
  link=b.Link(None)
  for cmd in [11,14,30,31,34,35,60,64]:
   with self.assertRaises(ValueError):link.request(cmd)
 def test_channel_decode(self):
  layouts=json.loads(Path(__file__).with_name('radio-read-layouts.json').read_text())
  raw=b'\0'+int(144390000).to_bytes(4,'big')+int(146520000).to_bytes(4,'big')+bytes(6)+b'TEST\0\0\0\0\0\0'
  row=b.decode(raw,layouts['RfCh'])
  self.assertEqual(row['tx_freq'],144390000);self.assertEqual(row['rx_freq'],146520000)
  self.assertEqual(row['name_str'],'TEST');self.assertEqual(row['_decoded_bits'],200)
if __name__=='__main__':unittest.main()
