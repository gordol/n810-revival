"""Replay provenance must survive the legacy viewer's connection labels."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('replay_view',Path(__file__).with_name('n810-aprs-view.py'))
view=importlib.util.module_from_spec(spec);spec.loader.exec_module(view)

class ReplayStatus(unittest.TestCase):
    def test_replay_preserves_provenance_without_live_connection_claim(self):
        for status in ('REPLAY | original capture timestamps | hardware unavailable | TX disabled',
                       'REPLAY | end of recorded sequence | no live radio'):
            self.assertEqual(view.friendly_status(status),status)

    def test_real_connection_states_still_apply(self):
        self.assertEqual(view.friendly_status('Bluetooth unavailable'),'OFFLINE  |  waiting to reconnect')
        self.assertEqual(view.friendly_status('Radio disconnected'),'OFFLINE  |  waiting to reconnect')
        self.assertEqual(view.friendly_status('Listening'),'RADIO CONNECTED  |  listening for APRS')
        self.assertEqual(view.friendly_status('Connecting'),'CONNECTING  |  radio / feed')

    def test_replay_packet_arrival_never_claims_live_radio(self):
        with patch.dict(view.os.environ, {'N810_DEV_MODE':'REPLAY'}):
            state=view.State()
            row=state.add('12:34:56 N0CALL>APRS,WIDE1-1 ctl=03 pid=f0 >test')
            self.assertIsNotNone(row)
            self.assertEqual(state.status,'Receiving APRS')
            self.assertEqual(view.friendly_status(state.status),
                             'REPLAY  |  receiving recorded APRS  |  TX disabled')
            self.assertEqual(view.friendly_status('Radio disconnected'),
                             'OFFLINE  |  waiting to reconnect')
            self.assertEqual(view.friendly_status('Bluetooth unavailable'),
                             'OFFLINE  |  waiting to reconnect')

    def test_normal_packet_arrival_keeps_real_mode_label(self):
        with patch.dict(view.os.environ, {}, clear=True):
            self.assertEqual(view.friendly_status('Receiving APRS'),
                             'RADIO CONNECTED  |  listening for APRS')
        with patch.dict(view.os.environ, {'N810_DEV_MODE':'OTHER'}):
            self.assertEqual(view.friendly_status('Receiving APRS'),
                             'RADIO CONNECTED  |  listening for APRS')

if __name__=='__main__':unittest.main()
