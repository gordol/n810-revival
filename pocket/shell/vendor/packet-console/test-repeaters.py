import importlib.util
from pathlib import Path
import unittest
import tempfile
import zipfile
spec=importlib.util.spec_from_file_location('repeaters',Path(__file__).with_name('n810-repeaters.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class Tests(unittest.TestCase):
 def test_import_and_filter(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'pack.zip'
   header='FC_RECORD_ID,OUTPUT_FREQ,INPUT_FREQ,CALL,CITY,LOCALE,FM_WIDE,LATITUDE,LONGITUDE,EXPIRATION_DATE,CTCSS_IN,CTCSS_OUT\n'
   body='1,146.8,146.2,TEST,Tacoma,South,Y,47.2,-122.5,2030-01-01,103.5,100\n2,146.9,146.3,OLD,Tacoma,South,Y,47.2,-122.5,2020-01-01,,\n3,147,147.6,DIG,Tacoma,South,N,47.2,-122.5,2030-01-01,,\n'
   with zipfile.ZipFile(path,'w') as z:
    z.writestr('WWARA-rptrlist-20261014.csv','DATA_SPEC_VERSION=2015.2.2\n'+header+body)
    z.writestr('copyright.txt','Test fixture notice')
   data=r.import_wwara(path);rows=r.candidates(data,47.17,-122.52,150,'2026-10-15')
   self.assertEqual([x['call'] for x in rows],['TEST'])
   self.assertEqual((rows[0]['tx_ctcss'],rows[0]['rx_ctcss']),(103.5,100))
   self.assertAlmostEqual(rows[0]['tx_mhz']-rows[0]['rx_mhz'],-.6)
   output=Path(folder)/'data.json';r.write(output,data);self.assertEqual(output.stat().st_mode&0o777,0o600)
 def test_service_filters_and_unknown_positions(self):
  services={'services':[dict(call='TEST-10',frequency_mhz=145.63,service='Winlink gateway',transport='Packet',area='Test area',position=None,source_checked='2026-10-15',source_url='https://example.test',verification='published',baud=None),
      dict(call='TEST-1',frequency_mhz=145.63,service='Mailbox',transport='Packet',area='Test area',position=None,source_checked='2026-10-15',source_url='https://example.test',verification='published',baud=None)]}
  data={'repeaters':[]}
  rows=r.directory_rows(data,services,47,-122,1,'All')
  self.assertEqual(len(rows),2)
  self.assertTrue(all(row['km'] is None for row in rows))
  self.assertEqual(len(r.directory_rows(data,services,47,-122,1,'Winlink')),1)
  self.assertEqual(len(r.directory_rows(data,services,47,-122,1,'Mailboxes')),1)
  self.assertEqual(r.directory_rows(data,services,47,-122,1,'Voice'),[])
  gateway=next(row for row in rows if row['kind']=='Winlink')
  self.assertIn('Baud     Unknown',r.details(gateway,{}))
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'banks.json'
   r.add_service(gateway,path);r.add_service(gateway,path)
   import json
   library=json.loads(path.read_text());picks=next(b for b in library['banks'] if b['name']=='Data service picks')
   self.assertEqual(len(picks['channels']),1)
   channel=picks['channels'][0]
   self.assertFalse(channel['tx_enabled']);self.assertEqual(channel['connect_call'],'TEST-10')
   self.assertIsNone(channel['baud']);self.assertIn('bandwidth',channel['review_required'])
 def test_directory_render(self):
  class Window:
   def getmaxyx(self):return 39,133
   def erase(self):pass
   def refresh(self):pass
   def addnstr(self,y,x,text,n,attr):assert 0<=y<39 and 0<=x<133 and n<=132-x
  class Args:lat=47.17;lon=-122.52;radius=150
  r.draw(Window(),[],0,{},Args(),'','Packet',{})
 def test_distance(self):
  self.assertEqual(r.distance(47,-122,47,-122),0)
  self.assertAlmostEqual(r.distance(0,0,1,0),111.19,places=1)
if __name__=='__main__':unittest.main()
