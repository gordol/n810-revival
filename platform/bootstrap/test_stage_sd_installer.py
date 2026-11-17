# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify bootstrap isolation and reject incompatible module packages."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from stage_sd_installer import stage

class StageSDInstaller(unittest.TestCase):
    def fixture(self, folder):
        root=Path(folder)/'root';package=Path(folder)/'package';release='5.15.224-n810-sd-installer'
        for name in ('sbin','usr/local/sbin','usr/sbin','usr/bin','bin','lib/modules/operating-kernel'):
            (root/name).mkdir(parents=True,exist_ok=True)
        (root/'sbin/n810-slot-init').write_text('#!/bin/sh\nexec /sbin/init\n')
        (root/'lib/modules/operating-kernel/keep').write_text('operating GPU/modules unchanged')
        for name in ('usr/sbin/dropbear','usr/bin/dropbearconvert','bin/busybox'):(root/name).touch()
        modules=package/'root/lib/modules'/release;modules.mkdir(parents=True)
        (modules/'fixture.ko').write_bytes(b'fixture')
        (package/'Module.symvers').write_text('0x1234 module_layout vmlinux EXPORT_SYMBOL\n')
        (package/'zImage-omap2420-n810').write_bytes(b'fixture kernel')
        (package/'BUILD.json').write_text(json.dumps(dict(kind='n810-sd-installer-kernel',release=release,kernel_modules=1)))
        return root,package

    def test_keeps_operating_modules_and_gates_temporary_init(self):
        with tempfile.TemporaryDirectory() as folder:
            root,package=self.fixture(folder)
            with patch('stage_sd_installer.subprocess.check_output',return_value='0x1234 module_layout\n'):
                result=stage(root,package)
            self.assertEqual(result['module_crc_checks'],1)
            self.assertEqual((root/'lib/modules/operating-kernel/keep').read_text(),'operating GPU/modules unchanged')
            init=(root/'sbin/n810-slot-init').read_text()
            self.assertIn('n810.install=sd',init);self.assertTrue(init.endswith('exec /sbin/init\n'))
            script=(root/'usr/local/sbin/n810-sd-installer').read_text()
            self.assertIn('dropbear -s -j -k',script)
            self.assertNotIn('/etc/init.d/pocket',script)

    def test_bad_abi_is_rejected_before_root_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root,package=self.fixture(folder)
            with patch('stage_sd_installer.subprocess.check_output',return_value='0x9876 module_layout\n'):
                with self.assertRaisesRegex(ValueError,'ABI mismatch'):stage(root,package)
            self.assertFalse((root/'usr/local/sbin/n810-sd-installer').exists())
            self.assertEqual((root/'sbin/n810-slot-init').read_text(),'#!/bin/sh\nexec /sbin/init\n')

if __name__=='__main__':unittest.main()
