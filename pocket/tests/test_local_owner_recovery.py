from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import selectors
import signal
import socket
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

DOMAIN = Path(__file__).resolve().parents[1] / 'shell/vendor/apps/domains/reticulum'
sys.path.insert(0, str(DOMAIN))
from provider import Provider, LocalProvider, CarrierProvider, MeshCoreProvider
from local_owner import ManagedOwner, endpoint_identity
from owner import exchange

STARTUP_TIMEOUT = float(os.environ.get('POCKET_STARTUP_TEST_TIMEOUT', '8'))


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir='/tmp')
        self.root = Path(self.temporary.name)
        self.providers, self.processes = [], []

    def tearDown(self):
        for provider in self.providers:
            process = getattr(provider.transport, 'process', None)
            if process is not None: self.processes.append(process)
            provider.close()
        for process in set(self.processes):
            if process.poll() is None: process.terminate()
            process.wait(timeout=max(5, STARTUP_TIMEOUT))
        self.temporary.cleanup()

    def wait(self, provider, predicate):
        deadline = time.monotonic() + STARTUP_TIMEOUT
        with selectors.DefaultSelector() as selector:
            selector.register(provider.readable, selectors.EVENT_READ)
            while not predicate(provider.snapshot()):
                remaining = deadline - time.monotonic()
                if remaining <= 0: self.fail(str(provider.snapshot()))
                selector.select(remaining)
                provider.drain()

    def session(self, port='/dev/unused'):
        provider = LocalProvider(self.root, 'fixture', interpreter=sys.executable, radio_id='fixture',
                                 connection='usb', port=port, minimum_txpower=0, maximum_txpower=0)
        self.providers.append(provider)
        return provider

    def fixture(self, block=None, availability_only=False):
        path = self.root / 'owner.sock'
        command = [sys.executable, '-B', str(Path(__file__).with_name('fixtures') / 'local_owner_fixture.py'),
                   '--socket', str(path), '--state', str(self.root), '--station', 'fixture']
        if block: command += ['--block', str(block)]
        def validate(state):
            if state.get('service_type') != 'lifecycle-fixture': raise ValueError('Unexpected fixture owner')
        transport = ManagedOwner(path, dict(service='fixture', station='fixture'), lambda: (command, validate), availability_only=availability_only)
        provider = Provider(path, transport=transport)
        self.providers.append(provider)
        return provider

    def test_availability_stream_validates_owner_and_recovers_on_eof(self):
        provider=self.fixture(availability_only=True)
        self.wait(provider,lambda state:state.get('owner_online'))
        self.assertEqual(provider.snapshot(),dict(version=1,owner_online=True,capabilities=[],scope='availability'))
        old=provider.transport.process;self.processes.append(old)
        epoch=provider.transport.epoch
        old.kill();old.wait(timeout=max(5,STARTUP_TIMEOUT))
        self.wait(provider,lambda state:provider.transport.epoch>epoch and state.get('owner_online'))
        self.assertIsNot(provider.transport.process,old)
        self.assertEqual(provider.snapshot()['scope'],'availability')
        self.assertFalse((self.root/'actions').exists())

    def test_simultaneous_session_clients_share_one_persistent_idle_owner(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = list(pool.map(lambda _: self.session(), range(2)))
        for provider in (a, b): self.wait(provider, lambda state: state.get('owner_online'))
        started = [provider.transport.process for provider in (a, b) if provider.transport.process is not None]
        self.assertEqual(len(started), 1)
        self.processes.extend(started)
        a.close(); self.providers.remove(a)
        state = exchange(b.path, dict(version=1, action='snapshot'))
        self.assertEqual(state['radio_state'], 'idle')
        self.assertIsNone(started[0].poll())

    def test_multiple_deaths_restart_idle_without_replaying_queued_actions(self):
        provider = self.fixture()
        self.wait(provider, lambda state: state.get('owner_online'))
        epoch = provider.transport.epoch
        for _ in range(2):
            old = provider.transport.process
            self.processes.append(old)
            old.kill(); old.wait(timeout=max(5, STARTUP_TIMEOUT))
            self.wait(provider, lambda state: state.get('owner_online') and state.get('pid') != old.pid)
            self.assertEqual(provider.snapshot()['radio_state'], 'idle')
        provider.pending.put(dict(version=1, request_id='old-queued-send', action='send', payload={}, _local_epoch=epoch))
        self.wait(provider, lambda state: (state.get('last_job') or {}).get('id') == 'old-queued-send')
        self.assertEqual(provider.snapshot()['last_job']['state'], 'failed')
        self.assertIn('not replayed', provider.snapshot()['last_job']['error'])
        self.assertFalse((self.root / 'actions').exists())

    def test_unknown_refused_socket_is_never_removed(self):
        path = self.root / 'management-runtime'
        path.mkdir(mode=0o700)
        endpoint = path / 'owner.sock'
        with socket.socket(socket.AF_UNIX) as stale: stale.bind(str(endpoint))
        endpoint.chmod(0o600)
        inode = endpoint.stat().st_ino
        provider = self.session()
        self.wait(provider, lambda state: 'Unrecognized' in str(state.get('error')))
        self.assertEqual(endpoint.stat().st_ino, inode)
        self.assertIsNone(provider.transport.process)

    def test_live_mismatched_owner_is_not_replaced(self):
        a = self.session()
        self.wait(a, lambda state: state.get('owner_online'))
        self.processes.append(a.transport.process)
        inode = Path(a.path).stat().st_ino
        b = self.session('/dev/different')
        self.wait(b, lambda state: 'does not match' in str(state.get('error')))
        self.assertEqual(Path(a.path).stat().st_ino, inode)
        self.assertIsNone(b.transport.process)
        self.assertTrue(exchange(a.path, dict(version=1, action='snapshot'))['owner_online'])

    def test_cancellation_before_ready_stops_only_the_owned_startup(self):
        marker = self.root / 'initializing'
        provider = self.fixture(marker)
        # The process-created file is an initialization marker, not a radio observation.
        deadline = time.monotonic() + max(5, STARTUP_TIMEOUT)
        while not marker.exists():
            if time.monotonic() >= deadline: self.fail('Fixture did not initialize')
            time.sleep(0.005)
        process = provider.transport.process
        self.processes.append(process)
        provider.close(); self.providers.remove(provider)
        self.assertIsNotNone(process.poll())
        self.assertFalse((self.root / 'owner.sock').exists())

    def test_second_client_can_cancel_while_first_waits_for_readiness(self):
        marker = self.root / 'initializing'
        first = self.fixture(marker)
        deadline = time.monotonic() + max(5, STARTUP_TIMEOUT)
        while not marker.exists():
            if time.monotonic() >= deadline: self.fail('Fixture did not initialize')
            time.sleep(0.005)
        process = first.transport.process
        self.processes.append(process)
        second = self.fixture(marker)
        self.wait(second, lambda state: bool(state.get('error')) and second.transport.delay > 0)
        started = time.monotonic()
        second.close(); self.providers.remove(second)
        self.assertLess(time.monotonic() - started, 2)
        self.assertFalse(second.worker.is_alive())
        self.assertIsNone(second.transport.process)
        self.assertIsNone(process.poll())
        first.close(); self.providers.remove(first)
        self.assertIsNotNone(process.poll())

    def test_replaced_stale_inode_is_retained(self):
        provider = self.fixture()
        self.wait(provider, lambda state: state.get('owner_online'))
        process = provider.transport.process
        self.processes.append(process)
        provider.close(); self.providers.remove(provider)
        process.kill(); process.wait(timeout=max(5, STARTUP_TIMEOUT))
        path = self.root / 'owner.sock'
        path.unlink()
        with socket.socket(socket.AF_UNIX) as stale: stale.bind(str(path))
        path.chmod(0o600)
        inode = path.stat().st_ino
        other = self.fixture()
        self.wait(other, lambda state: 'Unrecognized' in str(state.get('error')))
        self.assertEqual(path.stat().st_ino, inode)
        self.assertIsNone(other.transport.process)

    def test_reused_inode_with_different_ctime_is_not_the_known_endpoint(self):
        transport = ManagedOwner(self.root / 'owner.sock', dict(service='fixture'), lambda: None)
        try:
            original = SimpleNamespace(st_dev=1, st_ino=42, st_ctime_ns=100)
            replacement = SimpleNamespace(st_dev=1, st_ino=42, st_ctime_ns=101)
            transport.record(original)
            self.assertTrue(transport.known_stale(original))
            self.assertFalse(transport.known_stale(replacement))
            self.assertNotEqual(endpoint_identity(original), endpoint_identity(replacement))
        finally:
            transport.close(); transport.dispose()

    def test_carrier_and_meshcore_borrow_matching_idle_owners(self):
        for kind in ('carrier', 'meshcore'):
            state = self.root / kind
            if kind == 'carrier':
                make = lambda: CarrierProvider(state, 'fixture', sys.executable,
                    [dict(type='tcp-client', host='127.0.0.1', port=45678)])
            else:
                make = lambda: MeshCoreProvider(state, 'fixture', sys.executable, '/dev/unused')
            a, b = make(), make()
            self.providers.extend((a, b))
            for provider in (a, b): self.wait(provider, lambda row: row.get('owner_online'))
            self.assertEqual(sum(p.transport.process is not None for p in (a, b)), 1)
            self.assertNotIn(a.snapshot().get('radio_state', a.snapshot().get('connection_state')), ('online', 'connected'))


if __name__ == '__main__': unittest.main()
