import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('directory',Path(__file__).with_name('n810-aprs-directory.py'))
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)

def address(call,ssid=0,last=False,used=False):
 return bytes(ord(c)<<1 for c in call.ljust(6))+bytes([0x60|(ssid<<1)|int(last)|(0x80 if used else 0)])

def record(source='TEST',used=True):
 frame=b'\0'+address('APRS')+address(source)+address('W7DK',last=True,used=used)+b'\x03\xf0hello'
 return dict(time='2026-10-15T07:00:00+00:00',direction='radio_to_host',frame=frame.hex())

class Tests(unittest.TestCase):
 def test_control_text_and_malformed_frames(self):
  self.assertEqual(d.terminal.printable('bad\0call\x1b[31m'),'bad\\x00call\\x1b[31m')
  with tempfile.TemporaryDirectory() as folder:
   db=d.database(Path(folder)/'directory.db')
   row=record();row['frame']='00ff01003700020009020082a09a92606c60ac8682a0964060ae92888a64406303f0'
   self.assertEqual(d.ingest(db,[row],d.load_monitor(),'N0DEM'),0)
   self.assertEqual(db.execute('SELECT count(*) FROM stations').fetchone()[0],0)
   db.close()
 def test_shared_mice_history(self):
  import json
  with tempfile.TemporaryDirectory() as folder:
   db=d.database(Path(folder)/'directory.db');path=Path(folder)/'history.json'
   path.write_text(json.dumps({'packets':['00:12:01 K7MM-2>T7QPXV,WIDE1-1,WIDE2-1 ctl=03 pid=f0 `27}m57>/]comment']}))
   d.import_history(db,path,'N0DEM');d.import_history(db,path,'N0DEM')
   ev={k:v for k,t,v in d.station_evidence(db,'K7MM-2')}
   self.assertAlmostEqual(json.loads(ev['position'])[0],47.181,6)
   self.assertEqual(json.loads(ev['mice'])['speed_knots'],12)
   self.assertEqual(db.execute('SELECT packets FROM stations').fetchone(),(0,))
   self.assertEqual(db.execute('SELECT count(*) FROM legacy_records').fetchone(),(1,))
   db.close()
 def test_ui_state(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('ui',Path(__file__).with_name('n810-ui-state.py'))
  ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
  with tempfile.TemporaryDirectory() as folder:
   ui.root=lambda:Path(folder)
   saved=dict(call='BALDI',scroll=4,terrain=True,center=[47.2,-122.5])
   ui.save('test',saved);self.assertEqual(ui.load('test'),saved)
   self.assertEqual((Path(folder)/'test.json').stat().st_mode&0o777,0o600)
   (Path(folder)/'test.json').write_text('invalid')
   self.assertEqual(ui.load('test'),{})
 def test_relay_direction(self):
  with tempfile.TemporaryDirectory() as folder:
   db=d.database(Path(folder)/'directory.db')
   d.ingest(db,[record()],d.load_monitor(),'N0DEM')
   relays=d.station_evidence(db,'W7DK')
   rows=dict((k,v) for k,t,v in relays)
   self.assertIn('TEST',rows['forwarded'])
   self.assertEqual(db.execute('SELECT relay FROM via WHERE call=?',('TEST',)).fetchone(),('W7DK',))
   db.close()
 def test_legacy_import_provenance(self):
  import json
  with tempfile.TemporaryDirectory() as folder:
   db=d.database(Path(folder)/'directory.db');path=Path(folder)/'history.json'
   line='21:28:40 TEST>APRS,W7DK* ctl=03 pid=f0 !4713.13N/12150.61W_PHG7830/W2,WAn,Baldi'
   path.write_text(json.dumps({'packets':[line,line,line.replace('TEST>','N0DEM>')]}))
   self.assertEqual(d.import_history(db,path,'N0DEM'),2)
   self.assertEqual(d.import_history(db,path,'N0DEM'),0)
   self.assertEqual(db.execute('SELECT packets FROM stations').fetchone(),(0,))
   self.assertEqual(db.execute('SELECT count(*) FROM via').fetchone(),(0,))
   ev={k:(t,v) for k,t,v in d.station_evidence(db,'TEST')}
   self.assertIn('role',ev);self.assertEqual(d.age(ev['position'][0]),'older text')
   d.ingest(db,[record()],d.load_monitor(),'N0DEM')
   self.assertEqual(db.execute('SELECT last,packets FROM stations WHERE call="TEST"').fetchone(),('2026-10-15T07:00:00+00:00',1))
   self.assertEqual(db.execute('SELECT count(*) FROM via').fetchone(),(1,))
   db.close()
 def test_readable_details(self):
  ev=[(k,'2026-10-15T07:00:00+00:00',v) for k,v in d.evidence('!4713.13N/12150.61W_PHG7830/W2,WAn,Baldi N7FSP')]
  lines=d.station_details('BALDI','',False,'2026-10-15T07:00:00+00:00',6,ev,[],'',85)
  self.assertIn('RADIO',lines)
  self.assertIn('Power      49 W',lines)
  self.assertFalse(any('2026-10-15T' in x for x in lines))
  self.assertTrue(any('PHG7830' in x for x in d.station_details('BALDI','',False,'2026-10-15T07:00:00+00:00',6,ev,[],'',85,True)))
 def test_phg(self):
  import json
  rf=json.loads(dict(d.evidence('!4713.13N/12150.61W_PHG7830/W2,WAn,Baldi N7FSP'))['phg'])
  self.assertEqual((rf['watts'],rf['height_ft'],rf['height_m'],rf['gain_db'],rf['direction']),(49,2560,780,3,'omnidirectional'))
  rf=json.loads(dict(d.evidence('>PHG5132'))['phg'])
  self.assertEqual((rf['watts'],rf['height_ft'],rf['gain_db'],rf['direction']),(25,20,3,'E'))
  self.assertNotIn('phg',dict(d.evidence('>PHGxxxx')))
 def test_passive_evidence(self):
  self.assertIn(('messaging','Messaging advertised'),d.evidence('=4711.51N/12231.75W-test'))
  self.assertTrue(any(k=='position' for k,v in d.evidence('=4711.51N/12231.75W-test')))
  self.assertFalse(any(k=='position' for k,v in d.evidence(':TARGET   :meet at 4711.51N/12231.75W')))
  self.assertIn(('ack','Acknowledgement observed'),d.evidence(':TARGET   :ack56'))
  self.assertTrue(any(k=='service:BBS' for k,v in d.evidence('>BBS 145.010MHz')))
  self.assertFalse(d.evidence('`binary Mic-E'))
 def test_replay_and_used_hops(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'directory.db';db=d.database(path);monitor=d.load_monitor()
   self.assertEqual(d.ingest(db,[record(),record()],monitor,'N0DEM'),1)
   self.assertEqual(db.execute('SELECT packets FROM via').fetchone(),(1,))
   d.ingest(db,[record('OTHER',False),record('N0DEM')],monitor,'N0DEM')
   # Received traffic retains the sender identity, including our own call.
   self.assertEqual(db.execute('SELECT packets FROM stations WHERE call="N0DEM"').fetchone(),(1,))
   sent=record('N0DEM');sent['direction']='host_to_radio'
   self.assertEqual(d.ingest(db,[sent],monitor,'N0DEM'),0)
   self.assertEqual(db.execute('SELECT count(*) FROM stations').fetchone(),(3,))
   self.assertEqual(db.execute('SELECT count(*) FROM via').fetchone(),(2,))
   db.close();db=d.database(path)
   self.assertEqual(d.ingest(db,[record()],monitor,'N0DEM'),0)
   self.assertEqual(db.execute('SELECT packets FROM stations WHERE call="TEST"').fetchone(),(1,))
   db.close()

if __name__=='__main__':unittest.main()
