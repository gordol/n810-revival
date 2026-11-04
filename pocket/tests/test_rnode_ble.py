import asyncio
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'shell'))
sys.path.insert(0, str(ROOT / 'shell/vendor/apps/domains/reticulum'))
from ble_transport import BLESerial
from endpoints import Endpoint
from app_registry import validate_reticulum_selection
from rnode_ble_view import RNodeBluetooth


class SelectionTests(unittest.TestCase):
    def test_owner_selection_survives_restart_and_setup_events_are_applied(self):
        from session_owner import SessionOwner
        with tempfile.TemporaryDirectory() as tmp:
            owner = SessionOwner(tmp, 'laptop', 'd76d', 'usb', '/dev/cu.radio', 0, 0)
            try:
                owner.dispatch(dict(version=1, action='select_connection', payload=dict(connection='ble', port='ble://RNode D76D')))
                self.assertEqual(owner.snapshot()['radios'][0]['connection'], 'ble')
                owner.post(dict(kind='ble_state', setup_generation=owner.setup_generation,
                                state=dict(phase='paired', authenticated=True, devices=[])))
                owner.drain()
                self.assertTrue(owner.snapshot()['bluetooth']['authenticated'])
                owner.post(dict(kind='ble_state', setup_generation=owner.setup_generation-1,
                                state=dict(phase='scanning')))
                owner.drain()
                self.assertEqual(owner.snapshot()['bluetooth']['phase'], 'paired')
            finally:
                owner.close()
            restored = SessionOwner(tmp, 'laptop', 'd76d', 'usb', '/dev/cu.radio', 0, 0)
            try:
                self.assertEqual(restored.store.endpoint.port, 'ble://RNode D76D')
                self.assertEqual(restored.connection, 'ble')
            finally:
                restored.close()

    def test_tui_usb_ble_and_pair_actions_use_selected_owner(self):
        calls = []
        state = dict(version=1, radio_state='idle', radios=[dict(station_id='laptop', radio_id='d76d', connection='usb', port='/dev/cu.radio')],
                     capabilities=['rnode_bluetooth_on','rnode_pairing_mode','select_connection','ble_scan','ble_pair','ble_stop'])
        service = SimpleNamespace(snapshot=lambda: state, request=lambda action,payload: calls.append((action,payload)))
        view = RNodeBluetooth(app_context=SimpleNamespace(services={'reticulum':service}))
        view.open()
        for width in (40, 76):
            view.width = width
            self.assertTrue(all(len(row)<=width for row in view.lines()))
        view.key('1'); view.key('2'); view.key('e')
        self.assertTrue(view.modal())
        for char in 'RNode D76D': view.key(char)
        view.key('\r'); view.key('s'); view.key('p'); view.key('x')
        self.assertEqual(calls, [('rnode_bluetooth_on',{}), ('rnode_pairing_mode',{}),
            ('select_connection',dict(connection='ble',port='ble://RNode D76D')),
            ('ble_scan',{}), ('ble_pair',{}), ('ble_stop',{})])

    def test_ble_selection_preserves_explicit_device_and_rejects_config_injection(self):
        value = dict(mode='local', state='/tmp/state', interpreter='/usr/bin/python3',
                     station='laptop', radio_id='d76d', connection='ble',
                     port='ble://RNode D76D', minimum_txpower=0, maximum_txpower=0)
        self.assertEqual(validate_reticulum_selection(value)['port'], value['port'])
        self.assertEqual(Endpoint('laptop', 'd76d', 'ble', value['port']).port, value['port'])
        for port in ('ble://', 'ble:// ', 'ble://RNode\n[interfaces]', '/dev/cu.radio'):
            with self.assertRaises(ValueError):
                validate_reticulum_selection(dict(value, port=port))
            with self.assertRaises(ValueError):
                Endpoint('laptop', 'd76d', 'ble', port)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_connected_but_unauthenticated_mac_never_reports_verified(self):
        from ble_setup import BLESetup
        states = []
        setup = BLESetup.__new__(BLESetup)
        setup.loop, setup.target, setup.devices = asyncio.get_running_loop(), 'RNode D76D', {}
        setup.publish = states.append
        class Scanner:
            def __init__(self, detection_callback, **kwargs): self.callback = detection_callback
            async def __aenter__(self):
                self.callback(SimpleNamespace(name='RNode D76D', address='device-id'),
                              SimpleNamespace(local_name='RNode D76D', rssi=-40))
            async def __aexit__(self, *args): pass
        class Client:
            def __init__(self, *args, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def start_notify(self, *args): pass
            async def write_gatt_char(self, *args, **kwargs):
                raise OSError('Insufficient encryption')
        with patch.dict(sys.modules, bleak=SimpleNamespace(BleakScanner=Scanner, BleakClient=Client)), patch('sys.platform', 'darwin'):
            await setup.work('ble_pair')
        self.assertIn('authenticating', [state['phase'] for state in states])
        self.assertFalse(any(state['authenticated'] for state in states))
        self.assertEqual(states[-1]['phase'], 'error')
        self.assertIn('choose USB port', states[-1]['error'])

    async def test_usb_utility_zero_exit_without_device_is_reported_as_failure(self):
        from ble_setup import BLESetup
        states = []
        setup = BLESetup.__new__(BLESetup)
        setup.port = '/dev/cu.missing'
        setup.state = lambda phase, error=None, **kwargs: states.append((phase, error))
        async def communicate(**kwargs): return (b'Could not open the specified serial port', None)
        process = SimpleNamespace(returncode=0, communicate=communicate)
        async def launch(*args, **kwargs): return process
        with patch('asyncio.create_subprocess_exec', launch):
            await setup.work('rnode_bluetooth_on')
        self.assertEqual(states[-1][0], 'error')
        self.assertIn('USB cable', states[-1][1])

    async def test_authenticated_write_respects_mtu_and_arms_readback_before_reply(self):
        loop = asyncio.get_running_loop()
        complete = loop.create_future()
        events = []
        owner = SimpleNamespace(loop=loop, detached=False,
                                _command_written=lambda data: events.append(('submitted', data)),
                                _transport_error=lambda error: self.fail(error))
        serial = BLESerial(owner, 'RNode D76D')
        serial.is_open = True
        serial.response = True
        serial.rx = SimpleNamespace(max_write_without_response_size=3)
        async def write(characteristic, data, response):
            events.append(('gatt', data, response))
            if data == b'def':
                complete.set_result(True)
        serial.client = SimpleNamespace(write_gatt_char=write)
        sender = asyncio.create_task(serial.send())
        serial.write(b'abcdef')
        await complete
        sender.cancel()
        await asyncio.gather(sender, return_exceptions=True)
        self.assertEqual(events, [('submitted', b'abcdef'), ('gatt', b'abc', True), ('gatt', b'def', True)])

    async def test_cancel_discovery_stops_scanner_without_connecting(self):
        entered, exited = asyncio.Event(), asyncio.Event()
        class Scanner:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): entered.set(); return self
            async def __aexit__(self, *args): exited.set()
        owner = SimpleNamespace(loop=asyncio.get_running_loop(), _status=lambda *args: None)
        serial = BLESerial(owner, 'RNode D76D')
        with patch.dict(sys.modules, bleak=SimpleNamespace(BleakScanner=Scanner, BleakClient=lambda *args, **kwargs: self.fail('Connected after cancellation'))):
            task = asyncio.create_task(serial.open())
            await entered.wait()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(exited.is_set())
        self.assertFalse(serial.is_open)

    async def test_disconnect_is_reported_and_never_reconnects(self):
        errors = []
        serial = BLESerial(SimpleNamespace(_transport_error=errors.append), 'RNode D76D')
        serial.is_open = True
        serial.disconnected(None)
        self.assertFalse(serial.is_open)
        self.assertEqual(errors, ['BLE device disconnected; select Connect to reconnect'])
        serial.closing = True
        serial.disconnected(None)
        self.assertEqual(len(errors), 1)


if __name__ == '__main__':
    unittest.main()
