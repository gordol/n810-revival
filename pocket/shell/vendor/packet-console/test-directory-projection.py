"""Read-only Directory projection, bounds, shared evidence and handoff checks."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('projection',HERE/'n810-directory-projection.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
STAMP='2020-01-02T03:04:05+00:00'

class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'directory.db';db=p.directory().database(self.path)
        for call in ('TEST-1','TEST-2','OTHER'):
            db.execute('INSERT INTO stations VALUES(?,?,?,?)',(call,STAMP,STAMP,3))
        db.execute("INSERT INTO people VALUES('TEST',1,'Test person','Shared notes')")
        db.execute('INSERT INTO evidence VALUES(?,?,?,?)',('TEST-1','position',STAMP,'[47.1,-122.5]'))
        db.execute("INSERT INTO legacy_evidence VALUES('TEST-1','position','legacy unknown date','[1,2]')")
        db.execute("INSERT INTO legacy_evidence VALUES('TEST-1','service:BBS','legacy unknown date','BBS mention')")
        for relay in ('RELAY1','RELAY2'):db.execute('INSERT INTO via VALUES(?,?,?,?,?)',('TEST-1',relay,STAMP,STAMP,2))
        db.commit();db.close();self.before=self.path.read_bytes()
    def test_bounds_and_base_call_metadata(self):
        result=p.list_stations(self.path,dict(buddy_only=True,limit=1))
        self.assertEqual(len(result['rows']),1);self.assertTrue(result['has_more'])
        self.assertEqual(result['rows'][0]['name'],'Test person')
        self.assertEqual(result['rows'][0]['base_call'],'TEST')
        self.assertTrue(result['rows'][0]['buddy'])
        self.assertEqual(len(p.list_stations(self.path,dict(via='relay1'))['rows']),1)
        self.assertEqual(p.list_stations(self.path,dict(offset=100))['rows'],[])
        for filters in ({'limit':501},{'offset':-1},{'limit':True},{'buddy_only':1},{'unknown':1}):
            with self.assertRaises(ValueError):p.list_stations(self.path,filters)
    def test_details_reuse_precedence_without_packet_route(self):
        detail=p.station_details(self.path,'test-1',relay_limit=1)
        self.assertEqual(detail['position'],dict(lat=47.1,lon=-122.5,stamp=STAMP,source='capture'))
        self.assertTrue(detail['relays_truncated']);self.assertEqual(len(detail['heard_through']),1)
        self.assertIsNone(detail['capture_ref']);self.assertIsNone(detail['route'])
        self.assertEqual(detail['notes'],'Shared notes');self.assertTrue(detail['lines'])
        self.assertEqual(next(e['source'] for e in detail['evidence'] if e['kind']=='service:BBS'),'legacy_text')
        self.assertEqual(p.navigation_target(detail),dict(call='TEST-1',source='directory',position=[47.1,-122.5],position_time=STAMP))
        self.assertNotIn('id',p.navigation_target(detail));json.dumps(detail)
    def test_selected_relay_with_forwarded_records_is_json_serializable(self):
        db=p.directory().database(self.path)
        db.execute('INSERT INTO stations VALUES(?,?,?,?)',('RELAY1',STAMP,STAMP,1))
        db.commit();db.close()
        detail=p.station_details(self.path,'RELAY1')
        forwarded=next(e for e in detail['evidence'] if e['kind']=='forwarded')
        self.assertEqual(json.loads(forwarded['detail']),[['TEST-1',2]])
        self.assertEqual(forwarded['source'],'aggregate')
        self.assertIn('TEST-1', '\n'.join(detail['lines']))
        self.assertIsNone(detail['route']);self.assertIsNone(detail['capture_ref'])
        json.dumps(detail)

    def test_unknown_and_no_position(self):
        self.assertIsNone(p.station_details(self.path,'MISSING'))
        self.assertEqual(p.navigation_target(p.station_details(self.path,'OTHER')),{'call':'OTHER','source':'directory'})
    def test_read_only_no_database_creation_or_mutation(self):
        p.list_stations(self.path);p.station_details(self.path,'TEST-1')
        self.assertEqual(self.path.read_bytes(),self.before)
        with p.connect(self.path) as db:
            with self.assertRaises(p.sqlite3.OperationalError):db.execute('DELETE FROM stations')
        missing=self.path.parent/'missing.db'
        with self.assertRaises(p.sqlite3.OperationalError):p.list_stations(missing)
        self.assertFalse(missing.exists())

if __name__=='__main__':unittest.main()
