from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from radio_tune_client import Tune


class TuneRoutingTests(unittest.TestCase):
    def test_missing_endpoint_does_not_authorize_mac_radio(self):
        job=Tune(None,direct_mac=False)
        with patch('mac_uvpro.enabled',return_value=True), patch('mac_uvpro.tune') as tune:
            job.run({'rx_mhz':55.555})
        tune.assert_not_called()
        self.assertIn('No radio owner control socket configured',job.status)

    def test_explicit_mac_authorization_uses_direct_radio(self):
        job=Tune(None,direct_mac=lambda:True)
        result={'state':'secondary_tuned'}
        with patch('mac_uvpro.enabled',return_value=True), patch('mac_uvpro.tune',return_value=result) as tune:
            job.run({'rx_mhz':55.555})
        tune.assert_called_once_with({'rx_mhz':55.555})
        self.assertIn('Mac Bluetooth',job.status)


if __name__=='__main__':unittest.main()
