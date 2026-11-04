"""Nokia packaging cannot reintroduce reliance on desktop Python RNS."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from package_nokia import require_native_reticulum,runtime_files,sha


class NativePackageTests(unittest.TestCase):
    def test_nokia_omits_desktop_loader_but_keeps_shared_owner_and_native_code(self):
        prefix='vendor/apps/domains/reticulum/'
        files={prefix+name:b'fixture' for name in ('desktop_stack.py','lxmf_owner.py','native_owner.py','backend_policy.py')}
        self.assertEqual(set(runtime_files(files)),set(files)-{prefix+'desktop_stack.py'})

    def test_library_and_matching_arm_provenance_required(self):
        library=b'fixture native library'
        record=dict(abi=2,platform='Linux-armv6l',library_sha256=sha(library))
        files={'vendor/native/libpocket_rns.so':library,
               'vendor/native/libpocket_rns.provenance.json':json.dumps(record).encode()}
        require_native_reticulum(files)
        for missing in files:
            with self.assertRaisesRegex(ValueError,'require microReticulum'):
                require_native_reticulum({key:value for key,value in files.items() if key!=missing})
        for field,value in [('abi',1),('platform','Darwin-arm64'),('library_sha256','invalid')]:
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'identity mismatch'):
                require_native_reticulum({**files,'vendor/native/libpocket_rns.provenance.json':json.dumps({**record,field:value}).encode()})
