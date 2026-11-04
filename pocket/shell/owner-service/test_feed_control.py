import json
import socket
import unittest
import tempfile
from pathlib import Path
from unittest import mock
from feed_control import Intent, Requests, authorize, frame, save_intent


class ControlTests(unittest.TestCase):
    def controller(self, owner, power):
        owner.observe_controller({'available': True, 'powered': power, 'devices': [], 'error': None})

    def test_power_cycle_preserves_enabled_intent(self):
        owner = Intent()
        self.assertFalse(owner.can_receive)
        self.controller(owner, True)
        self.assertTrue(owner.can_receive)
        owner.action('controller_off')
        self.assertFalse(owner.can_receive)
        self.assertTrue(owner.enabled)
        self.controller(owner, False)
        owner.action('controller_on')
        self.assertFalse(owner.can_receive)
        self.controller(owner, True)
        self.assertTrue(owner.can_receive)

    def test_stop_while_off_does_not_restart_on_power_on(self):
        owner = Intent()
        self.controller(owner, False)
        owner.action('receive_stop')
        self.controller(owner, True)
        self.assertFalse(owner.can_receive)
        self.assertEqual(owner.suspension, 'stopped')

    def test_disconnect_is_intent_not_global_power(self):
        owner = Intent()
        self.controller(owner, True)
        owner.action('radio_disconnect')
        self.assertFalse(owner.can_receive)
        self.assertTrue(owner.controller['powered'])
        self.assertIsNone(owner.connected)

    def test_stop_preserves_observed_connection_until_disconnect(self):
        owner = Intent()
        self.controller(owner, True)
        owner.connected = True
        owner.action('receive_stop')
        owner.stopping = True
        self.assertTrue(owner.snapshot()['radio']['connected'])
        self.assertTrue(owner.snapshot()['reception']['stopping'])

    def test_durable_intent_sync_failures_are_not_acknowledged(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'intent.json'
            save_intent(path, True)
            with mock.patch('feed_control.os.fsync', side_effect=OSError('file sync failed')):
                with self.assertRaises(OSError):
                    save_intent(path, False)
            self.assertTrue(json.loads(path.read_text())['enabled'])
            self.assertEqual(list(Path(directory).glob('.reception-intent-*')), [])
            with mock.patch('feed_control.os.fsync', side_effect=[None, OSError('directory sync failed')]):
                with self.assertRaises(OSError):
                    save_intent(path, False)
            self.assertFalse(json.loads(path.read_text())['enabled'])
            save_intent(path, True)
            self.assertTrue(json.loads(path.read_text())['enabled'])

    def test_first_use_requires_established_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)/'missing-state'
            path = parent/'intent.json'
            with self.assertRaisesRegex(FileNotFoundError, 'not established'):
                save_intent(path, False)
            self.assertFalse(parent.exists())
            parent.mkdir()
            save_intent(path, False)
            self.assertFalse(json.loads(path.read_text())['enabled'])

    def test_first_file_parent_sync_failure_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'intent.json'
            with mock.patch('feed_control.os.fsync', side_effect=[None, OSError('parent sync failed')]):
                with self.assertRaisesRegex(OSError, 'parent sync failed'):
                    save_intent(path, False)
            self.assertFalse(json.loads(path.read_text())['enabled'])

    def test_unknown_controller_and_link_are_distinct(self):
        owner = Intent()
        self.assertIsNone(owner.snapshot()['radio']['connected'])
        self.assertIsNone(owner.controller['powered'])
        with self.assertRaises(ValueError):
            owner.action('controller_on')

    def test_fragmented_protocol_and_limits(self):
        request = dict(type='feed_control', version=1, request_id='a', action='subscribe')
        data = json.dumps(request).encode() + b'\n'
        parser = Requests()
        self.assertEqual(parser.feed(data[:8]), [])
        self.assertEqual(parser.feed(data[8:]), [request])
        for changes in ({'action': {}}, {'request_id': 'é'}, {'request_id': 'a'*65}, {'version': True}):
            with self.assertRaises(ValueError):
                Requests().feed(json.dumps(dict(request, **changes)).encode()+b'\n')
        with self.assertRaises(ValueError):
            Requests().feed(b'x'*4097)
        with self.assertRaises(ValueError):
            frame({'data': 'x'*32768})

    @unittest.skipUnless(hasattr(socket, 'SO_PEERCRED'), 'Linux peer credentials')
    def test_same_uid_peer(self):
        a, b = socket.socketpair()
        try:
            self.assertTrue(authorize(a))
            self.assertFalse(authorize(a, uid=999999))
        finally:
            a.close()
            b.close()


if __name__ == '__main__':
    unittest.main()
