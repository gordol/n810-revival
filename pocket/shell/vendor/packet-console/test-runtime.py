"""Portable runtime handoffs, atomic private writes and visible Directory failures."""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

r=module('runtime','n810-runtime.py')

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.root.chmod(0o700)
        p=patch.dict(os.environ,N810_RUNTIME_DIR=str(self.root));p.start();self.addCleanup(p.stop)
    def test_private_override_roundtrip_and_names(self):
        for name in ('n810-map-request.json','n810-message-request.json','n810-directory-request.json'):
            value={'call':'TEST-1','id':17};path=r.write_json(name,value)
            self.assertEqual(path,self.root/name);self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(r.read_json(name),value)
        self.assertEqual(len(list(self.root.iterdir())),3)
    def test_default_path_is_unchanged_without_creating_it(self):
        with patch.dict(os.environ,N810_RUNTIME_DIR=''),patch.object(Path,'lstat',return_value=os.stat(self.root)):
            self.assertEqual(r.runtime_path('n810-map-request.json'),Path('/dev/shm/n810-map-request.json'))
    def test_missing_unsafe_relative_and_symlink_roots(self):
        for root in (self.root/'missing',Path('relative')):
            with patch.dict(os.environ,N810_RUNTIME_DIR=str(root)):
                with self.assertRaises((OSError,ValueError)):r.write_json('request.json',{})
        self.assertFalse((self.root/'missing').exists())
        bad=self.root/'unsafe';bad.mkdir(mode=0o755);bad.chmod(0o755)
        link=self.root/'link';link.symlink_to(self.root,target_is_directory=True)
        for root in (bad,link):
            with patch.dict(os.environ,N810_RUNTIME_DIR=str(root)):
                with self.assertRaises(OSError):r.runtime_path('request.json')
    def test_basename_and_reader_validation(self):
        for name in ('','../escape','/tmp/escape','..'):
            with self.assertRaises(ValueError):r.runtime_path(name)
        public=self.root/'request.json';public.write_text('{}');public.chmod(0o644)
        with self.assertRaises(OSError):r.read_json('request.json')
        public.chmod(0o600);public.write_text('{')
        with self.assertRaises(ValueError):r.read_json('request.json')
        link=self.root/'link.json';link.symlink_to(public)
        with self.assertRaises(OSError):r.read_json('link.json')
    def test_atomic_collision_safe_and_failure_preserves_old_value(self):
        name='n810-map-request.json';r.write_json(name,{'old':True})
        with patch.object(r.os,'replace',side_effect=OSError('replace denied')):
            with self.assertRaises(OSError):r.write_json(name,{'new':True})
        self.assertEqual(r.read_json(name),{'old':True})
        self.assertEqual(list(self.root.iterdir()),[self.root/name])
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i:r.write_json(name,{'id':i,'text':'x'*1000}),range(20)))
        result=r.read_json(name);self.assertIn(result['id'],range(20));self.assertEqual(result['text'],'x'*1000)
        self.assertEqual(len(list(self.root.iterdir())),1)
    def test_size_limit(self):
        with self.assertRaises(ValueError):r.write_json('big.json',{'text':'x'*r.LIMIT})
    def test_directory_missing_runtime_reports_navigation_failure(self):
        d=module('directory_runtime_test','n810-aprs-directory.py')
        db=self.root/'directory.sqlite3';conn=d.database(db)
        conn.execute("INSERT INTO stations VALUES('TEST','2020-01-01T00:00:00+00:00','2020-01-01T00:00:00+00:00',1)");conn.commit();conn.close()
        class Screen:
            def __init__(self,key):self.keys=iter([ord(key),ord('q')]);self.text=[]
            def keypad(self,*a):pass
            def timeout(self,*a):pass
            def getmaxyx(self):return 40,133
            def erase(self):pass
            def refresh(self):pass
            def addnstr(self,y,x,text,*a):self.text.append(text)
            def getch(self):return next(self.keys)
        args=type('Args',(),{'db':str(db)})()
        for key in ('v','m'):
            screen=Screen(key)
            with patch.dict(os.environ,N810_RUNTIME_DIR=str(self.root/'absent')),patch.object(d.curses,'curs_set'),patch.object(d,'ui_state',SimpleNamespace(load=lambda *a:{},save=lambda *a:None),create=True),patch.object(d,'visibility',SimpleNamespace(visible=lambda:True),create=True):
                d.display(screen,args)
            self.assertTrue(any('Navigation failed:' in text for text in screen.text),screen.text[-5:])

if __name__=='__main__':unittest.main()
