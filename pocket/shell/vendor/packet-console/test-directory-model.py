"""Shared Directory model behavior without terminal or transport dependencies."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('model',HERE/'n810-directory-model.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
STAMP='2020-01-02T03:04:05+00:00'

class ModelTests(unittest.TestCase):
    def test_import_has_no_terminal_or_transport_modules(self):
        code="import runpy,sys;runpy.run_path(sys.argv[1]);assert not any(x in sys.modules for x in ('curses','socket','subprocess'))"
        subprocess.run([sys.executable,'-c',code,str(HERE/'n810-directory-model.py')],check=True)
    def test_schema_reopen_preserves_personal_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db';db=m.database(path)
            db.execute("INSERT INTO people VALUES('TEST',1,'Name','Notes')");db.commit();db.close()
            db=m.database(path)
            self.assertEqual(db.execute('SELECT * FROM people').fetchone(),('TEST',1,'Name','Notes'))
            self.assertTrue({'legacy_records','legacy_evidence','seen'} <= {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")});db.close()
    def test_evidence_precedence_and_aggregate_relay_facts(self):
        with tempfile.TemporaryDirectory() as folder:
            db=m.database(Path(folder)/'db')
            db.execute("INSERT INTO legacy_evidence VALUES('TEST','position','legacy unknown date','[1,2]')")
            db.execute('INSERT INTO evidence VALUES(?,?,?,?)',('TEST','position',STAMP,'[47,-122]'))
            db.execute('INSERT INTO via VALUES(?,?,?,?,?)',('OTHER','TEST',STAMP,STAMP,2))
            rows={k:(t,d) for k,t,d in m.station_evidence(db,'TEST')}
            self.assertEqual(rows['position'],(STAMP,'[47,-122]'))
            self.assertEqual(rows['relay_activity'][1],'1');self.assertEqual(json.loads(rows['forwarded'][1]),[['OTHER',2]])
            db.close()
    def test_compact_and_technical_details_preserve_evidence(self):
        evidence=[('position',STAMP,'[47.1,-122.5]'),('messaging',STAMP,'Messaging advertised'),('forwarded','','[]'),('service:BBS',STAMP,'BBS mention')]
        args=('TEST-1','Person',True,STAMP,3,evidence,[('RELAY',2,STAMP)],'Personal note',60)
        compact='\n'.join(m.station_details(*args));technical='\n'.join(m.station_details(*args,technical=True))
        for text in (compact,technical):
            for expected in ('TEST-1','Person','RELAY','BBS mention','Personal note'):self.assertIn(expected,text)
        self.assertIn('HEARD THROUGH',compact);self.assertIn('EVIDENCE / CAPTURE TIMES (UTC)',technical)
        self.assertEqual(m.age('legacy unknown date'),'older text')

if __name__=='__main__':unittest.main()
