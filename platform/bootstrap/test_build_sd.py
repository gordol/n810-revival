"""Checks for the SD image layout and input validation without a device."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('build_sd', HERE / 'build_sd.py')
build_sd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_sd)


class SDBuilderTest(unittest.TestCase):
    def test_mbr_root_partition_matches_kernel_layout(self) -> None:
        record = build_sd.mbr(2048 * 1024 * 1024 // 512, 0x12345678)
        self.assertEqual(len(record), 512)
        self.assertEqual(record[510:512], b'\x55\xaa')
        self.assertEqual(struct.unpack_from('<I', record, 440)[0], 0x12345678)
        self.assertEqual(record[450], 0x83)
        self.assertEqual(struct.unpack_from('<II', record, 454), (2048, 4194304))

    def test_rejects_invalid_or_multiple_public_keys(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            key = Path(name) / 'owner.pub'
            record = struct.pack('>I', 11) + b'ssh-ed25519' + struct.pack('>I', 32) + bytes(range(32))
            key.write_text('ssh-ed25519 ' + base64.b64encode(record).decode() + '\n')
            self.assertTrue(build_sd.public_key(key).startswith('ssh-ed25519 '))
            key.write_text(key.read_text() * 2)
            with self.assertRaises(ValueError):
                build_sd.public_key(key)
            key.write_text('ssh-ed25519 ' + base64.b64encode(b'fake-key-material' * 3).decode() + '\n')
            with self.assertRaises(ValueError):
                build_sd.public_key(key)
            key.write_text('ssh-ed25519 !!!\n')
            with self.assertRaises(ValueError):
                build_sd.public_key(key)

    def test_rejects_wrong_root_device_and_tampered_kernel(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            package = Path(name)
            image = package / 'zImage-omap2420-n810'
            image.write_bytes(b'candidate combined image')
            (package / 'KERNELRELEASE').write_text('5.15.224-n810\n')
            modules = package / 'root/lib/modules/5.15.224-n810'
            modules.mkdir(parents=True)
            (modules / 'test.ko').write_bytes(b'module')
            report = {'release': '5.15.224-n810', 'root_device': '/dev/mmcblk0p2',
                      'files': {image.name: hashlib.sha256(image.read_bytes()).hexdigest(),
                                (modules / 'test.ko').relative_to(package).as_posix():
                                hashlib.sha256((modules / 'test.ko').read_bytes()).hexdigest()}}
            (package / 'BUILD.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'root-device'):
                build_sd.kernel_inputs(package)
            report['root_device'] = '/dev/mmcblk0p1'
            (package / 'BUILD.json').write_text(json.dumps(report))
            self.assertEqual(build_sd.kernel_inputs(package)[0], '5.15.224-n810')
            (modules / 'test.ko').write_bytes(b'tampered module')
            with self.assertRaisesRegex(ValueError, 'module does not match'):
                build_sd.kernel_inputs(package)
            (modules / 'test.ko').write_bytes(b'module')
            image.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'does not match'):
                build_sd.kernel_inputs(package)


if __name__ == '__main__':
    unittest.main()
