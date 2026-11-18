import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from native_navigation import native_key
from bluetooth_view import Bluetooth, State


class FirstUse(unittest.TestCase):
    def test_scan_pair_callsign_and_start(self):
        form=Bluetooth(State(),local_receive=True)
        done=threading.Event()
        form.bind_wakeup(done.set)
        address='02:00:00:00:00:01'
        with patch('peripheral_setup.uv_pro_radios',return_value=[]), \
             patch('peripheral_setup.receive_profile',side_effect=FileNotFoundError), \
             patch('peripheral_setup.radio_discovery',return_value=[address]) as discover, \
             patch('peripheral_setup.save_receive') as save, \
             patch('optional_services.start') as start:
            def press(key):
                done.clear()
                self.assertTrue(native_key(form,key))
                self.assertTrue(done.wait(2))
            press('\r')
            self.assertIn('[ Scan for UV-PRO ]',form.lines())
            press('\r')
            discover.assert_called_once_with('scan')
            self.assertIn('[ Pair selected radio ]',form.lines())
            press('\r')
            discover.assert_called_with('pair',address)
            start.assert_not_called()
            for key in 'n0call':self.assertTrue(native_key(form,key))
            press('\r')
            save.assert_called_once_with({'callsign':'N0CALL','address':address})
            start.assert_called_once_with(['receive'])
