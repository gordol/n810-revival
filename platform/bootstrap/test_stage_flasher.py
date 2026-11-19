import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from stage_flasher import stage


class FlasherStagingTests(unittest.TestCase):
    def fixture(self, folder):
        build = folder / 'build'
        build.mkdir()
        header = bytearray(20)
        header[:5] = b'\x7fELF\x01'
        header[18:20] = b'\x28\x00'
        for name, content in {'0xFFFF': bytes(header), 'source.tar.gz': b'source',
                              'usb-host.patch': b'patch', 'COPYING': b'license'}.items():
            (build / name).write_bytes(content)
        sha = lambda name: hashlib.sha256((build / name).read_bytes()).hexdigest()
        record = {'binary_sha256': sha('0xFFFF'), 'identity': {
            'target': 'armel', 'usb_only': True, 'source_revision': 'fixture',
            'source_sha256': sha('source.tar.gz'),
            'usb_host_patch_sha256': sha('usb-host.patch')}}
        (build / 'BUILD.json').write_text(json.dumps(record))
        return build

    def test_install_contains_matching_source_and_no_setuid_bit(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            build = self.fixture(folder)
            root = folder / 'root'
            stage(root, build)
            self.assertTrue((root/'usr/local/sbin/n810-provision').is_file())
            self.assertTrue((root/'usr/local/lib/n810-installer/flasher/BUILD.json').is_file())
            self.assertTrue((root/'usr/local/lib/n810-installer/bootstrap/linux_storage.py').is_file())
            self.assertEqual((root / 'usr/local/bin/0xFFFF').stat().st_mode & 0o7777, 0o755)
            self.assertEqual((root / 'usr/local/share/doc/0xffff/source.tar.gz').read_bytes(), b'source')

    def test_changed_binary_or_source_is_rejected_before_install(self):
        for name in ('0xFFFF', 'source.tar.gz', 'usb-host.patch'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                build = self.fixture(folder)
                (build / name).write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    stage(folder / 'root', build)
                self.assertFalse((folder / 'root').exists())

    def test_local_device_build_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            build = self.fixture(folder)
            record = json.loads((build / 'BUILD.json').read_text())
            record['identity']['usb_only'] = False
            (build / 'BUILD.json').write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, 'USB-only'):
                stage(folder / 'root', build)
