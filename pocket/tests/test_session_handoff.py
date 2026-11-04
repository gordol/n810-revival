"""A started radio hands state over through its existing subscription."""
import os,sys,tempfile,unittest,socket
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum'))
import session_owner as session

class HandoffTests(unittest.TestCase):
    def test_handoff_restores_only_explicit_controls_without_replaying_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner=session.SessionOwner(tmp,'test','radio','usb','/dev/null',2,2)
            grant=dict(peer='ab'*16,expected_public_key='12'*64,service='reticulum',operations=['snapshot'])
            try:
                owner.phase='online'
                with patch.object(session,'exchange',return_value=dict(version=1)):
                    for action,payload in [('service_share',grant),('service_discovery',dict(enabled=True)),('message_discovery',dict(enabled=True)),('send',dict(peer=grant['peer'],text='never replay'))]:
                        owner.dispatch(dict(version=1,action=action,payload=payload))
                owner.phase='opening'
                with patch.object(session,'exchange',return_value=dict(version=1)) as exchange:
                    owner._restore_controls(owner.generation)
                requests=[call.args[1] for call in exchange.call_args_list]
                self.assertEqual([r['action'] for r in requests],['service_share','service_discovery','message_discovery'])
                self.assertEqual(requests[0]['payload'],grant)
                owner.drain();self.assertEqual(owner.phase,'online')
            finally:owner.close()

    def test_revocation_and_explicit_disconnect_clear_sharing_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner=session.SessionOwner(tmp,'test','radio','usb','/dev/null',2,2)
            grant=dict(peer='ab'*16,expected_public_key='12'*64,service='reticulum',operations=['snapshot'])
            try:
                owner._remember_control('service_share',grant,dict(version=1))
                owner._remember_control('service_discovery',dict(enabled=True),dict(version=1))
                owner._remember_control('revoke_peer',dict(peer=grant['peer']),dict(version=1))
                self.assertFalse(owner.runtime_controls)
                owner._remember_control('service_share',grant,dict(version=1,error='not authorized'))
                self.assertFalse(owner.runtime_controls)
                owner._remember_control('service_share',grant,dict(version=1))
                owner.phase='online'
                with patch.object(session.threading,'Thread'):
                    owner.dispatch(dict(version=1,action='disconnect',request_id='explicit',payload=dict(station='test',radio='radio')))
                self.assertFalse(owner.runtime_controls)
            finally:owner.close()

    def test_refused_sharing_restore_does_not_report_online(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner=session.SessionOwner(tmp,'test','radio','usb','/dev/null',2,2)
            try:
                owner._remember_control('service_share',dict(peer='ab'*16,expected_public_key='12'*64,service='reticulum',operations=['snapshot']),dict(version=1))
                owner.phase='opening'
                with patch.object(session,'exchange',return_value=dict(version=1,error='Verify the selected peer fingerprint first')):
                    owner._restore_controls(owner.generation)
                owner.drain();self.assertEqual(owner.phase,'error')
                self.assertIn('Cannot restore sharing',owner.error)
            finally:owner.close()

    def run_start(self,response):
        with tempfile.TemporaryDirectory() as tmp:
            owner=session.SessionOwner(tmp,'test','radio','usb','/dev/null',2,2)
            profile=dict(id='test',label='Test',frequency=912345000,bandwidth=500000,txpower=2,spreadingfactor=7,codingrate=5)
            owner.store.commit({'test':profile},'test')
            request=dict(version=1,action='connect',request_id='connect',payload=dict(station='test',radio='radio'))
            def spawn(command,**kwargs):
                os.write(kwargs['pass_fds'][0],b'R')
                return SimpleNamespace(poll=lambda:0,returncode=0)
            try:
                with patch.dict(os.environ,POCKET_RNS_LIBRARY='stock'),patch.object(session.subprocess,'Popen',side_effect=spawn),patch.object(session,'exchange',return_value=response) as exchange,patch.object(session,'SessionEvents') as events:
                    owner._start(request,owner.generation)
                    exchange.assert_called_once_with(owner.worker_socket,request)
                    if response.get('error'):
                        events.assert_not_called();owner.drain()
                        self.assertEqual(owner.phase,'error')
                    else:
                        events.assert_called_once_with(owner.worker_socket,owner,owner.generation)
                        self.assertIs(owner.reader,events.return_value)
            finally:owner.child=None;owner.reader=None;owner.close()
    def test_success_uses_initial_subscription_snapshot(self):
        self.run_start(dict(version=1,job=dict(state='complete')))
    def test_explicit_connect_error_is_not_ignored(self):
        self.run_start(dict(version=1,error='Radio failed'))

class SessionEndpointTests(unittest.TestCase):
    def test_known_dead_session_is_reaped_without_touching_unknown_endpoint(self):
        from local_owner import EndpointReceipt
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'owner.sock';receipt=EndpointReceipt(path,dict(service='session',station='test'))
            with socket.socket(socket.AF_UNIX) as listener:listener.bind(str(path));path.chmod(0o600);receipt.record(path.lstat())
            receipt.remove_stale();self.assertFalse(path.exists())
            with socket.socket(socket.AF_UNIX) as listener:listener.bind(str(path));path.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'Unrecognized'):receipt.remove_stale()
            self.assertTrue(path.exists())
    def test_live_or_locked_session_is_never_reaped(self):
        from local_owner import EndpointReceipt
        from owner import private_lock
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'owner.sock';receipt=EndpointReceipt(path,dict(service='session',station='test'))
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(path));listener.listen(2);path.chmod(0o600);receipt.record(path.lstat())
                with self.assertRaisesRegex(OSError,'still listening'):receipt.remove_stale()
                self.assertTrue(path.exists())
            with private_lock(path.with_suffix('.lifetime.lock'),blocking=False):
                with self.assertRaisesRegex(OSError,'lifetime lock'):receipt.remove_stale()
                self.assertTrue(path.exists())
            receipt.remove_stale();self.assertFalse(path.exists())

if __name__=='__main__':unittest.main()
