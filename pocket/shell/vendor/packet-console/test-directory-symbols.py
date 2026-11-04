"""Persist only actual decoded APRS symbols through the existing evidence schema."""
import importlib.util,json
from pathlib import Path
import tempfile,unittest
HERE=Path(__file__).resolve().parent

def load(name,file):
 s=importlib.util.spec_from_file_location(name,HERE/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

d=load('directory','n810-aprs-directory.py');p=load('projection','n810-directory-projection.py')
STAMP='2026-10-19T01:02:03+00:00'
def addr(call,last=False):return bytes(ord(c)<<1 for c in call.ljust(6))+bytes([0x60|last])
def record(payload,dest='APRS',stamp=STAMP):
 return dict(time=stamp,direction='radio_to_host',frame=(b'\0'+addr(dest)+addr('TEST',True)+b'\x03\xf0'+payload.encode('ascii')).hex())

class SymbolTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.path=Path(self.temp.name)/'db';self.db=d.database(self.path);self.addCleanup(self.db.close);self.monitor=d.load_monitor()
 def test_actual_capture_symbol_position_role_and_no_repeater_inference(self):
  row=record('!4713.00N/12230.00W#BBS')
  self.assertEqual(d.ingest(self.db,[row],self.monitor,'N0CALL'),1)
  symbol=self.db.execute("SELECT stamp,detail FROM evidence WHERE kind='symbol'").fetchone()
  self.assertEqual(symbol[0],STAMP);self.assertEqual(json.loads(symbol[1]),dict(table='/',code='#'))
  batch=p.map_stations(self.path)['rows'][0];detail=p.station_details(self.path,'TEST')
  self.assertEqual(batch['symbol'],dict(table='/',code='#',stamp=STAMP,source='capture'))
  self.assertEqual(detail['symbol'],batch['symbol']);self.assertIsNotNone(batch['position'])
  self.assertIn('digipeater_advertised',batch['categories']);self.assertNotIn('repeater',batch['categories'])
 def test_duplicate_does_not_change_counts_or_evidence(self):
  row=record('!4713.00N/12230.00W#')
  d.ingest(self.db,[row],self.monitor,'N0CALL');before=list(self.db.execute('SELECT * FROM evidence ORDER BY kind'))
  self.assertEqual(d.ingest(self.db,[row],self.monitor,'N0CALL'),0)
  self.assertEqual(list(self.db.execute('SELECT * FROM evidence ORDER BY kind')),before)
  self.assertEqual(self.db.execute('SELECT packets FROM stations').fetchone()[0],1)
 def test_missing_or_invalid_symbol_stays_unknown(self):
  for payload in ('>BBS 146.820MHz','!9913.00N/12230.00W#','!4713.00N/12230.00W '):
   self.assertNotIn('symbol',dict(d.evidence(payload)))
  for table,code in [('/',None),('/', 'xx'),('/', '\0'),('é','#'),('','>')]:self.assertIsNone(d.model.symbol_value(table,code))
  row=record('>146.820MHz');d.ingest(self.db,[row],self.monitor,'N0CALL')
  self.assertIsNone(p.map_stations(self.path)['rows'][0]['symbol'])
 def test_overlay_and_mice_original_bytes_retained(self):
  facts=dict(d.evidence('!4713.00NA12230.00W#'));self.assertEqual(json.loads(facts['symbol']),dict(table='A',code='#'))
  facts=dict(d.evidence('`27}m57>/]comment','T7QPXV'))
  self.assertEqual(json.loads(facts['symbol']),dict(table='/',code='>'))
  d.ingest(self.db,[record('`27}m57>/]comment',dest='T7QPXV')],self.monitor,'N0CALL')
  self.assertEqual(p.map_stations(self.path)['rows'][0]['symbol']['code'],'>')
 def test_older_capture_cannot_overwrite_newer_symbol(self):
  d.ingest(self.db,[record('!4713.00N/12230.00W>')],self.monitor,'N0CALL')
  d.ingest(self.db,[record('!4713.00N/12230.00W#',stamp='2020-01-01T00:00:00+00:00')],self.monitor,'N0CALL')
  self.assertEqual(p.map_stations(self.path)['rows'][0]['symbol']['code'],'>')

if __name__=='__main__':unittest.main()
