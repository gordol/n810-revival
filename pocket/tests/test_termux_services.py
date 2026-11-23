from pathlib import Path
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SHELL = Path(__file__).resolve().parents[1]/'shell'
sys.path.insert(0, str(SHELL))
from termux_radio import PhoneFeed
from termux_services import PhoneStatus
from system_view import model


class PhoneTests(unittest.TestCase):
    def test_power_unknown_after_failed_resample(self):
        read = PhoneStatus(lambda: {'system': {}})
        with patch('termux_services.time.monotonic', side_effect=[0, 2, 32]), patch(
            'termux_services.output', side_effect=['{"percentage":43,"status":"CHARGING"}','1','0','','denied']
        ):
            first = read()
            self.assertEqual(model.battery_rows(first['power'])[0]['capacity_percent'], 43)
            self.assertTrue(first['bluetooth_controller']['powered'])
            self.assertFalse(read()['bluetooth_controller']['powered'])
            last = read()
            self.assertEqual(last['power'], [])
            self.assertNotIn('bluetooth_controller', last)

    def test_authenticated_serial_to_stations_without_remote_device(self):
        ready = threading.Event()
        args = {}
        def launch(command, **kwargs):
            args.update(port=int(command[command.index('port')+1]), token=command[-1])
            ready.set()
            return SimpleNamespace(returncode=0, stdout='', stderr='')
        root = SHELL/'vendor/packet-console'
        fixture = json.loads((root/'fixtures/walk-mixed-vendor.json').read_text())
        raw = bytes.fromhex(fixture['complete_kiss_frame'])
        with tempfile.TemporaryDirectory() as tmp, patch('termux_radio.subprocess.run', side_effect=launch):
            feed = PhoneFeed('unused', 'unused', directory=Path(tmp)/'stations.sqlite3', sources=root)
            try:
                self.assertTrue(ready.wait(2))
                address = ('127.0.0.1', args['port'])
                with socket.create_connection(address) as bad:
                    bad.sendall(b'wrong\n')
                with socket.create_connection(address) as peer:
                    peer.sendall(args['token'].encode()+b'\nREADY\n\xc0'+raw.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc')+b'\xc0')
                    deadline = time.monotonic()+5
                    while not feed.state['packets'] and time.monotonic()<deadline:
                        time.sleep(.02)
                    self.assertEqual(feed.state['raw_records'][0]['frame'], raw.hex())
                    self.assertTrue(feed.feed_control['radio']['connected'])
                    self.assertIsNone(feed.projection_error)
                    self.assertIsNotNone(feed.last_directory_ingest)
                feed.worker.join(2)
                self.assertFalse(feed.state['online'])
            finally:
                feed.close()
