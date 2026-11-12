# SPDX-License-Identifier: GPL-2.0-or-later
"""Resumed kernel packages must validate without hashing their old manifest."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('kernel_build', Path(__file__).with_name('build.py'))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class KernelPackageTest(unittest.TestCase):
    def test_resumed_manifest_excludes_itself_and_hashes_updated_outputs(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder)
            (package / 'BUILD.json').write_text('old build record')
            (package / 'kernel.bin').write_bytes(b'new kernel')
            module = package / 'root/lib/modules/test.ko'
            module.parent.mkdir(parents=True)
            module.write_bytes(b'new module')
            self.assertEqual(build.package_hashes(package), {
                'kernel.bin': hashlib.sha256(b'new kernel').hexdigest(),
                'root/lib/modules/test.ko': hashlib.sha256(b'new module').hexdigest()})


if __name__ == '__main__':
    unittest.main()
