"""Fixture-only launcher parity, diagnostics and stopped-session upgrade checks."""
import ast
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


entry = load('nokia_session_entry', ROOT/'platform/n810/session_entry.py')
upgrade = load('nokia_session_upgrade', ROOT/'platform/n810/upgrade_session.py')
trusted_path = upgrade.trusted


class SessionTests(unittest.TestCase):
    def test_command_matches_original_supervisor_function(self):
        # Compile only command(), without initializing the privileged supervisor.
        source = ROOT/'tests/fixtures/nokia_session/original_command.py'
        tree = ast.parse(source.read_text())
        command = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'command')
        namespace = dict(os=os, stat=stat, ASSETS=entry.ASSETS)
        exec(compile(ast.Module(body=[command], type_ignores=[]),str(source),'exec'),namespace)
        for value in (None, '9'):
            env = {} if value is None else {'N810_KEYBOARD_FD':value}
            with patch.dict(os.environ,env,clear=True), patch.object(os,'fstat',return_value=SimpleNamespace(st_mode=stat.S_IFCHR,st_rdev=os.makedev(13,64))):
                self.assertEqual(entry.command(),namespace['command']())

    def test_default_launch_keeps_native_touch_and_local_services(self):
        with patch.dict(os.environ,{},clear=True): argv=entry.command()
        self.assertEqual(argv[:3],['/usr/bin/python3','-I','/usr/local/share/n810-pocket/demo.py'])
        for arg in ('--device-radio','--native-stations','--station-db','--touch-device','--touch-calibration','--touch-display','--touch-rotation'):
            self.assertIn(arg,argv)
        self.assertNotIn('--no-local-services',argv)

    def test_keyboard_bounds_types_and_device_identity(self):
        for value in ('','2','65536','abc','９',' 9','+9','9\n','-9'):
            with self.subTest(value=value), patch.dict(os.environ,{'N810_KEYBOARD_FD':value},clear=True):
                with self.assertRaises(ValueError): entry.command()
        for major,minor in ((13,63),(13,256),(1,64)):
            with patch.dict(os.environ,{'N810_KEYBOARD_FD':'9'},clear=True),patch.object(os,'fstat',return_value=SimpleNamespace(st_mode=stat.S_IFCHR,st_rdev=os.makedev(major,minor))):
                with self.assertRaises(ValueError): entry.command()
        with patch.dict(os.environ,{'N810_KEYBOARD_FD':'9'},clear=True),patch.object(os,'fstat',return_value=SimpleNamespace(st_mode=stat.S_IFREG,st_rdev=0)):
            with self.assertRaises(ValueError): entry.command()
        for fd,minor in ((3,64),(65535,255)):
            with patch.dict(os.environ,{'N810_KEYBOARD_FD':str(fd)},clear=True),patch.object(os,'fstat',return_value=SimpleNamespace(st_mode=stat.S_IFCHR,st_rdev=os.makedev(13,minor))):
                self.assertEqual(entry.command()[-2:],['--keyboard-fd',str(fd)])
        with patch.dict(os.environ,{'N810_KEYBOARD_FD':'9'},clear=True),patch.object(os,'fstat',side_effect=OSError('closed')):
            with self.assertRaises(OSError): entry.command()

    def test_root_and_arguments_rejected_before_launch(self):
        with patch.object(entry.os,'geteuid',return_value=0),self.assertRaises(SystemExit): entry.main()
        with patch.object(entry.os,'geteuid',return_value=1000),patch.object(entry.sys,'argv',['entry','extra']),self.assertRaises(SystemExit): entry.main()

    def test_no_supervisor_load_and_no_import_time_launch(self):
        source=(ROOT/'platform/n810/session_entry.py').read_text()
        self.assertNotIn('console_helper',source)
        self.assertNotIn("helper['command']",source)
        self.assertIn("if __name__=='__main__':main()",source)

    def run_fixture(self, config=None, failure=None, symlink=False, config_mode=None):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root=Path(temp.name);state=root/'state';state.mkdir()
        assets=root/'assets';assets.mkdir();(assets/'build-info.json').write_text('{"artifact_sha256":"fixture"}')
        if config is not None:
            (state/'diagnostics.json').write_bytes(config)
            if config_mode is not None:(state/'diagnostics.json').chmod(config_mode)
        if symlink:
            (state/'diagnostics.json').symlink_to(assets/'build-info.json')
        original_path=Path
        def fixture_path(value):
            if value=='/home/nokia/.local/state/current-world':return state
            if value=='/usr/local/share/n810-pocket/build-info.json':return assets/'build-info.json'
            return original_path(value)
        seen=[]
        def launch(path,run_name):
            seen.append((path,run_name,list(entry.sys.argv)))
            if failure:raise failure
        with patch.object(entry,'Path',fixture_path),patch.object(entry.sys,'argv',['entry']),patch.object(entry.sys,'path',[]),patch.dict(os.environ,{},clear=True),patch.object(entry.runpy,'run_path',side_effect=launch):
            if failure:
                with self.assertRaises(type(failure)):entry.main()
            else:entry.main()
        run=next((state/'console-runs').iterdir())
        # Installed entry has literal backslash-n evidence suffix; preserve original contract.
        launch_data=json.loads((run/'launch.json').read_text().removesuffix('\\n'))
        exit_data=json.loads((run/'exit.json').read_text().removesuffix('\\n'))
        return state,run,seen,launch_data,exit_data

    def test_metrics_default_off_and_evidence(self):
        mask=os.umask(0o077);self.addCleanup(os.umask,mask)
        state,run,seen,launch_data,exit_data=self.run_fixture()
        self.assertNotIn('--metrics',seen[0][2])
        self.assertIn('--session',seen[0][2])
        self.assertEqual(launch_data['diagnostics'],dict(requested_metrics=None,effective_metrics=False))
        self.assertEqual(exit_data['exit_code'],0)
        self.assertEqual(stat.S_IMODE(run.stat().st_mode),0o700)
        self.assertEqual(len(seen),1)

    def test_explicit_metrics(self):
        mask=os.umask(0o077);self.addCleanup(os.umask,mask)
        for enabled in (True,False):
            with self.subTest(enabled=enabled):
                state,run,seen,launch_data,exit_data=self.run_fixture(json.dumps(dict(metrics=enabled)).encode())
                self.assertEqual('--metrics' in seen[0][2],enabled)
                self.assertEqual(launch_data['diagnostics']['requested_metrics'],enabled)

    def test_failure_exit_evidence(self):
        mask=os.umask(0o077);self.addCleanup(os.umask,mask)
        for failure,code in ((SystemExit(7),7),(RuntimeError('fixture'),1)):
            state,run,seen,launch_data,exit_data=self.run_fixture(failure=failure)
            self.assertEqual(exit_data['exit_code'],code)
            self.assertEqual(exit_data['error'],type(failure).__name__)
            self.assertGreaterEqual(exit_data['elapsed_seconds'],0)

    def test_writable_diagnostics_rejected(self):
        mask=os.umask(0o077);self.addCleanup(os.umask,mask)
        with self.assertRaises(SystemExit):self.run_fixture(b'{"metrics":true}',config_mode=0o666)

    def test_invalid_diagnostics_fail_closed(self):
        mask=os.umask(0o077);self.addCleanup(os.umask,mask)
        for raw in (b'{}',b'{"metrics":1}',b'{"metrics":true,"extra":0}',b'x'*1025,b'\xff'):
            with self.subTest(raw=raw[:25]),self.assertRaises(SystemExit):self.run_fixture(raw)
        with self.assertRaises(SystemExit):self.run_fixture(symlink=True)


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.entry=self.root/'entry';self.selector=self.root/'selector';self.backup=self.root/'backup'
        self.old_entry=b'original entry';self.new_entry=b'new entry'
        old_hash=upgrade.digest(self.old_entry);new_hash=upgrade.digest(self.new_entry)
        self.old_selector=('entry='+old_hash).encode();self.new_selector=('entry='+new_hash).encode()
        self.entry.write_bytes(self.old_entry);self.selector.write_bytes(self.old_selector)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        for name,value in dict(ENTRY=self.entry,SELECTOR=self.selector,BACKUP=self.backup,
             OLD_ENTRY=old_hash,NEW_ENTRY=new_hash,OLD_SELECTOR=upgrade.digest(self.old_selector),
             NEW_SELECTOR=upgrade.digest(self.new_selector)).items():
            self.stack.enter_context(patch.object(upgrade,name,value))
        # Actual ownership checks have separate tests; fixture paths are user-owned.
        self.stack.enter_context(patch.object(upgrade,'trusted'))

    def test_reviewed_capacity_selector_is_verified_without_rewriting_or_backup_changes(self):
        capacity=b'reviewed capacity selector'
        self.entry.write_bytes(self.new_entry);self.selector.write_bytes(capacity)
        self.backup.mkdir();saved=self.backup/'original';saved.write_bytes(b'preserve original backups')
        with patch.object(upgrade,'CURRENT_SELECTOR',upgrade.digest(capacity)),patch.object(upgrade,'write') as write:
            self.assertFalse(upgrade.install_files(self.new_entry))
        write.assert_not_called()
        self.assertEqual(self.entry.read_bytes(),self.new_entry)
        self.assertEqual(self.selector.read_bytes(),capacity)
        self.assertEqual(saved.read_bytes(),b'preserve original backups')

    def test_capacity_path_refuses_old_entry_or_unexpected_selector_without_writes(self):
        capacity=b'reviewed capacity selector'
        for entry,selector in ((self.old_entry,capacity),(self.new_entry,b'unexpected selector')):
            with self.subTest(entry=entry,selector=selector):
                self.entry.write_bytes(entry);self.selector.write_bytes(selector)
                with patch.object(upgrade,'CURRENT_SELECTOR',upgrade.digest(capacity)),patch.object(upgrade,'write') as write,self.assertRaisesRegex(ValueError,'Unexpected hash'):
                    upgrade.install_files(self.new_entry)
                write.assert_not_called()
                self.assertEqual(self.entry.read_bytes(),entry);self.assertEqual(self.selector.read_bytes(),selector)
                self.assertFalse(self.backup.exists())

    def test_upgrade_idempotence_preserves_original_and_modes(self):
        self.assertTrue(upgrade.install_files(self.new_entry))
        saved=(self.backup/'session_entry.py.before').read_bytes()
        self.assertEqual(saved,self.old_entry)
        self.assertEqual(self.entry.read_bytes(),self.new_entry)
        self.assertEqual(self.selector.read_bytes(),self.new_selector)
        self.assertFalse(upgrade.install_files(self.new_entry))
        self.assertEqual((self.backup/'session_entry.py.before').read_bytes(),saved)
        self.assertEqual(stat.S_IMODE(self.entry.stat().st_mode),0o755)
        self.assertEqual(stat.S_IMODE(self.selector.stat().st_mode),0o644)
        self.assertFalse(json.loads((self.backup/'receipt.json').read_text())['restarted'])

    def test_failed_second_write_rolls_back_both(self):
        real=upgrade.write
        def fail(path,raw,mode):
            if path==self.selector and raw==self.new_selector:raise OSError('fixture write failed')
            return real(path,raw,mode)
        with patch.object(upgrade,'write',side_effect=fail),self.assertRaises(OSError):upgrade.install_files(self.new_entry)
        self.assertEqual(self.entry.read_bytes(),self.old_entry)
        self.assertEqual(self.selector.read_bytes(),self.old_selector)
        self.assertEqual((self.backup/'session_entry.py.before').read_bytes(),self.old_entry)
        self.assertTrue(upgrade.install_files(self.new_entry))

    def test_resume_mixed_install_with_originals(self):
        upgrade.install_files(self.new_entry)
        self.selector.write_bytes(self.old_selector)
        self.assertTrue(upgrade.install_files(self.new_entry))
        self.assertEqual(self.selector.read_bytes(),self.new_selector)

    def test_unknown_payload_or_missing_original_refused(self):
        with self.assertRaises(ValueError):upgrade.install_files(b'unreviewed')
        self.entry.write_bytes(self.new_entry)
        (self.backup/'session_entry.py.before').unlink()
        with self.assertRaises(ValueError):upgrade.install_files(self.new_entry)

    def test_symlink_and_oversize_read_refused(self):
        link=self.root/'link';link.symlink_to(self.entry)
        with self.assertRaises(OSError):upgrade.read(link,{upgrade.OLD_ENTRY})
        self.entry.write_bytes(b'x'*(upgrade.LIMIT+1))
        with self.assertRaises(ValueError):upgrade.read(self.entry,{upgrade.digest(self.entry.read_bytes())})

    def test_status_must_be_stopped_and_restored(self):
        for status in ({'state':'running','restored':True},{'state':'stopped','restored':False}):
            with patch.object(upgrade.subprocess,'check_output',return_value=json.dumps(status)),self.assertRaises(RuntimeError):upgrade.stopped()
        with patch.object(upgrade.subprocess,'check_output',return_value='{"state":"stopped","restored":true}'):upgrade.stopped()

    def test_trust_rejects_wrong_owner_links_and_writable_paths(self):
        for mode,uid in ((stat.S_IFREG|0o644,501),(stat.S_IFLNK|0o777,0),(stat.S_IFDIR|0o777,0)):
            with patch.object(Path,'lstat',return_value=SimpleNamespace(st_mode=mode,st_uid=uid)):
                with self.assertRaises(PermissionError):trusted_path(Path('/fixture'))
        def metadata(path):
            return SimpleNamespace(st_mode=(stat.S_IFREG|0o755) if str(path)=='/fixture' else (stat.S_IFDIR|0o755),st_uid=0)
        with patch.object(Path,'lstat',metadata):trusted_path(Path('/fixture'))

    def test_real_preserved_selector_transformation_pin(self):
        original=(ROOT/'tests/fixtures/nokia_session/original_selector.py.txt').read_bytes()
        with patch.object(upgrade,'OLD_ENTRY','bb0efaa3160060c67af307133ed6e250bc670daa76c171dfca3f7411a9b6a9de'),patch.object(upgrade,'NEW_ENTRY','44810f2369cfbf8908a6a590b83e875ece59c4e5825ebe91ef8c37a5f51931f8'),patch.object(upgrade,'OLD_SELECTOR','e435f02faa766a199dc8fa6fb14a3f483894e34936e9b9942a69d1b7fe5a9e3d'),patch.object(upgrade,'NEW_SELECTOR','cb6d69e258652312702745f7e3b09c83e64873506f7e9e300d6fb833d13db270'):
            transformed=upgrade.selector_bytes(original)
            self.assertEqual(upgrade.digest(transformed),upgrade.NEW_SELECTOR)

    def test_selector_and_entry_pins_match_preserved_candidates(self):
        actual=ROOT/'platform/n810/session_entry.py'
        # Fixed source bytes are independently pinned by the release owner.
        self.assertEqual(hashlib.sha256(actual.read_bytes()).hexdigest(),'44810f2369cfbf8908a6a590b83e875ece59c4e5825ebe91ef8c37a5f51931f8')


if __name__=='__main__':unittest.main()
