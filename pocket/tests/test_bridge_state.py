"""Binary bridge metadata must reuse existing masters and retain ownership guards."""
from pathlib import Path
import json,os,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import receive_bridge as bridge
from runtime_codec import unpack
class BridgeStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/tmp',prefix='bridge-state-');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700);self.config=bridge._configuration('user@host','/tmp/key')
    def test_binary_writes_and_reads_from_legacy_path_alias(self):
        path=self.root/'services.json';bridge._write(path,{'system':'/tmp/service'})
        self.assertFalse(path.exists());self.assertEqual(unpack(path.with_suffix('.msgpack').read_bytes()),{'system':'/tmp/service'})
        self.assertEqual(bridge._read(path),{'system':'/tmp/service'})
        self.assertEqual(path.with_suffix('.msgpack').stat().st_mode&0o777,0o600)
    def test_existing_legacy_master_is_reused_under_same_lock(self):
        directory=self.root/'b-012345abcdef';directory.mkdir(mode=0o700)
        record=dict(config=self.config,directory=str(directory),token='saved-token')
        registry=self.root/'0123456789abcdef.json';owner=directory/'owner.json'
        for path in (registry,owner):path.write_text(json.dumps(record));path.chmod(0o600)
        original=registry.read_bytes()
        with patch.object(bridge,'_master',return_value=True),patch.object(bridge,'_ready',return_value=True),patch.object(bridge,'_run',side_effect=AssertionError('Must not open another SSH master')):
            self.assertEqual(bridge.ensure('user@host','/tmp/key',self.root),directory)
        self.assertEqual(registry.read_bytes(),original)
        self.assertEqual(bridge._read(registry),record)
        self.assertTrue(registry.with_suffix('.msgpack').is_file())
        self.assertEqual(bridge._paths(self.config,self.root)[2],registry.with_suffix('.lock'))
        with patch.object(bridge,'_master',return_value=False):self.assertTrue(bridge.stop('user@host','/tmp/key',self.root))
        self.assertFalse(directory.exists());self.assertFalse(registry.exists());self.assertFalse(registry.with_suffix('.msgpack').exists())
    def test_device_attachment_does_not_wait_for_radio_endpoints(self):
        root,record_path,_=bridge._paths(self.config,self.root)
        directory=root/'b-001122334455';directory.mkdir(mode=0o700)
        record=dict(config=self.config,directory=str(directory),token='saved-token')
        bridge._write(directory/'owner.msgpack',record);bridge._write(record_path,record)
        with patch.object(bridge,'_master',return_value=True),patch.object(bridge,'_ready',side_effect=AssertionError('Radio readiness must not gate device SSH')):
            self.assertEqual(bridge.ensure('user@host','/tmp/key',self.root,require_receive=False),directory)

    def test_ssh_budget_is_configurable_and_covers_handshake_not_ui_startup(self):
        from types import SimpleNamespace
        failure=SimpleNamespace(returncode=255,stderr=b'fixture failure')
        with patch.dict(os.environ,POCKET_SSH_CONNECT_TIMEOUT='17'),patch.object(bridge,'_run',return_value=failure) as run,self.assertRaises(bridge.BridgeError):
            bridge.ensure('user@host','/tmp/key',self.root,require_receive=False)
        command,timeout=run.call_args.args
        self.assertIn('ConnectTimeout=17',command);self.assertEqual(timeout,21)

    def test_ssh_banner_timeout_is_not_reported_as_a_radio_or_key_failure(self):
        from types import SimpleNamespace
        failure=SimpleNamespace(returncode=255,stderr=b'Connection timed out during banner exchange')
        with patch.object(bridge,'_run',return_value=failure),self.assertRaises(bridge.BridgeError) as caught:
            bridge.ensure_preferred('user@host','/tmp/key',self.root,require_receive=False)
        message=str(caught.exception)
        self.assertTrue(message.startswith('SSH device connection failed.'))
        self.assertIn('SSH did not respond before the timeout',message)
        self.assertNotIn('Check SSH host/key',message)
        self.assertNotIn('No receive connection',message)

    def test_unsafe_or_symlinked_records_are_rejected(self):
        target=self.root/'data';target.write_bytes(b'x');path=self.root/'owner.msgpack';path.symlink_to(target)
        with self.assertRaises(bridge.BridgeError):bridge._read(path)
        path.unlink();bridge._write(path,{'a':1});path.chmod(0o666)
        with self.assertRaises(bridge.BridgeError):bridge._read(path)
    def test_unrelated_broken_record_cannot_block_a_new_connection(self):
        bad=self.root/'1111111111111111.json';bad.write_bytes(b'broken');bad.chmod(0o600)
        root,path,lock=bridge._paths(self.config,self.root)
        self.assertEqual(root,self.root);self.assertEqual(path.suffix,'.msgpack')
        self.assertEqual(bad.read_bytes(),b'broken')

    def test_binary_record_takes_precedence_over_legacy(self):
        old=self.root/'services.json';old.write_text('{"old":true}');old.chmod(0o600)
        bridge._write(old,{'current':True});self.assertEqual(bridge._read(old),{'current':True})
if __name__=='__main__':unittest.main()
