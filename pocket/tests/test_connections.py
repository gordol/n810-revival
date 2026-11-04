import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

SHELL = Path(__file__).resolve().parents[1] / 'shell'
sys.path.insert(0, str(SHELL))
from connections import Connections
from native_connections import ConnectionsView
from launch import command


class ReceiveOwner:
    """Two actual Unix socket endpoints with bounded, empty retained history."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir()
        self.stop = threading.Event()
        self.listeners = []
        self.clients = []
        self.threads = []
        for name in ('aprs.sock', 'replay.sock'):
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(self.root/name)); listener.listen(8); listener.settimeout(.1)
            self.listeners.append(listener)
            thread = threading.Thread(target=self.serve, args=(listener, name), daemon=True)
            thread.start(); self.threads.append(thread)

    def serve(self, listener, name):
        while not self.stop.is_set():
            try: client, _ = listener.accept()
            except socket.timeout: continue
            except OSError: return
            if name == 'replay.sock':
                with client: client.sendall(b'{"type":"snapshot","version":1,"records":0}\n')
            else: self.clients.append(client)

    def close(self):
        self.stop.set()
        for listener in self.listeners: listener.close()
        for thread in self.threads: thread.join(1)
        for client in self.clients: client.close()


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pocket-', dir='/tmp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def connection(self, factory=None):
        service = Connections(self.root/'directory.sqlite3', SHELL/'vendor/packet-console', self.root/'runtime', factory)
        self.addCleanup(service.close)
        return service

    def wait(self, predicate):
        end = time.monotonic()+3
        while not predicate():
            if time.monotonic()>end: self.fail('Timed out waiting for source publication')
            time.sleep(.005)

    def test_offline_launch_does_not_create_worker_or_read_owner(self):
        service = self.connection(lambda *_: self.fail('Unexpected connection'))
        self.assertIsNone(service._pool)
        self.assertFalse(service.read(0)['live']['data']['receive_connected'])
        argv = command(['--state', str(self.root/'shell'), '--instance', 'one'])
        self.assertIn('--shell', argv)
        for option in ('--ssh-receive', '--receive-feed', '--replay', '--device-radio'):
            self.assertNotIn(option, argv)

    def test_cold_local_setup_keeps_observation_and_cancel_available(self):
        import builtins
        from unittest.mock import patch
        from service_selection import Selection
        service=self.connection(lambda *_:self.fail('Cancelled startup attached a device'))
        service.reticulum=Selection(None,self.root)
        self.addCleanup(service.reticulum.close)
        entered,release=threading.Event(),threading.Event()
        original=builtins.__import__
        def slow_import(name,*args,**kwargs):
            if name=='concurrent.futures' and threading.current_thread().name=='local-services':
                entered.set();release.wait(3)
            return original(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=slow_import):
            try:
                service.attach_local_services()
                self.assertTrue(entered.wait(1))
                self.assertTrue(service._lock.acquire(blocking=False));service._lock.release()
                self.assertTrue(service.reticulum.lock.acquire(blocking=False));service.reticulum.lock.release()
                self.assertFalse(service.reticulum.snapshot()['owner_online'])
                service.disconnect();service.reticulum.disconnect()
            finally:
                release.set();service._local_start.join(2)
        self.assertFalse(service._local_start.is_alive())
        self.assertIsNone(service.source)
        self.assertIsNone(service.reticulum.provider)

    def test_two_instances_use_same_socket_owner_and_disconnect_independently(self):
        owner = ReceiveOwner(self.root/'owner'); self.addCleanup(owner.close)
        a, b = self.connection(), self.connection()
        for service in (a,b): self.assertTrue(service.connect('socket', str(owner.root)))
        self.wait(lambda: all(s.read(0)['live']['data'].get('receive_connected') for s in (a,b)))
        a.disconnect()
        self.assertFalse(a.read(0)['live']['data']['receive_connected'])
        self.assertTrue(b.read(0)['live']['data']['receive_connected'])
        self.assertEqual(len(owner.clients), 2)

    def test_ssh_selection_reuses_existing_adapter_and_source_contract(self):
        from unittest.mock import patch
        owner = ReceiveOwner(self.root/'ssh-owner'); self.addCleanup(owner.close)
        service = self.connection(); service.ssh_key = '/explicit/key'
        service.reticulum=SimpleNamespace(registry=None)
        def attach(root,target,registry,factory):return factory()
        with patch('receive_bridge.ensure_preferred', return_value=(owner.root.resolve(), 'operator@host')) as ensure, patch('device_connection.attach',side_effect=attach):
            self.assertTrue(service.connect('ssh', 'operator@host'))
            self.wait(lambda: service.read(0)['live']['data'].get('receive_connected'))
            ensure.assert_called_once_with(target='operator@host', key='/explicit/key', runtime=service.runtime/'ssh',require_receive=False)
        self.assertTrue(service.remote)
        self.assertEqual(service.label, 'operator@host')

    def test_cancelled_completion_cannot_reconnect_and_queue_stays_bounded(self):
        started, release, closed = threading.Event(), threading.Event(), threading.Event()
        def factory(*_):
            started.set(); release.wait(2)
            return SimpleNamespace(bind_wakeup=lambda cb: None, close=closed.set), 'old'
        service = self.connection(factory)
        self.assertTrue(service.connect('socket', 'old')); self.assertTrue(started.wait(1))
        service.disconnect()
        for _ in range(20): self.assertFalse(service.connect('socket', 'new'))
        release.set(); self.assertTrue(closed.wait(1)); self.wait(lambda: service._future.done())
        self.assertIsNone(service.source)

    def test_failure_keeps_local_shell_alive_and_notifies(self):
        event = threading.Event(); service = self.connection(); service.bind_wakeup(event.set)
        self.assertTrue(service.connect('socket', str(self.root/'missing')))
        self.wait(lambda: not service.busy)
        self.assertTrue(event.is_set()); self.assertIn('aprs.sock', service.error)
        self.assertIsNone(service.source)

    def test_switch_uses_existing_state_consumer_and_publishes_new_owner(self):
        from radio_state import State
        a, b = ReceiveOwner(self.root/'a'), ReceiveOwner(self.root/'b')
        self.addCleanup(a.close); self.addCleanup(b.close)
        service = self.connection(); state = State(source=service)
        event = threading.Event(); state.bind_wakeup(event.set); state.update(True)
        service.connect('socket', str(a.root))
        self.wait(lambda: service.read(0)['live']['data'].get('receive_connected'))
        state.update(); version = state.version
        service.disconnect(); state.update()
        self.assertGreater(state.version, version)
        self.assertFalse(state.payload['live']['data']['receive_connected'])
        service.connect('socket', str(b.root))
        self.wait(lambda: service.label == str(b.root.resolve()) and service.read(0)['live']['data'].get('receive_connected'))
        state.update(); self.assertTrue(state.payload['live']['data']['receive_connected'])

    def test_saved_address_is_a_preference_not_an_automatic_connection(self):
        service = self.connection(lambda *_: self.fail('Unexpected attachment'))
        view = ConnectionsView(None, app_context=SimpleNamespace(services={'connections': service}))
        view.restore_session({'address': 'operator@example'})
        self.assertEqual(view.address, 'operator@example')
        self.assertIsNone(service._pool)
        self.assertEqual(view.session_state(), {'address': 'operator@example'})
        service.suggested_address = 'explicit-host'
        other = ConnectionsView(None, app_context=SimpleNamespace(services={'connections': service}))
        other.restore_session({'address': 'old-host'})
        self.assertEqual(other.address, 'explicit-host')

    def test_device_inventory_identifies_local_telemetry_and_other_owners(self):
        service=self.connection()
        service.source=SimpleNamespace(system={'system':{'source':'local'}},state={},close=lambda:None,bind_wakeup=lambda cb:None)
        service._pool=__import__('concurrent.futures',fromlist=['ThreadPoolExecutor']).ThreadPoolExecutor(max_workers=1)
        view=ConnectionsView(None,app_context=SimpleNamespace(services={'connections':service}))
        self.assertIn('System: connected',' '.join(view.lines()))
        service.source=SimpleNamespace(catalogue_provider=SimpleNamespace(snapshot=lambda:dict(owner_online=True)),adopted={},state={},close=lambda:None,bind_wakeup=lambda cb:None)
        service.reticulum=SimpleNamespace(provider=object(),label="nokia@remote",snapshot=lambda:dict(owner_online=True))
        self.assertIn('Reticulum: connected',' '.join(view.lines()))
        self.assertIn('nokia@remote',' '.join(view.lines()))

    def test_local_device_stays_attached_when_radio_is_offline(self):
        service=self.connection()
        service._pool=__import__('concurrent.futures',fromlist=['ThreadPoolExecutor']).ThreadPoolExecutor(max_workers=1)
        receive=SimpleNamespace(state=dict(online=False,error='Receive socket offline: FileNotFoundError'))
        service.source=SimpleNamespace(local_device=True,closed=False,receive=receive,
            system={'system':{'source':'laptop'}},catalogue={'services':[dict(id='system',available=True),dict(id='receive',available=False)]},
            close=lambda:None,bind_wakeup=lambda cb:None)
        view=ConnectionsView(None,app_context=SimpleNamespace(services={'connections':service}))
        lines=view.lines();text=' '.join(lines)
        self.assertTrue(lines[0].startswith('[*Device]'))
        self.assertIn('Attached',lines[1]);self.assertIn('System: connected',text)
        self.assertIn('Feed: unavailable',text)
        self.assertNotIn('FileNotFoundError',text)
        self.assertEqual(receive.state['error'],'Receive socket offline: FileNotFoundError')

    def test_failed_ssh_preserves_local_attachment_and_keeps_details_out_of_status(self):
        service=self.connection()
        service._pool=__import__('concurrent.futures',fromlist=['ThreadPoolExecutor']).ThreadPoolExecutor(max_workers=1)
        service.source=SimpleNamespace(local_device=True,closed=False,state={},system={'system':{'source':'laptop'}},close=lambda:None,bind_wakeup=lambda cb:None)
        service._intent=('ssh','nokia@192.168.10.1')
        service.error='SSH device connection failed.\nnokia@192.168.10.1: Connection timed out during banner exchange\nConnection to port 22 timed out'
        view=ConnectionsView(None,app_context=SimpleNamespace(services={'connections':service}))
        for width in (40,76):
            view.width=width;lines=view.lines()
            self.assertIn('Attached',lines[1]);self.assertIn('SSH timed out',lines[2])
            self.assertNotIn('banner exchange',' '.join(lines))
            self.assertEqual(len([hit for hit in view._hits if hit[3]=='e']),1)
        self.assertEqual(view.help_pages()[0][0],'Connection error')
        self.assertIn('banner exchange',' '.join(view.help_pages()[0][1]))

    def test_visible_buttons_dispatch_same_actions_as_keys(self):
        service = self.connection()
        view = ConnectionsView(None, app_context=SimpleNamespace(services={'connections': service}))
        for width, height in ((38,16),(74,19)):
            view.width, view.height = width, height
            lines = view.lines(); self.assertEqual(len(lines), height)
            self.assertTrue(all(len(line)<=width for line in lines))
            x,y,w,_=next(hit for hit in view._hits if hit[3]=='e')
            self.assertTrue(view.pointer(x,y,width,0,False)); self.assertTrue(view.editing)
            view.key('x'); view.key('escape'); self.assertFalse(view.editing)
            x,y,w,_=next(hit for hit in view._hits if hit[3]=='d')
            self.assertTrue(view.pointer(x,y,width,0,False)); self.assertIsNone(service.source)

    def test_service_rows_open_apps_without_connecting(self):
        opened=[]
        service=self.connection(lambda *_:self.fail('Opening an app must not connect'))
        registry=SimpleNamespace(by_title={'Radio Feed':'radio-feed','Reticulum':'reticulum','Messages':'messages'},open=opened.append)
        view=ConnectionsView(SimpleNamespace(activate=opened.append),app_context=SimpleNamespace(registry=registry,services={'connections':service}))
        view.width,view.height=40,16
        view.lines()
        for key in ('i','f','r','m'):
            x,y,w,_=next(hit for hit in view._hits if hit[3]==key)
            self.assertTrue(view.pointer(x,y,40,0,False))
        self.assertEqual(opened,['System','radio-feed','reticulum','messages'])
        self.assertIsNone(service._pool)

    def test_explicit_owner_tabs_preserve_independent_addresses(self):
        service=self.connection()
        service.reticulum=SimpleNamespace()
        service.meshcore=SimpleNamespace()
        view=ConnectionsView(None,app_context=SimpleNamespace(services={'connections':service}))
        view.address='laptop'
        view.key('o');view.address='radio-owner'
        view.key('b');view.address='mesh-owner'
        view.key('v');self.assertEqual(view.address,'laptop')
        view.key('o');self.assertEqual(view.address,'radio-owner')
        view.key('b');self.assertEqual(view.address,'mesh-owner')

    def test_focus_cycles_do_not_change_tabs_or_connect(self):
        from native_navigation import native_key,navigation
        service=self.connection(lambda *_:self.fail('Focus must not connect'))
        service.reticulum=SimpleNamespace()
        service.meshcore=SimpleNamespace()
        view=ConnectionsView(None,app_context=SimpleNamespace(services={'connections':service}))
        view.address='device-host';state=navigation(view)
        state.select('tabs')
        native_key(view,'\t');self.assertEqual(state.current().key,'action:i')
        self.assertEqual(view.selected_service,'receive')
        native_key(view,'backtab');self.assertEqual(state.current().key,'tabs')
        native_key(view,'right');self.assertEqual(view.selected_service,'reticulum')
        native_key(view,'right');self.assertEqual(view.selected_service,'meshcore')
        native_key(view,'right');self.assertEqual(view.selected_service,'receive')
        self.assertEqual(view.address,'device-host');self.assertIsNone(service._pool)
        native_key(view,'e');native_key(view,'x');native_key(view,'\t')
        self.assertFalse(view.editing);self.assertEqual(view.selected_service,'receive')


if __name__ == '__main__': unittest.main()
