"""The controller indicator remains truthful when the UV-Pro feed is absent."""
from pathlib import Path
import sys
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from bluetooth_view import State,project


class BluetoothHardwareFallbackTests(unittest.TestCase):
    def hardware(self,powered,age=0):
        return dict(available=True,powered=powered,observed_at=time.time()-age)

    def test_feed_absent_uses_fresh_controller_observation(self):
        for powered,role in ((True,'bluetooth'),(False,'warning')):
            state=State(hardware=lambda:self.hardware(powered))
            self.assertIs(state.read()['powered'],powered)
            self.assertEqual(state.panel()[1]['bluetooth:open'],role)
            self.assertIsNone(state.read()['radio_connected'])

    def test_stale_hardware_does_not_claim_power(self):
        self.assertIsNone(project(None,False,self.hardware(True,age=30))['powered'])

    def test_fresh_hardware_observation_wins_over_stale_feed(self):
        snapshot=dict(version=1,type='state',controller=dict(available=True,powered=False,devices=[]),
                      reception=dict(enabled=True),radio=dict(connected=False),capabilities=[])
        self.assertIs(project(snapshot,True,self.hardware(True))['powered'],True)


if __name__=='__main__':unittest.main()
