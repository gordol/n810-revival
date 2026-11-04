"""Bounded station map facts, honest categories and content-based cache revisions."""
import importlib.util,json
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('projection',HERE/'n810-directory-projection.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
STAMP='2026-10-19T01:02:03+00:00'

class MapProjectionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.path=Path(self.temp.name)/'db';self.db=p.directory().database(self.path);self.addCleanup(self.db.close)
  for call in ('DIGI','VOICE','UNKNOWN'):self.db.execute('INSERT INTO stations VALUES(?,?,?,?)',(call,STAMP,STAMP,1))
  for call,kind,value in [('DIGI','position','[47.1,-122.5]'),('DIGI','role','APRS digipeater / advertised symbol'),('VOICE','voice','146.820MHz'),('VOICE','service:BBS','BBS mention')]:self.db.execute('INSERT INTO evidence VALUES(?,?,?,?)',(call,kind,STAMP,value))
  self.db.execute("INSERT INTO legacy_evidence VALUES('DIGI','position','legacy unknown date','[1,2]')")
  self.db.execute('INSERT INTO via VALUES(?,?,?,?,?)',('VOICE','DIGI',STAMP,STAMP,1));self.db.commit()
 def test_positions_and_categories_preserve_provenance_not_inference(self):
  rows={r['call']:r for r in p.map_stations(self.path)['rows']}
  digi=rows['DIGI'];self.assertEqual(digi['position']['lat'],47.1);self.assertEqual(digi['position']['source'],'capture')
  self.assertIsNone(digi['symbol']);self.assertIn('digipeater_advertised',digi['categories']);self.assertIn('relay_observed',digi['categories'])
  self.assertEqual(set(rows['VOICE']['categories']),{'voice_advertised','service:BBS'})
  self.assertEqual(rows['UNKNOWN']['categories'],[]);self.assertIsNone(rows['UNKNOWN']['position'])
  for row in rows.values():
   self.assertNotIn('repeater',row['categories']);self.assertNotIn('internet_linked',row['categories'])
  json.dumps(rows)
 def test_symbol_only_if_explicitly_stored_and_malformed_position_unknown(self):
  self.db.execute('INSERT INTO evidence VALUES(?,?,?,?)',('DIGI','symbol',STAMP,json.dumps(dict(table='/',code='#'))))
  self.db.execute('INSERT INTO evidence VALUES(?,?,?,?)',('UNKNOWN','position',STAMP,'[999,0]'));self.db.commit()
  rows={r['call']:r for r in p.map_stations(self.path)['rows']}
  self.assertEqual(rows['DIGI']['symbol']['code'],'#');self.assertIsNone(rows['UNKNOWN']['position'])
 def test_bounded_pages_and_no_database_mutation(self):
  before=self.path.read_bytes();result=p.map_stations(self.path,limit=1)
  self.assertEqual(len(result['rows']),1);self.assertTrue(result['has_more'])
  self.assertEqual(p.map_stations(self.path,limit=0)['rows'],[])
  self.assertEqual(self.path.read_bytes(),before)
 def test_cache_skips_heartbeats_and_content_revision_ignores_noop(self):
  cache=p.StationMapCache(self.path);self.addCleanup(cache.close)
  first=cache.snapshot()
  with patch.object(p,'_station_batch',wraps=p._station_batch) as query:
   self.assertIs(cache.snapshot(),first);query.assert_not_called()
   self.db.execute("UPDATE stations SET packets=packets WHERE call='DIGI'");self.db.commit()
   self.assertIs(cache.snapshot(),first)
   self.db.execute("UPDATE stations SET packets=packets+1 WHERE call='DIGI'");self.db.commit()
   changed=cache.snapshot();self.assertNotEqual(changed['revision'],first['revision'])
   self.assertIs(cache.snapshot(),changed)
 def test_lost_database_not_served_as_current(self):
  cache=p.StationMapCache(self.path);self.addCleanup(cache.close);cache.snapshot();self.path.unlink()
  with self.assertRaises(OSError):cache.snapshot()
  self.assertIsNone(cache.value)

if __name__=='__main__':unittest.main()
