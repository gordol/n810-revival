import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('control',Path(__file__).with_name('n810-radio-control.py'))
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
class Tests(unittest.TestCase):
 def test_profiles_save_and_validation(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'profiles.json';profiles=c.load(path)
   self.assertIsNone(profiles['Voice Alert test']['tx_ctcss'])
   profiles['APRS']['rx_ctcss']=c.validate('rx_ctcss','100')
   c.save(path,profiles);self.assertEqual(c.load(path),profiles)
   self.assertEqual(path.stat().st_mode&0o777,0o600)
   for key,value in [('digital_channel','1'),('channel','180'),('rx_mhz','nan'),('tx_mhz','0'),('beacon_seconds','-1'),('rx_ctcss','nan')]:
    with self.assertRaises(ValueError):c.validate(key,value)
 def test_render(self):
  class Window:
   def __init__(self,h,w):self.h=h;self.w=w;self.text=[]
   def getmaxyx(self):return self.h,self.w
   def erase(self):pass
   def refresh(self):pass
   def addnstr(self,y,x,text,n,attr):
    assert 0<=y<self.h and 0<=x<self.w and n<=self.w-x-1
    self.text.append(text)
  for size in ((39,133),(24,80)):
   win=Window(*size);c.render(win,c.defaults(),0,0,'fields','',None,False,False)
   self.assertIn('Radio: not synchronized',win.text)
   c.render(win,c.defaults(),0,0,'profiles','',None,False,True)
if __name__=='__main__':unittest.main()
