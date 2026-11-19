"""Private image setup is opt-in and never leaks Wi-Fi secrets into receipts."""
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from setup_profile import validate, wpa_config, stage, read_stdin

class SetupProfileTests(unittest.TestCase):
    def test_defaults_and_boolean_choices(self):
        self.assertEqual(validate({})['startup'],dict(receive=False,meshcore=False,reticulum=False))
        for value in ({'startup':{'receive':1}}, {'startup':{'unknown':True}}, {'password':'secret'}):
            with self.assertRaises(ValueError):validate(value)
    def test_wpa_known_vector_and_injection_safe_ssid(self):
        text=wpa_config(dict(ssid='IEEE',passphrase='password',country='US'))
        self.assertIn('psk=f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e',text)
        self.assertNotIn('password',text)
        text=wpa_config(dict(ssid='"} # test',passphrase='password',country='GB'))
        self.assertIn('ssid=227d20232074657374',text)
        with self.assertRaises(ValueError):validate({'wifi':dict(ssid='x',passphrase='short')})
    def test_stage_owner_modes_and_sanitized_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'home/nokia').mkdir(parents=True)
            result=stage(root,dict(startup={'receive':True},wifi=dict(ssid='IEEE',passphrase='password',country='US')))
            conf=root/'etc/wpa_supplicant/wpa_supplicant-wlan0.conf'
            self.assertEqual(stat.S_IMODE(conf.stat().st_mode),0o600)
            choices=root/'home/nokia/.config/pocket/services.json'
            self.assertEqual(choices.stat().st_uid,os.getuid())
            self.assertEqual(json.loads(choices.read_text()),dict(receive=True,meshcore=False,reticulum=False))
            self.assertNotIn('password',json.dumps(result))
            self.assertNotIn('f42c6fc5',json.dumps(result))
    def test_profile_size_limit(self):
        with self.assertRaises(ValueError):read_stdin(io.StringIO(' '*8193))
