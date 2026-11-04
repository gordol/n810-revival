import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('radio_source',Path(__file__).with_name('radio-snapshot-source.py'))
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


class Tests(unittest.TestCase):
    def test_single_output_lock_reuses_same_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);output=root/'state.json';access=root/'access.json'
            owner=s.acquire(output,access)
            try:
                self.assertIsNone(s.acquire(output,access))
                with self.assertRaises(ValueError):s.acquire(output,root/'other.json')
                self.assertEqual(output.with_name('state.json.producer.lock').stat().st_mode&0o777,0o600)
            finally:owner.close()
            next_owner=s.acquire(output,access);self.assertIsNotNone(next_owner);next_owner.close()

    def test_nested_duplicate_cli_exits_before_config_or_network(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);access=root/'access.json';output=root/'state.json'
            access.write_text('{"cookie":"test-secret-never-output"}');access.chmod(0o600)
            output.write_text('{"live":{"captured":"old"}}');old=output.read_bytes()
            owner=s.acquire(output,access)
            try:
                child=subprocess.run([sys.executable,str(Path(__file__).with_name('radio-snapshot-source.py')),'--access',str(access),'--output',str(output),'--watch'],capture_output=True,text=True,timeout=5)
                self.assertEqual(child.returncode,0);self.assertEqual(json.loads(child.stdout),{'producer':'reused'})
                self.assertNotIn('test-secret',child.stdout+child.stderr);self.assertEqual(output.read_bytes(),old)
            finally:owner.close()

    def test_first_fetch_outage_preserves_existing_observations(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);access=root/'access.json';output=root/'state.json'
            access.write_text(json.dumps(dict(origin='https://localhost:1',certificate='unused',cookie='test-secret')));access.chmod(0o600)
            old=dict(catalog={'data':{'captured':'old-catalog','radio_snapshot':{'banks':[{'index':0}]}}},live={'data':{'captured':'old-live','radio_live':{'heartbeat':123}}},connector={'ssh':{'success':True,'observed_at':123}})
            output.write_text(json.dumps(old));output.chmod(0o600)
            stdout=io.StringIO()
            with patch.object(sys,'argv',['source','--access',str(access),'--output',str(output)]),patch.object(s.ssl,'create_default_context',return_value=object()),patch.object(s.urllib.request,'urlopen',side_effect=OSError('offline')),patch.object(s.signal,'signal'),contextlib.redirect_stdout(stdout):
                self.assertEqual(s.main(),0)
            result=json.loads(output.read_text())
            self.assertEqual(result['catalog']['data'],old['catalog']['data'])
            self.assertEqual(result['live']['data'],old['live']['data'])
            self.assertEqual(result['connector'],old['connector'])
            self.assertIn('retained',result['live']['error'])
            self.assertNotIn('test-secret',stdout.getvalue())
            self.assertEqual(output.stat().st_mode&0o777,0o600)

    def test_unchanged_payload_does_not_refresh_mtime(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json';payload={'live':{'data':{'captured':'old'}}}
            self.assertTrue(s.save(path,payload));before=path.stat().st_mtime_ns
            self.assertFalse(s.save(path,payload));self.assertEqual(path.stat().st_mtime_ns,before)

    def test_corrupt_or_non_object_seed_is_not_a_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json'
            for value in ('broken','[]','null'):
                path.write_text(value);self.assertEqual(s.load_retained(path),{})


if __name__=='__main__':unittest.main()
