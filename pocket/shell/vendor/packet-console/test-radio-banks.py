import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('banks',Path(__file__).with_name('n810-radio-banks.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
class Tests(unittest.TestCase):
 def test_unlimited_local_banks_and_roundtrip(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'banks.json';data={'version':1,'banks':[]}
   csv='name,rx_mhz,tx_mhz,rx_ctcss,tx_ctcss,scan,tx_enabled\nTest,146.52,146.52,,100,true,false\n'
   for i in range(12):b.import_csv(data,csv,'Bank %d'%i)
   b.save(path,data);self.assertEqual(b.load(path),data)
   self.assertEqual(path.stat().st_mode&0o777,0o600)
   original=next(bank for bank in data['banks'] if bank['name']=='Bank 0')
   copy={'version':1,'banks':[]};bank=b.import_csv(copy,b.export_csv(original),'Copy')
   for key,_ in b.FIELDS:self.assertEqual(bank['channels'][0][key],original['channels'][0][key])
 def test_core_slots(self):
  data={'version':1,'banks':[]};b.ensure_core(data)
  self.assertEqual([r['hardware_slot'] for r in data['banks'][0]['channels']],[0,1,2])
  self.assertEqual([r['rx_mhz'] for r in data['banks'][0]['channels']],[144.390,146.520,446.000])
  data['banks'][0]['channels'].reverse()
  with self.assertRaises(ValueError):b.ensure_core(data)
 def test_invalid_import_is_atomic(self):
  data={'version':1,'banks':[]}
  with self.assertRaises(ValueError):b.import_csv(data,'name,rx_mhz\nGood,146.52\nBad,nan\n','Bad')
  self.assertEqual(data['banks'],[])
 def test_bad_saved_file_preserved(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'banks.json';path.write_text('broken')
   with self.assertRaises(ValueError):b.load(path)
   self.assertEqual(path.read_text(),'broken')
 def test_render_sizes_and_empty(self):
  class Window:
   def __init__(self,h,w):self.size=h,w
   def getmaxyx(self):return self.size
   def erase(self):pass
   def refresh(self):pass
   def addnstr(self,y,x,text,n,attr):
    assert 0<=y<self.size[0] and 0<=x<self.size[1] and n<=self.size[1]-x-1
  for size in [(39,133),(24,80)]:
   for data in [{'version':1,'banks':[]},b.load('/tmp/nonexistent-bank-test-9973.json')]:
    b.render(Window(*size),data,0,0,0,0,'',None,False)
if __name__=='__main__':unittest.main()
