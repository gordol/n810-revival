"""Startup failures are retried; cancellation never resurrects an attachment."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import device_services
from connections import Connections

class RecoveryTests(unittest.TestCase):
    def wait(self,predicate):
        deadline=time.monotonic()+float(os.environ.get('POCKET_STARTUP_TEST_TIMEOUT','30'))
        while not predicate():
            if time.monotonic()>deadline:self.fail('Recovery did not finish')
            time.sleep(.01)

    def test_catalogue_readiness_survives_timeouts_without_duplicate_owner(self):
        ready=dict(implementation=device_services.identity(),release=__import__('build_identity').IDENTITY['release_id'],services=[{'id':'system'}])
        process=SimpleNamespace(poll=lambda:None)
        with tempfile.TemporaryDirectory(dir='/tmp') as root, patch.object(device_services,'exchange',side_effect=[FileNotFoundError(),TimeoutError(),dict(ready,services=[]),ConnectionError("frame interrupted"),ready]), patch.object(subprocess,'Popen',return_value=process) as spawn:
            result=device_services.ensure(root,timeout=4)
            self.assertEqual(result['socket'],str(Path(root)/'owner.sock'))
            self.assertEqual(spawn.call_count,1)

    def test_verified_stale_directory_is_retired_once_before_restart(self):
        ready=dict(implementation=device_services.identity(),release=__import__('build_identity').IDENTITY['release_id'],services=[{'id':'system'}],pid=222)
        stale=dict(ready,implementation='previous',pid=111)
        process=SimpleNamespace(poll=lambda:None)
        with tempfile.TemporaryDirectory(dir='/tmp') as root,patch.object(device_services,'exchange',side_effect=[stale,stale,FileNotFoundError(),ready]),patch.object(device_services,'retire_stale') as retire,patch.object(subprocess,'Popen',return_value=process) as spawn:
            self.assertEqual(device_services.ensure(root,timeout=4)['pid'],222)
            retire.assert_called_once_with(str(Path(root)/'owner.sock'),stale,root)
            spawn.assert_called_once()

    def test_unverified_stale_directory_is_never_replaced(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as root,patch.object(device_services,'exchange',return_value=dict(implementation='previous',pid=111)),patch.object(device_services,'retire_stale',side_effect=ValueError('Cannot verify stale directory')),patch.object(subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'Cannot verify'):device_services.ensure(root,timeout=4)
            spawn.assert_not_called()

    def test_slow_existing_owner_is_not_replaced(self):
        ready=dict(implementation=device_services.identity(),release=__import__('build_identity').IDENTITY['release_id'],services=[{'id':'system'}])
        with tempfile.TemporaryDirectory(dir='/tmp') as root, patch.object(device_services,'exchange',side_effect=[BlockingIOError(11,'backlog full'),TimeoutError(),ready]), patch.object(subprocess,'Popen') as spawn:
            device_services.ensure(root,timeout=3)
            spawn.assert_not_called()

    def test_failed_child_reports_exit_without_waiting_full_deadline(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as root, patch.object(device_services,'exchange',side_effect=FileNotFoundError()), patch.object(subprocess,'Popen',return_value=SimpleNamespace(poll=lambda:1)):
            with self.assertRaisesRegex(RuntimeError,'exited'):device_services.ensure(root,timeout=30)

    def test_directory_defers_workers_until_first_response_and_closes_unstarted(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as root:
            owner=device_services.DeviceOwner(Path(root)/'state','device')
            self.assertIsNone(owner.worker)
            self.assertIsNone(owner.samples)
            self.assertEqual(owner.snapshot(directory=True)['services'][0]['state'],'ready')
            owner.close()

    def test_cli_bootstrap_reuses_interpreter_and_releases_startup_lock(self):
        import signal
        with tempfile.TemporaryDirectory(dir='/tmp') as root:
            runtime=Path(root)/'runtime'
            script="import sys;sys.path.insert(0,sys.argv[1]);from device_services import ensure,encode;sys.stdout.buffer.write(encode(ensure(sys.argv[2],inherit=True)))"
            result=subprocess.run([sys.executable,'-I','-c',script,str(device_services.ROOT),str(runtime)],capture_output=True,timeout=20,env=dict(os.environ,HOME=root))
            self.assertEqual(result.returncode,0,result.stderr)
            from wire import decode
            first=decode(result.stdout)
            try:
                second=device_services.ensure(runtime,timeout=3)
                self.assertEqual(first['pid'],second['pid'])
                self.wait(lambda:device_services.exchange(runtime/'owner.sock',dict(version=1,action='snapshot',scope='directory')).get('telemetry'))
            finally:os.kill(first['pid'],signal.SIGTERM)

    def test_slow_optional_owner_does_not_block_system_catalogue(self):
        started=threading.Event();release=threading.Event()
        options=[]
        def factory(**kwargs):
            options.append(kwargs)
            started.set();release.wait(5)
            return SimpleNamespace(snapshot=lambda:dict(owner_online=True),path='/tmp/test-owner',bind_wakeup=lambda cb:None,close=lambda:None)
        with tempfile.TemporaryDirectory(dir='/tmp') as root, patch.object(device_services,'OWNER_IDS',('reticulum',)), patch.object(device_services,'saved_owner',return_value=dict(mode='local',state=root)), patch.object(device_services,'owner_factory',return_value=factory):
            owner=device_services.DeviceOwner(Path(root)/'state','device')
            owner.response_sent()
            try:
                self.assertTrue(started.wait(3))
                self.assertIs(options[0]['availability_only'],True)
                self.wait(lambda:bool(owner.snapshot()['services']))
                snapshot=owner.snapshot()
                self.assertTrue(snapshot['services'][0]['available'])
                self.wait(lambda:bool(owner.snapshot()['telemetry']))
                self.assertFalse(next(row for row in snapshot['services'] if row['id']=='reticulum')['available'])
            finally:
                release.set();owner.close()

    def test_directory_is_immediate_while_configuration_and_telemetry_are_blocked(self):
        release=threading.Event();entered=threading.Event()
        def slow_selection(*args):
            entered.set();release.wait(5);return None
        def slow_sample(owner):release.wait(5)
        with tempfile.TemporaryDirectory(dir='/tmp') as root, patch.object(device_services,'saved_owner',side_effect=slow_selection), patch.object(device_services.DeviceOwner,'sample',slow_sample):
            owner=device_services.DeviceOwner(Path(root)/'state','device')
            owner.response_sent()
            try:
                self.assertTrue(entered.wait(2))
                rows={row['id']:row for row in owner.snapshot()['services']}
                self.assertEqual(set(rows),{'system','receive','reticulum','meshcore'})
                self.assertEqual(rows['system']['state'],'ready')
                self.assertEqual(rows['reticulum']['state'],'starting')
                self.assertEqual(rows['meshcore']['state'],'starting')
                self.assertEqual(owner.snapshot()['telemetry'],{})
                release.set()
                self.wait(lambda:next(row for row in owner.snapshot()['services'] if row['id']=='reticulum')['state']=='unavailable')
            finally:release.set();owner.close()

    def test_directory_query_does_not_read_or_encode_receive_history(self):
        class Receive:
            @property
            def state(self):raise AssertionError('Directory read touched receive history')
        owner=device_services.DeviceOwner.__new__(device_services.DeviceOwner)
        owner.receive=Receive();owner.guard=threading.RLock();owner.implementation='fixture';owner.release='test';owner.revision=0
        owner.services=[dict(id='system',available=True,state='ready'),dict(id='reticulum',available=False,state='starting')]
        owner.telemetry=dict(system=dict(observed_at=1))
        result=owner.dispatch(dict(version=1,action='snapshot',scope='directory'))
        self.assertNotIn('receive',result)
        self.assertEqual(result['services'],owner.services)
        self.assertEqual(result['telemetry'],owner.telemetry)
        with self.assertRaisesRegex(ValueError,'scope'):owner.dispatch(dict(action='snapshot',scope='unknown'))

    def test_real_catalogue_subscription_recovers_after_owner_restart(self):
        import signal
        from app_registry import Registry
        from concurrent.futures import ThreadPoolExecutor
        children=[];spawn=subprocess.Popen
        def start(*args,**kwargs):
            child=spawn(*args,**kwargs);children.append(child);return child
        with tempfile.TemporaryDirectory(dir='/tmp') as root, patch.dict(os.environ,HOME=root), patch.object(subprocess,'Popen',side_effect=start):
            runtime=Path(root)/'runtime';provider=None
            try:
                # Exercise the production readiness deadline, including cold
                # target imports, rather than a shorter test-only deadline.
                with ThreadPoolExecutor(max_workers=2) as pool:
                    first,borrowed=list(pool.map(lambda _:device_services.ensure(runtime),range(2)))
                self.assertEqual(first['pid'],borrowed['pid'])
                self.assertEqual(len(children),1)
                provider=Registry().configure_reticulum(socket_path=first['socket'],register=False)
                self.wait(lambda:provider.snapshot().get('owner_online'))
                os.kill(first['pid'],signal.SIGTERM)
                self.wait(lambda:not provider.snapshot().get('owner_online'))
                second=device_services.ensure(runtime)
                self.assertNotEqual(first['pid'],second['pid'])
                self.wait(lambda:provider.snapshot().get('owner_online'))
                self.assertEqual(provider.snapshot()['pid'],second['pid'])
            finally:
                if provider is not None:provider.close()
                for child in children:
                    if child.poll() is None:child.terminate()
                    try:child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill();child.wait(timeout=5)

    def connection(self,factory):
        service=Connections('/tmp/unused','/tmp/unused','/tmp/unused',factory)
        self.addCleanup(service.close)
        return service

    def source(self,online=True,services=()):
        state=dict(owner_online=online,services=list(services))
        return SimpleNamespace(dynamic_services=True,catalogue_provider=SimpleNamespace(snapshot=lambda:state),bindings={},bind_wakeup=lambda cb:None,close=lambda:None,state=state)

    def test_initial_transient_failure_recovers_without_user_retry(self):
        calls=[];source=self.source()
        def factory(*args):
            calls.append(args)
            if len(calls)==1:raise TimeoutError('temporarily busy')
            return source,'device'
        service=self.connection(factory);service.connect('ssh','selected-host')
        self.wait(lambda:service.source is source)
        self.assertEqual(calls,[('ssh','selected-host')]*2)
        self.assertEqual(service.error,'')

    def test_failed_switch_retries_even_while_previous_device_is_online(self):
        first,second=self.source(),self.source();calls=[]
        def factory(kind,address):
            calls.append(address)
            if len(calls)==2:raise TimeoutError('new device starting')
            return (first if address=='old' else second),address
        service=self.connection(factory);service.connect('ssh','old')
        self.wait(lambda:service.source is first and service._future.done())
        service.connect('ssh','new');self.wait(lambda:service.source is second)
        self.assertEqual(calls,['old','new','new'])

    def test_owner_loss_reattaches_selected_device(self):
        first,second=self.source(),self.source();sources=iter((first,second))
        service=self.connection(lambda *_:(next(sources),'device'))
        service.connect('ssh','selected-host');self.wait(lambda:service.source is first)
        first.state['owner_online']=False;service.notify()
        self.wait(lambda:service.source is second)

    def test_late_service_readiness_attaches_service_bundle(self):
        first,second=self.source(),self.source();sources=iter((first,second))
        service=self.connection(lambda *_:(next(sources),'device'))
        service.connect('ssh','selected-host');self.wait(lambda:service.source is first)
        first.state['services']=[dict(id='reticulum',available=True)]
        service.notify();self.wait(lambda:service.source is second)

    def test_late_endpoint_attaches_while_service_is_still_starting(self):
        first,second=self.source(),self.source();sources=iter((first,second))
        service=self.connection(lambda *_:(next(sources),'device'))
        service.connect('ssh','selected-host');self.wait(lambda:service.source is first)
        first.state['services']=[dict(id='reticulum',available=False,state='starting',socket='/tmp/rns/owner.sock')]
        service.notify();self.wait(lambda:service.source is second)

    def test_recovery_preserves_an_independently_selected_owner(self):
        class Selection:
            def __init__(self):self.provider=None;self.generation=0
            def adopt(self,provider,*args,**kwargs):self.provider=provider;self.generation+=1
            def disconnect(self):self.provider=None;self.generation+=1
        for independent in (object(),None):
            old_owner=SimpleNamespace(close=lambda:None)
            new_owner=SimpleNamespace(close=lambda:None)
            first,second=self.source(),self.source(services=[dict(id="reticulum",available=True)])
            first.bindings={'reticulum':old_owner};second.bindings={'reticulum':new_owner}
            sources=iter((first,second));service=self.connection(lambda *_:(next(sources),'device'))
            service.reticulum=Selection()
            service.connect('ssh','selected-host');self.wait(lambda:service.source is first)
            if independent is None:service.reticulum.disconnect()
            else:service.reticulum.adopt(independent,'separate owner')
            first.state['owner_online']=False;service.notify()
            self.wait(lambda:service.source is second)
            self.assertIs(service.reticulum.provider,independent)
            self.assertFalse(service._needs_recovery())
            service.close()

    def test_peer_catalogue_does_not_reattach_ungranted_services(self):
        source=self.source(services=[dict(id='reticulum',available=True)])
        source.dynamic_services=False
        service=self.connection(lambda *_:(source,'peer'))
        service.connect('peer','verified-peer');self.wait(lambda:service.source is source)
        service.notify();self.assertIsNone(service._retry)

    def test_disconnect_cancels_pending_retry(self):
        calls=[]
        def factory(*args):calls.append(args);raise TimeoutError('busy')
        service=self.connection(factory);service.connect('ssh','selected-host')
        self.wait(lambda:service._retry is not None)
        service.disconnect();time.sleep(1.2)
        self.assertEqual(len(calls),1);self.assertIsNone(service.source)

    def test_configuration_error_is_not_retried(self):
        calls=[]
        def factory(*args):calls.append(args);raise ValueError('bad configuration')
        service=self.connection(factory);service.connect('socket','invalid')
        self.wait(lambda:not service.busy)
        self.assertIsNone(service._retry);self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
