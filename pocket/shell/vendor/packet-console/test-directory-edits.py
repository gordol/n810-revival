"""Two-client Directory edit serialization and conflict behavior."""
import concurrent.futures
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('model',Path(__file__).with_name('n810-directory-model.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class EditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'db';self.a=m.database(self.path);self.b=sqlite3.connect(self.path,timeout=.02)
        self.addCleanup(self.a.close);self.addCleanup(self.b.close)
        self.a.execute("INSERT INTO stations VALUES('TEST-1','old','new',7)")
        self.a.execute("INSERT INTO evidence VALUES('TEST-1','role','date','BBS')");self.a.commit()
    def test_old_toggle_behavior_and_base_call(self):
        self.assertTrue(m.toggle_buddy(self.a,'test-1')['person']['buddy'])
        self.assertFalse(m.toggle_buddy(self.b,'TEST-2')['person']['buddy'])
        self.assertEqual(self.a.execute('SELECT call,buddy FROM people').fetchone(),('TEST',0))
    def test_distinct_fields_merge_without_losing_evidence(self):
        old=m.get_person(self.a,'TEST')
        self.assertEqual(m.edit_person(self.a,'TEST',{'name':'Alice'},{'name':old['name']})['status'],'applied')
        result=m.edit_person(self.b,'TEST',{'notes':'Field notes'},{'notes':old['notes']})
        self.assertEqual(result['person']['name'],'Alice');self.assertEqual(result['person']['notes'],'Field notes')
        self.assertEqual(self.a.execute('SELECT * FROM stations').fetchone(),('TEST-1','old','new',7))
        self.assertEqual(self.a.execute('SELECT * FROM evidence').fetchone(),('TEST-1','role','date','BBS'))
    def test_stale_same_field_conflict_and_safe_repeated_set(self):
        m.edit_person(self.a,'TEST',{'name':'Alice'},{'name':''})
        self.assertEqual(m.edit_person(self.b,'TEST',{'name':'Bob'},{'name':''})['status'],'conflict')
        self.assertEqual(m.edit_person(self.b,'TEST',{'name':'Alice'},{'name':''})['status'],'unchanged')
        self.assertEqual(m.get_person(self.b,'TEST')['name'],'Alice')
    def test_invalid_edits_do_not_create_person(self):
        for changes in ({},{'buddy':1},{'name':'x'*121},{'notes':'x'*4097},{'notes':'bad\0text'},{'packets':0}):
            self.assertEqual(m.edit_person(self.a,'TEST',changes)['status'],'invalid')
        self.assertEqual(m.edit_person(self.a,'bad;sql',{'name':'A'})['status'],'invalid')
        self.assertEqual(m.edit_person(self.a,'TEST',{'name':'A'},{'notes':''})['status'],'invalid')
        self.assertEqual(self.a.execute('SELECT count(*) FROM people').fetchone()[0],0)
    def test_busy_and_existing_transaction_are_not_committed(self):
        self.a.execute('BEGIN IMMEDIATE')
        self.assertEqual(m.toggle_buddy(self.b,'TEST')['status'],'busy')
        self.assertEqual(m.toggle_buddy(self.a,'TEST')['status'],'error')
        self.assertTrue(self.a.in_transaction);self.a.rollback()
    def test_concurrent_toggle_actions_both_apply(self):
        def action(_):
            db=sqlite3.connect(self.path,timeout=1)
            try:return m.toggle_buddy(db,'TEST')['status']
            finally:db.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(action,range(2))),['applied','applied'])
        self.assertFalse(m.get_person(self.a,'TEST')['buddy'])
    def test_optional_expected_is_not_version_protection(self):
        m.edit_person(self.a,'TEST',{'name':'Alice'})
        result=m.edit_person(self.b,'TEST',{'name':'Bob'})
        self.assertEqual(result['status'],'applied');self.assertEqual(result['person']['name'],'Bob')

if __name__=='__main__':unittest.main()
