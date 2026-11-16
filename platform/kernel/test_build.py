# SPDX-License-Identifier: GPL-2.0-or-later
"""Resumed kernel packages must validate without hashing their old manifest."""
import hashlib
import json
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('kernel_build', Path(__file__).with_name('build.py'))
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class KernelPackageTest(unittest.TestCase):
    def test_og_boot_governor_and_config_lock(self):
        here = Path(__file__).parent
        data = (here / 'n810.config').read_bytes()
        config = data.decode().splitlines()
        self.assertIn('CONFIG_CPU_FREQ_DEFAULT_GOV_POWERSAVE=y', config)
        self.assertIn('CONFIG_CPU_FREQ_GOV_POWERSAVE=y', config)
        self.assertNotIn('CONFIG_CPU_FREQ_DEFAULT_GOV_PERFORMANCE=y', config)
        lock = json.loads((here / 'source.lock.json').read_text())
        self.assertEqual(lock['inputs']['n810.config'], hashlib.sha256(data).hexdigest())
        self.assertEqual(lock['expected_modules'], 198)

    def test_toolchain_rejects_a_different_compiler(self):
        lock = {'toolchain': {'gcc_version': '12.2.0', 'binutils_version': '2.40'}}
        with patch.object(build.subprocess, 'check_output', side_effect=['12.2.0', 'GNU ld (GNU Binutils for Debian) 2.40']):
            build.check_toolchain(lock, {})
        with patch.object(build.subprocess, 'check_output', side_effect=['14.2.0', 'GNU ld (GNU Binutils for Debian) 2.44']):
            with self.assertRaisesRegex(RuntimeError, 'OG toolchain'):
                build.check_toolchain(lock, {})

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
