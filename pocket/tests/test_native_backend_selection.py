"""Native backend selection and isolation of optional messaging failures."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum'))
from native_owner import installed_library,use_native,selected_backend,NativeBackend
import backend_policy
import lxmf_owner

class NativeSelectionTest(unittest.TestCase):
    def test_explicit_stock_and_missing_library(self):
        with patch.dict(os.environ,POCKET_RNS_LIBRARY='stock'):
            self.assertIsNone(installed_library())
        with patch.dict(os.environ,POCKET_RNS_LIBRARY='/nonexistent/pocket-test-library'):
            with self.assertRaisesRegex(ValueError,'missing'):installed_library()
    def test_explicit_library(self):
        with tempfile.NamedTemporaryFile() as file:
            with patch.dict(os.environ,POCKET_RNS_LIBRARY=file.name):self.assertEqual(installed_library(),Path(file.name))

    def test_nokia_release_identity_controls_policy_not_station_name(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertFalse(backend_policy.native_required(root))
            for platform,expected in [('n810',True),('portable-source',False)]:
                (root/'build-info.json').write_text('{"platform":"'+platform+'"}')
                self.assertEqual(backend_policy.native_required(root),expected)

    def test_nokia_rejects_stock_override_and_direct_stack_load_before_import(self):
        with patch.object(backend_policy,'native_required',return_value=True),patch.dict(os.environ,POCKET_RNS_LIBRARY='stock'):
            with self.assertRaisesRegex(ValueError,'desktop-only'):installed_library()
            with patch.dict(sys.modules,{'RNS':None,'LXMF':None}):
                with self.assertRaisesRegex(ValueError,'desktop-only'):lxmf_owner.load_stack()

    def test_missing_nokia_library_never_selects_stock(self):
        with patch.object(backend_policy,'native_required',return_value=True),patch.dict(os.environ,{},clear=True),patch.object(Path,'is_file',return_value=False):
            with self.assertRaisesRegex(ValueError,'requires its packaged microReticulum'):use_native('usb')

    def test_nokia_rejects_ble_but_accepts_native_serial_services(self):
        with patch.object(backend_policy,'native_required',return_value=True):
            for connection,label in (('ble','Direct BLE'),):
                with self.assertRaisesRegex(ValueError,label):use_native(connection)
                with self.assertRaisesRegex(ValueError,label):selected_backend(connection)
            with tempfile.NamedTemporaryFile() as file,patch.dict(os.environ,POCKET_RNS_LIBRARY=file.name):
                for connection in ('usb','bluetooth','hub'):self.assertTrue(use_native(connection))

    def test_desktop_stock_and_ble_remain_available(self):
        with patch.object(backend_policy,'native_required',return_value=False),patch.dict(os.environ,POCKET_RNS_LIBRARY='stock'):
            for connection in ('usb','bluetooth','ble','hub'):self.assertFalse(use_native(connection))

    def test_desktop_loader_still_loads_both_python_stacks_and_cleans_import_hook(self):
        rns,lxmf=object(),object()
        before=list(sys.meta_path)
        with patch.object(backend_policy,'native_required',return_value=False),patch.dict(sys.modules,{'RNS':rns,'LXMF':lxmf}):
            self.assertEqual(lxmf_owner.load_stack(),(rns,lxmf))
        self.assertEqual(sys.meta_path,before)
    def test_all_launchers_share_connection_policy(self):
        with patch.object(backend_policy,'native_required',return_value=False):
            with tempfile.NamedTemporaryFile() as file,patch.dict(os.environ,POCKET_RNS_LIBRARY=file.name):
                for connection in ('usb','bluetooth','hub','loopback','kiss'):
                    self.assertTrue(use_native(connection))
                    self.assertIs(selected_backend(connection),NativeBackend)
                for connection in ('ble',):
                    self.assertFalse(use_native(connection))
                    self.assertIs(selected_backend(connection),lxmf_owner.LXMFBackend)
            with patch.dict(os.environ,POCKET_RNS_LIBRARY='stock'):
                for connection in ('usb','bluetooth','hub','loopback','ble','kiss'):
                    self.assertIs(selected_backend(connection),lxmf_owner.LXMFBackend)

if __name__=='__main__':unittest.main()
