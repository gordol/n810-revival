import importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('readback',Path(__file__).with_name('n810-radio-readback.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class Tests(unittest.TestCase):
 def test_only_completed_restored_snapshot(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder)
   for name,data in [('1',dict(complete=True,banks=[])),('2',dict(complete=False)),('3',dict(complete=True,restore_bank={},restored=False))]:
    path=root/name;path.mkdir();(path/'backup.json').write_text(json.dumps(data))
   # Empty restore response is not a valid proof of restoration either.
   path,data=r.latest(root)
   self.assertEqual(path.parent.name,'1')
 def test_tone_and_channel_details(self):
  self.assertEqual(r.tone(0),'Off');self.assertEqual(r.tone(10350),'103.5 Hz');self.assertEqual(r.tone(23),'DCS 23')
  fields=dict(name_str='APRS',tx_at_max_power=True,tx_at_med_power=False,rx_freq=144390000,tx_freq=144390000,
   rx_sub_audio=0,tx_sub_audio=0,rx_mod=0,bandwidth=1,tx_disable=False,scan=False,mute=False,talk_around=False,pre_de_emph_bypass=False)
  details=dict(r.channel_details(dict(index=0,decoded=fields)))
  self.assertEqual(details['RX'],'144.390000 MHz');self.assertEqual(details['Offset'],'+0.000 MHz')
 def test_small_and_device_render(self):
  class Win:
   def __init__(self,h,w):self.size=h,w
   def getmaxyx(self):return self.size
   def erase(self):pass
   def refresh(self):pass
   def addnstr(self,y,x,text,n,attr):assert 0<=y<self.size[0] and 0<=x<self.size[1] and n<=self.size[1]-x-1
  data=dict(banks=[dict(index=0,name='Ham',channels=[dict(index=0,response={'status':1})])],settings={'kiss_en':True},beacon={'aprs_callsign':'N0ANT'},reads={})
  for size in [(39,133),(24,80)]:
   for tab in range(4):r.draw(Win(*size),data,tab,0,0,0,0,None)
if __name__=='__main__':unittest.main()
