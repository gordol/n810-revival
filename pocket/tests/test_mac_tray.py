import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import mac_tray


class MacTrayTests(unittest.TestCase):
    def test_sample_arms_a_thirty_second_refresh_deadline(self):
        worker=Mock()
        with patch.object(mac_tray,'_deadline',0), \
                patch.object(mac_tray,'_state',('?', 'unknown', 'unknown')), \
                patch.object(mac_tray.time,'monotonic',return_value=100), \
                patch.object(mac_tray.threading,'Thread',return_value=worker):
            self.assertEqual(mac_tray.sample(),('?', 'unknown', 'unknown'))
            worker.start.assert_called_once()
            self.assertEqual(mac_tray.delay(),30)
            mac_tray.sample()
            worker.start.assert_called_once()
            with patch.object(mac_tray.time,'monotonic',return_value=130):
                self.assertEqual(mac_tray.delay(),0)

    def test_collector_wakes_panel_after_publishing_battery_and_bluetooth(self):
        wake=Mock()
        with patch.object(mac_tray,'_state',('?', 'unknown', 'unknown')), \
                patch.object(mac_tray,'_wakeup',wake), \
                patch('mac_tray.subprocess.check_output',side_effect=['82% -InternalBattery', 'on']):
            mac_tray._collect()
            self.assertEqual(mac_tray._state,('82%','unknown','on'))
            wake.assert_called_once()


if __name__=='__main__':unittest.main()
