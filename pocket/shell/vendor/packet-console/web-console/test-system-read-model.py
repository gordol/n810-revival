import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('system_read_model', Path(__file__).with_name('system-read-model.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def sample():
    return {'system': {'source': 'n810', 'platform': 'linux', 'observed_at': 1000,
            'boot_id': 'boot-a', 'uptime_seconds': 100,
            'cpu': {'total_ticks': 100, 'idle_ticks': 40},
            'load_average': [0.2, 0.1, 0.05],
            'memory_bytes': {'total': 1000, 'available': 400, 'free': 100},
            'swap': {'total_bytes': 800, 'free_bytes': 700, 'in_pages': 2,
                     'out_pages': 3, 'page_size_bytes': 4096}},
            'network_stats': {'wlan0': {'rx_bytes': 100, 'tx_bytes': 200}}}


class Tests(unittest.TestCase):
    def pair(self):
        before = sample()
        after = copy.deepcopy(before)
        after['system'].update(observed_at=1010, uptime_seconds=110,
                               cpu={'total_ticks': 200, 'idle_ticks': 65})
        after['system']['swap'].update(in_pages=7, out_pages=13)
        after['network_stats']['wlan0'].update(rx_bytes=1100, tx_bytes=2200)
        return after, before

    def test_real_deltas_and_units(self):
        current, previous = self.pair()
        originals = copy.deepcopy((current, previous))
        result = m.project(current, previous, now=1012)
        self.assertEqual(result['cpu_busy_percent'], 75)
        self.assertEqual(result['network_interfaces']['wlan0'],
                         {'rx_bytes_per_second': 100, 'tx_bytes_per_second': 200})
        self.assertEqual(result['swap'], {'in_bytes_per_second': 2048, 'out_bytes_per_second': 4096})
        self.assertEqual(result['memory_used_bytes'], 600)
        self.assertEqual(result['memory_free_bytes'], 100)
        self.assertEqual(result['swap_used_bytes'], 100)
        self.assertEqual(result['sample_age_seconds'], 2)
        self.assertEqual(result['source'], 'n810')
        self.assertEqual((current, previous), originals)

    def test_no_traffic_is_measured_zero(self):
        current, previous = self.pair()
        current['network_stats'] = copy.deepcopy(previous['network_stats'])
        current['system']['swap'] = copy.deepcopy(previous['system']['swap'])
        result = m.project(current, previous, now=1010)
        self.assertEqual(result['network_interfaces']['wlan0']['rx_bytes_per_second'], 0)
        self.assertEqual(result['swap']['in_bytes_per_second'], 0)

    def test_duplicate_cached_and_invalid_windows(self):
        for change in ({'boot_id': 'boot-b'}, {'boot_id': ''}, {'uptime_seconds': 100},
                       {'uptime_seconds': 99}, {'uptime_seconds': 221}, {'observed_at': 1000}):
            with self.subTest(change=change):
                current, previous = self.pair()
                current['system'].update(change)
                result = m.project(current, previous, now=1010)
                self.assertIsNone(result['cpu_busy_percent'])
                self.assertIsNone(result['network_interfaces']['wlan0']['rx_bytes_per_second'])
                self.assertIsNone(result['swap']['in_bytes_per_second'])
        result = m.project(sample(), sample(), now=1001)
        self.assertIsNone(result['rate_window_seconds'])

    def test_counter_reset_is_not_zero_activity(self):
        current, previous = self.pair()
        current['system']['cpu']['idle_ticks'] = 1
        current['system']['swap']['in_pages'] = 0
        current['network_stats']['wlan0']['rx_bytes'] = 0
        result = m.project(current, previous, now=1010)
        self.assertIsNone(result['cpu_busy_percent'])
        self.assertIsNone(result['swap']['in_bytes_per_second'])
        self.assertIsNone(result['network_interfaces']['wlan0']['rx_bytes_per_second'])

    def test_missing_available_cannot_use_free_as_used(self):
        current = sample()
        del current['system']['memory_bytes']['available']
        result = m.project(current, now=1000)
        self.assertIsNone(result['memory_used_bytes'])
        self.assertEqual(result['memory_free_bytes'], 100)
        self.assertIsNone(result['cpu_busy_percent'])
        self.assertIsNone(result['network_interfaces']['wlan0']['rx_bytes_per_second'])

    def test_replay_keeps_original_age_and_missing_evidence(self):
        current, previous = self.pair()
        result = m.project(current, previous, now=2000)
        self.assertEqual(result['observed_at'], 1010)
        self.assertEqual(result['sample_age_seconds'], 990)
        self.assertEqual(result['freshness'], 'stale')
        self.assertIsNone(result['cpu_busy_percent'])
        self.assertIsNone(result['rate_window_seconds'])
        self.assertEqual(m.project({}, now=2000)['freshness'], 'unavailable')
        self.assertIsNone(m.project(current, now=1000)['sample_age_seconds'])

    def test_battery_units_and_signed_current(self):
        current = sample()
        current['power'] = [{'POWER_SUPPLY_TYPE': 'Mains'},
                            {'POWER_SUPPLY_TYPE': 'Battery', 'POWER_SUPPLY_NAME': 'battery',
                             'POWER_SUPPLY_STATUS': 'Discharging', 'POWER_SUPPLY_CAPACITY': '72',
                             'POWER_SUPPLY_VOLTAGE_NOW': '3800000',
                             'POWER_SUPPLY_CURRENT_NOW': '-120000', 'POWER_SUPPLY_TEMP': '257'}]
        battery = m.project(current, now=1000)['batteries'][0]
        self.assertEqual(battery['current_microamps'], -120000)
        self.assertEqual(battery['temperature_tenths_celsius'], 257)
        self.assertEqual(battery['capacity_percent'], 72)

    def test_bad_cpu_memory_pages_and_missing_interface(self):
        current, previous = self.pair()
        current['system']['cpu']['idle_ticks'] = 200
        current['system']['memory_bytes']['available'] = 2000
        current['system']['swap']['page_size_bytes'] = None
        current['network_stats']['usb0'] = {'rx_bytes': 500, 'tx_bytes': 500}
        result = m.project(current, previous, now=1010)
        self.assertIsNone(result['cpu_busy_percent'])
        self.assertIsNone(result['memory_used_bytes'])
        self.assertIsNone(result['swap']['in_bytes_per_second'])
        self.assertIsNone(result['network_interfaces']['usb0']['rx_bytes_per_second'])


if __name__ == '__main__':
    unittest.main()
