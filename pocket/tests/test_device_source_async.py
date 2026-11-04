from pathlib import Path
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from device_radio_source import DeviceSource

class RetainedLoadingTests(unittest.TestCase):
    def test_slow_files_do_not_block_read_and_refresh_is_not_lost(self):
        receive=SimpleNamespace(bind_wakeup=lambda callback:None,refresh=lambda:None,
            close=lambda:True,read=lambda now:dict(live=dict(data=dict(captured=None))))
        entered=threading.Event();release=threading.Event();finished=threading.Event()
        with tempfile.TemporaryDirectory() as home,patch('console_source.Source',return_value=receive):
            source=DeviceSource(home=home,collector=lambda:{})
            self.addCleanup(source.close);self.addCleanup(release.set)
            source.bind_wakeup(lambda:finished.set())
            loads=[]
            def load():
                revision=len(loads)+1;loads.append(revision);entered.set()
                if not release.wait(5):raise RuntimeError('Test load was not released')
                return {'revision':revision},{'outbox':[revision]},None,{'revision':revision}
            source._load_files=load
            initial=source.read(0)
            self.assertTrue(entered.wait(3))
            self.assertNotIn('revision',initial['catalog'])
            # Calling read while the disk worker is blocked must return the old
            # publication. Refresh during that load schedules exactly one successor.
            source.refresh()
            self.assertNotIn('revision',source.read(0)['catalog'])
            first=source.files_pending
            release.set();first.result(timeout=3)
            first_payload=source.read(0)
            self.assertEqual(first_payload['catalog']['revision'],1)
            self.assertEqual(first_payload['catalog']['outbox'],[1])
            self.assertEqual(first_payload['live']['data']['radio_live']['revision'],1)
            second=source.files_pending
            self.assertIsNotNone(second);second.result(timeout=3)
            self.assertEqual(source.read(0)['catalog']['revision'],2)
            self.assertEqual(loads,[1,2]);self.assertIsNone(source.files_pending)
            self.assertTrue(finished.is_set())

    def test_live_startup_does_not_decode_saved_history_and_offline_fallback_still_loads(self):
        state=dict(error='Receive socket connecting',captured=None)
        receive=SimpleNamespace(state=state,starting=True,bind_wakeup=lambda callback:None,refresh=lambda:None,
            close=lambda:True,read=lambda now:dict(live=dict(data=dict(captured=state['captured']))))
        with tempfile.TemporaryDirectory() as home,patch('console_source.Source',return_value=receive):
            source=DeviceSource(home=home,collector=lambda:{})
            self.addCleanup(source.close)
            source.aprs.mkdir(parents=True);(source.aprs/'raw-frames.json').write_text('{}')
            with patch('device_retained.packet_bundle',return_value=([],[])) as decode:
                source.read(0)
                self.assertIsNone(source.rx_pending);decode.assert_not_called()
                receive.starting=False;state['error']='Receive socket unavailable';source._receive_changed();source.read(0)
                self.assertIsNotNone(source.rx_pending);source.rx_pending.result(timeout=3)
                decode.assert_called_once()
                source.read(0)
                state.update(error=None,captured=1);source._receive_changed()
                self.assertFalse(source._raw_refresh_pending)

if __name__=='__main__':unittest.main()
