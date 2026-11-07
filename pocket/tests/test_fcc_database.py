# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from fcc_database import build, lookup, status


def hd(usid, call, state='A', action='11/01/2026'):
    row = [''] * 59
    for index, value in {0:'HD', 1:str(usid), 4:call, 5:state, 6:'HA',
                         7:'01/01/2020', 8:'01/01/2030', 43:action}.items():
        row[index] = value
    return '|'.join(row)


def en(usid, name, kind='L', address='123 Example Street'):
    row = [''] * 30
    for index, value in {0:'EN',1:str(usid),5:kind,7:name,15:address,16:'Example City',17:'WA',18:'98000',
                         19:'Box 42',20:'Radio club secretary',22:'0000000000',23:'B'}.items():
        row[index] = value
    return '|'.join(row)


class FCCTests(unittest.TestCase):
    def test_import_preserves_public_mailing_address_and_license_metadata(self):
        build(self.archive(),self.database)
        row=lookup(self.database,'N0CALL')
        for key,value in dict(street_address='123 Example Street',po_box='Box 42',
                              attention_line='Radio club secretary',frn='0000000000',
                              entity_type='L',applicant_type='B').items():
            self.assertEqual(row[key],value)
        self.assertEqual(status(self.database)['schema_version'],2)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root/'directory.sqlite'

    def archive(self, headers=None, entities=None, amateur=None, missing=None):
        data = {'HD.dat':headers if headers is not None else [hd(1,'N0CALL')],
                'EN.dat':entities if entities is not None else [en(1,'Demo Operator')],
                'AM.dat':amateur if amateur is not None else ['AM|1|||N0CALL|E']}
        path = self.root/'input.zip'
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, rows in data.items():
                if name != missing:
                    item = zipfile.ZipInfo(name, (2026,11,1,9,0,0))
                    archive.writestr(item, ('\n'.join(rows)+'\n').encode('latin-1'))
        return path

    def test_real_layout_and_readonly_lookup(self):
        info = build(self.archive(), self.database)
        row = lookup(self.database, 'n0call-7')
        self.assertEqual((row['name'],row['license_class'],row['region']), ('Demo Operator','E','WA'))
        self.assertEqual((row['granted'],row['expires']), ('2020-01-01','2030-01-01'))
        self.assertEqual(info['source_data_date'], '2026-11-01')
        self.assertEqual(status(self.database)['stations'], 1)

    def test_callsign_reassignment_joins_by_license_id(self):
        archive = self.archive([hd(1,'N0CALL','C'), hd(2,'N0CALL','A')],
                               [en(1,'Previous Holder'), en(2,'Current Holder')],
                               ['AM|1|||N0CALL|G','AM|2|||N0CALL|E'])
        build(archive,self.database)
        row = lookup(self.database,'N0CALL')
        self.assertEqual((row['name'],row['license_class'],row['usid']),('Current Holder','E',2))

    def test_inactive_latest_chosen_by_date_not_archive_order(self):
        build(self.archive([hd(1,'N0CALL','E','01/01/2024'),hd(2,'N0CALL','C','01/01/2020')],
                           [en(1,'Newer'),en(2,'Older')]),self.database)
        self.assertEqual(lookup(self.database,'N0CALL')['name'],'Newer')

    def test_licensee_preferred_over_contact(self):
        build(self.archive(entities=[en(1,'Contact','C'), en(1,'Licensee','L')]),self.database)
        self.assertEqual(lookup(self.database,'N0CALL')['name'],'Licensee')

    def test_multiline_entity_does_not_drop_record(self):
        build(self.archive(entities=[en(1,'Demo\nClub')]),self.database)
        self.assertEqual(lookup(self.database,'N0CALL')['name'],'Demo Club')

    def test_blank_cancelled_callsign_counted_and_skipped(self):
        result=build(self.archive(headers=[hd(1,'N0CALL'),hd(2,'','C')]),self.database)
        self.assertEqual(result['skipped_blank_inactive_callsigns'],1)

    def test_blank_active_callsign_rejects_archive(self):
        with self.assertRaises(ValueError):
            build(self.archive(headers=[hd(1,'')]),self.database)
        self.assertFalse(self.database.exists())

    def test_bad_import_keeps_last_working_database(self):
        build(self.archive(),self.database)
        before=self.database.read_bytes()
        with self.assertRaises(ValueError):
            build(self.archive(headers=[hd(1,'N0CALL',action='not-a-date')]),self.database)
        self.assertEqual(self.database.read_bytes(),before)
        self.assertEqual(list(self.root.glob('.fcc-build-*')),[])

    def test_missing_member_does_not_publish(self):
        with self.assertRaises(KeyError):
            build(self.archive(missing='AM.dat'),self.database)
        self.assertFalse(self.database.exists())

    def test_count_and_join_coverage_must_pass(self):
        with self.assertRaises(ValueError):
            build(self.archive(),self.database,minimum_stations=2)
        with self.assertRaises(ValueError):
            build(self.archive(entities=[en(2,'Wrong License')]),self.database)

    def test_rebuild_cannot_discard_operator_notes(self):
        build(self.archive(),self.database)
        with closing(sqlite3.connect(self.database)) as conn, conn:
            conn.execute('CREATE TABLE notes(callsign TEXT, note TEXT)')
            conn.execute('INSERT INTO notes VALUES (?,?)',('N0CALL','Keep me'))
        with self.assertRaisesRegex(ValueError,'notes'):
            build(self.archive(),self.database)
        self.assertEqual(lookup(self.database,'N0CALL')['name'],'Demo Operator')


if __name__ == '__main__':
    unittest.main()
