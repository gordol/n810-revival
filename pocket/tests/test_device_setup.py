"""Exercise first-boot choices without a radio, privileged helper or device."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from native_device_setup import DeviceSetup
from native_navigation import native_key, navigation
from service_policy import load, save
from peripheral_setup import save_endpoints, receive_profile
from setup_choices import SetupChoices

class DeviceSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir="/tmp");self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        self.homepatch=patch('pathlib.Path.home',return_value=self.home)
        self.homepatch.start();self.addCleanup(self.homepatch.stop)
    def test_default_off_and_startup_not_immediate(self):
        form=DeviceSetup();self.addCleanup(form.close)
        self.assertFalse(any(load().values()))
        with patch('optional_services.start',side_effect=AssertionError('Save must not start services')):
            form.key('toggle-receive');form.key('save')
        self.assertTrue(load()['receive']);self.assertFalse(load()['reticulum'])
        self.assertEqual((self.home/'.config/pocket/services.json').stat().st_mode&0o777,0o600)
    def test_ui_fields_toggle_keyboard_and_pointer(self):
        form=DeviceSetup();self.addCleanup(form.close)
        self.assertIn('APRS','\n'.join(form.lines()))
        navigation(form).target='toggle-reticulum';native_key(form,'\r')
        self.assertTrue(form.choices.startup['reticulum'])
        form.key('page-radio');form.lines()
        row=next(row for row,key in form._hits if key=='callsign')
        form.pointer(dict(type='pointer',action='press',x=0,y=row))
        for key in 'N0CALL':native_key(form,key)
        self.assertEqual(form.callsign.text,'N0CALL')
    def test_wifi_secret_masked_not_saved_and_stdin_only(self):
        form=DeviceSetup();self.addCleanup(form.close);form.key('page-wifi')
        form.choices.wifi_ssid.text='IEEE';form.choices.wifi_pass.text='password'
        form.field='wifi_pass'
        self.assertNotIn('password','\n'.join(form.lines()))
        self.assertNotIn('password',json.dumps(form.session_state()))
        with patch('native_device_setup.subprocess.run') as run:
            run.return_value.returncode=0
            form.key('wifi-apply');form.pending.result(timeout=2);form.poll()
        self.assertEqual(form.choices.wifi_pass.text,'')
        self.assertNotIn('password',str(run.call_args.args))
        self.assertEqual(json.loads(run.call_args.kwargs['input'])['passphrase'],'password')
    def test_explicit_receive_needs_profile_and_no_personal_default(self):
        from optional_services import start
        with patch('optional_services.subprocess.Popen',side_effect=AssertionError('No process without profile')):
            with self.assertRaises(FileNotFoundError):start(['receive'])
        save_endpoints('N0CALL',receive='02:00:00:00:00:01')
        self.assertEqual(receive_profile()['address'],'02:00:00:00:00:01')
    def test_owner_endpoints_private_validated_and_reloadable(self):
        from app_registry import saved_reticulum_selection
        from meshcore_service import saved_selection
        save_endpoints('N0CALL',meshcore='/dev/ttyUSB0',reticulum='/dev/rfcomm0',tx_min=0,tx_max=0)
        state=self.home/'.local/state/current-world'
        ret=saved_reticulum_selection(state);mesh=saved_selection(state)
        self.assertEqual(ret['interpreter'],'/opt/n810-mesh/bin/python')
        self.assertEqual(mesh['interpreter'],'/opt/pocket-htit/bin/python')
        self.assertEqual(mesh['port'],'/dev/ttyUSB0')
        self.assertFalse(any(load().values()))
        for name in ('reticulum-owner.msgpack','meshcore-owner.toml'):
            self.assertEqual((state/name).stat().st_mode&0o777,0o600)
        with self.assertRaises(ValueError):save_endpoints('N0CALL',receive='not-a-bluetooth-address')
    def test_boot_default_starts_nothing(self):
        from optional_services import boot
        with patch('optional_services.start',side_effect=AssertionError('Default boot must be idle')):
            self.assertEqual(boot(),[])
    def test_laptop_choices_private_session_and_toggle(self):
        choices=SetupChoices();choices.wifi_ssid.text='IEEE';choices.wifi_pass.text='password'
        choices.key('toggle-meshcore')
        self.assertTrue(choices.profile()['startup']['meshcore'])
        self.assertNotIn('password',json.dumps(choices.public_state()))
        self.assertNotIn('password','\n'.join(choices.lines()))

    def test_identity_transfer_private_exclusive_and_active_owner_guard(self):
        import socket
        from peripheral_setup import identity_transfer
        source=self.home/'saved-identity';source.write_bytes(bytes(range(64)))
        identity_transfer('import',str(source))
        target=self.home/'.local/state/pocket-reticulum/identity'
        self.assertEqual(target.read_bytes(),source.read_bytes())
        self.assertEqual(target.stat().st_mode&0o777,0o600)
        with self.assertRaises(FileExistsError):identity_transfer('import',str(source))
        output=self.home/'export';identity_transfer('export',str(output))
        self.assertEqual(output.read_bytes(),source.read_bytes())
        endpoint=target.parent/'management-runtime/owner.sock';endpoint.parent.mkdir()
        server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.addCleanup(server.close)
        server.bind(str(endpoint));server.listen(1)
        with self.assertRaisesRegex(ValueError,'Stop Reticulum'):identity_transfer('import',str(source))
    def test_data_plan_runs_without_downloads_and_validates_area(self):
        from native_data_setup import prepare
        output=self.home/'data'
        result=prepare('plan','-123 47 -122.99 47.01','https://example.invalid/region.osm.pbf',str(output),'30')
        self.assertTrue(result)
        self.assertFalse(output.exists())
        with self.assertRaises(ValueError):prepare('build','bad bounds','https://example.invalid/map',str(output),'30')
    def test_packaging_requires_arm_reticulum_provenance(self):
        import importlib.util
        path=Path(__file__).resolve().parents[1]/'tools/stage_runtime.py'
        # The package verifier rejects incorrect ABI/platform before staging.
        sys.path.insert(0,str(path.parent))
        from package_nokia import require_native_reticulum
        with self.assertRaisesRegex(ValueError,'require microReticulum'):require_native_reticulum({})
