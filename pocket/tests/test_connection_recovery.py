"""Explicit connection intent survives restart; cold preparation remains cancellable."""
import os,signal,stat,subprocess,sys,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum'))
from owner import Owner
from owner import exchange,serve
import session_owner as session

class Radio(Owner):
    def __init__(self,state,target='radio-a',reset=False):
        super().__init__(state,'fixture');self.phase='idle';self.calls=[]
        self.configure_connection_recovery(lambda:dict(device=target),{},reset_error=reset)
    def dispatch(self,request):
        action=request['action'];self.calls.append(action)
        self.connection_requested(action=='connect')
        self.phase='opening' if action=='connect' else 'closing'
    def close(self):self.stop_connection_recovery()

class RecoveryTests(unittest.TestCase):
    def test_real_listener_resumes_on_restart_and_explicit_disconnect_stays_off(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as root:
            endpoint=Path(root)/'owner.sock';child=None
            def start():
                process=subprocess.Popen([sys.executable,__file__,'--serve-fixture',str(endpoint),root],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                deadline=time.monotonic()+5
                while not endpoint.exists():
                    if process.poll() is not None:self.fail(process.stderr.read().decode())
                    if time.monotonic()>deadline:process.terminate();process.wait();self.fail('Listener not ready')
                    time.sleep(.01)
                return process
            def stop(process):
                process.terminate();process.wait(timeout=5);process.stderr.close()
            try:
                child=start()
                self.assertEqual(exchange(endpoint,dict(version=1,action='snapshot'))['connection_state'],'idle')
                exchange(endpoint,dict(version=1,action='connect'));stop(child)
                child=start()
                self.assertEqual(exchange(endpoint,dict(version=1,action='snapshot'))['connection_state'],'online')
                exchange(endpoint,dict(version=1,action='disconnect'));stop(child)
                child=start()
                self.assertEqual(exchange(endpoint,dict(version=1,action='snapshot'))['connection_state'],'idle')
            finally:
                if child is not None and child.poll() is None:stop(child)

    def test_only_explicit_connection_is_restored_and_disconnect_persists(self):
        with tempfile.TemporaryDirectory() as root:
            first=Radio(root);first.recover_connection();self.assertEqual(first.calls,[])
            first.dispatch(dict(action='connect'));first.close()
            second=Radio(root);second.recover_connection();second.recover_connection()
            self.assertEqual(second.calls,['connect'])
            second.phase='online';second.dispatch(dict(action='disconnect'));second.close()
            third=Radio(root);third.recover_connection();self.assertEqual(third.calls,[]);third.close()

    def test_changed_target_does_not_inherit_permission_to_connect(self):
        with tempfile.TemporaryDirectory() as root:
            first=Radio(root);first.connection_requested(True);first.close()
            second=Radio(root,'radio-b');second.recover_connection();self.assertEqual(second.calls,[]);second.close()

    def test_failed_session_cleans_up_then_retries_without_clearing_intent(self):
        with tempfile.TemporaryDirectory() as root,patch('threading.Timer') as timer,patch('owner.time.monotonic',return_value=10):
            radio=Radio(root,reset=True);radio.connection_requested(True);radio.phase='error'
            radio.recover_connection();self.assertEqual(radio.calls,[])
            self.assertEqual(timer.call_count,1)
            radio._connection_due=0;radio.recover_connection();self.assertEqual(radio.calls,['disconnect'])
            self.assertTrue(radio._connection_wanted)
            radio.phase='idle';radio.recover_connection();self.assertEqual(radio.calls,['disconnect','connect'])
            radio.connection_requested(False);self.assertFalse(radio._connection_wanted)
            self.assertTrue(timer.return_value.cancel.called);radio.close()

    def test_unsafe_intent_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            radio=Radio(root);radio.connection_requested(True);radio.close()
            (Path(root)/'connection.msgpack').chmod(0o644)
            with self.assertRaisesRegex(ValueError,'Unsafe'):Radio(root)

class PreparationTests(unittest.TestCase):
    def prepare(self,communicate,cancel=None):
        owner=SimpleNamespace(cancel=cancel or threading.Event(),startup_timeout=60)
        helper=Mock();helper.exists.return_value=True
        helper.lstat.return_value=SimpleNamespace(st_mode=stat.S_IFREG|0o755,st_uid=0)
        process=Mock();process.returncode=0;process.poll.return_value=0;process.communicate.side_effect=communicate
        with patch.object(session,'Path',return_value=helper),patch.object(session.subprocess,'Popen',return_value=process):
            session.SessionOwner._prepare_bluetooth(owner)
        return process

    def test_cold_helper_can_take_more_than_old_thirty_second_limit(self):
        clock=[0.]
        def communicate(timeout):
            clock[0]+=.25
            if clock[0]<=35:raise session.subprocess.TimeoutExpired('prepare',timeout)
            return b'{"ok":true}',b''
        with patch.object(session.time,'monotonic',side_effect=lambda:clock[0]):self.prepare(communicate)
        self.assertGreater(clock[0],30)

    def test_cancel_terminates_preparation_instead_of_waiting_for_deadline(self):
        cancel=threading.Event();owner=SimpleNamespace(cancel=cancel,startup_timeout=60)
        helper=Mock();helper.exists.return_value=True;helper.lstat.return_value=SimpleNamespace(st_mode=stat.S_IFREG|0o755,st_uid=0)
        process=Mock();process.poll.side_effect=[None,None]
        def communicate(timeout):
            cancel.set();raise session.subprocess.TimeoutExpired('prepare',timeout)
        process.communicate.side_effect=communicate
        with patch.object(session,'Path',return_value=helper),patch.object(session.subprocess,'Popen',return_value=process):
            with self.assertRaises(InterruptedError):session.SessionOwner._prepare_bluetooth(owner)
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)

    def test_unsuccessful_helper_response_is_not_treated_as_ready(self):
        with self.assertRaisesRegex(ValueError,'failed'):self.prepare(lambda **kw:(b'{"ok":false}',b''))

if __name__=='__main__':
    if len(sys.argv)==4 and sys.argv[1]=='--serve-fixture':
        class FixtureRadio(Radio):
            def snapshot(self):return dict(version=1,owner_online=True,connection_state=self.phase,capabilities=['connect','disconnect'])
            def dispatch(self,request):
                if request['action']=='snapshot':return self.snapshot()
                super().dispatch(request)
                self.phase='online' if request['action']=='connect' else 'idle'
                return dict(version=1)
        signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
        serve(sys.argv[2],sys.argv[3],'fixture',lambda state,station:FixtureRadio(state))
    else:unittest.main()
