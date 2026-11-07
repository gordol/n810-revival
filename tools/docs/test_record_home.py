"""Check the privacy boundary of the documentation recording inputs."""
from contextlib import closing
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from record_home import club_copy, station_copy


class RecordingInputs(unittest.TestCase):
    def test_station_copy_excludes_identity_variants_and_private_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.sqlite'
            target = Path(directory) / 'capture.sqlite'
            with closing(sqlite3.connect(source)) as db, db:
                db.execute('CREATE TABLE stations(call TEXT, first REAL, last REAL, packets INTEGER)')
                db.execute('CREATE TABLE evidence(call TEXT, kind TEXT, stamp REAL, detail TEXT)')
                db.executemany('INSERT INTO stations VALUES(?,?,?,?)', [
                    ('DEMO1', 1, 2, 3), ('DEMO1-7', 1, 3, 4), ('DEMO2', 1, 4, 5)])
                db.executemany('INSERT INTO evidence VALUES(?,?,?,?)', [
                    ('DEMO1-7', 'position', 3, 'private position'),
                    ('DEMO2', 'position', 4, 'public position'),
                    ('DEMO2', 'role', 4, 'Relayed by demo1-7'),
                    ('DEMO2', 'message', 4, 'private message'),
                    ('DEMO2', 'person', 4, 'private name')])
            original = hashlib.sha256(source.read_bytes()).digest()
            result = station_copy(source, target, {'DEMO1'})
            self.assertEqual(result, {'stations': 1, 'latest_report': 4})
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(db.execute('SELECT call FROM stations').fetchall(), [('DEMO2',)])
                self.assertEqual(db.execute('SELECT kind,detail FROM evidence').fetchall(),
                                 [('position', 'public position')])
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), original)

    def test_club_copy_keeps_only_the_selected_public_club(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'fcc.sqlite'
            target = Path(directory) / 'club.sqlite'
            with closing(sqlite3.connect(source)) as db, db:
                db.execute('CREATE TABLE stations(callsign TEXT, name TEXT)')
                db.execute('CREATE TABLE license_details(callsign TEXT, status TEXT)')
                db.execute('CREATE TABLE fcc_meta(key TEXT, value TEXT)')
                db.executemany('INSERT INTO stations VALUES(?,?)',
                               [('DEMO2', 'EXAMPLE RADIO CLUB'), ('DEMO1', 'A PERSON')])
                db.executemany('INSERT INTO license_details VALUES(?,?)', [('DEMO2', 'A'), ('DEMO1', 'A')])
                db.executemany('INSERT INTO fcc_meta VALUES(?,?)',
                               [('source_data_date', '2026-11-01'), ('local_path', 'private input')])
            original = hashlib.sha256(source.read_bytes()).digest()
            club_copy(source, target, 'DEMO2')
            with closing(sqlite3.connect(target)) as db:
                self.assertEqual(db.execute('SELECT * FROM stations').fetchall(), [('DEMO2', 'EXAMPLE RADIO CLUB')])
                self.assertEqual(db.execute('SELECT * FROM license_details').fetchall(), [('DEMO2', 'A')])
                self.assertEqual(db.execute('SELECT * FROM fcc_meta').fetchall(), [('source_data_date', '2026-11-01')])
            with self.assertRaises(ValueError):
                club_copy(source, Path(directory) / 'person.sqlite', 'DEMO1')
            self.assertEqual(hashlib.sha256(source.read_bytes()).digest(), original)


if __name__ == '__main__':
    unittest.main()
