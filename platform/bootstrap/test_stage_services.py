"""A fresh service layout must not depend on manually copied Nokia home scripts."""
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from stage_services import REPO, stage, checked_environments, adapt_meshcore_debian

class StageServicesTests(unittest.TestCase):
    def test_requires_runtimes_and_stages_complete_shared_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaisesRegex(ValueError,'Missing optional-service'):checked_environments(root)
            for name in ('opt/n810-mesh/bin/python','opt/pocket-htit/bin/python',
                'usr/local/share/pocket/shell/vendor/native/libpocket_rns.so',
                'usr/local/share/pocket/shell/vendor/native/libpocket_rns.provenance.json'):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.touch()
            shell=root/'usr/local/share/pocket/shell'
            for name in ('vendor/packet-console','owner-service'):
                (shell/name).mkdir(parents=True,exist_ok=True)
                for source in (REPO/'pocket/shell'/name).glob('*.py'):
                    shutil.copyfile(source,shell/name/source.name)
            for name in ('peripheral_setup.py','service_policy.py','optional_services.py'):
                shutil.copyfile(REPO/'pocket/shell'/name,shell/name)
            for name in ('home/nokia','usr/local/sbin','etc/sudoers.d','etc/default'):(root/name).mkdir(parents=True,exist_ok=True)
            with patch('stage_services.subprocess.run') as run:
                target=stage(root)
            for name in ('n810-aprs-feed.py','uvpro-aprs-listen.py','n810-aprs-directory.py',
                         'n810-frame-history.py','n810-kiss-bridge.py','feed_control.py','bluez_events.py','control_changes.py'):
                self.assertTrue((target/name).is_file(),name)
            self.assertNotIn('/home/nokia/n810-radio-proxy.py',(target/'n810-aprs-feed.py').read_text())
            self.assertNotIn("addr = '02:",(target/'uvpro-aprs-listen.py').read_text())
            self.assertTrue((root/'home/nokia/.local/state/n810-aprs/directory.sqlite3').is_file())
            self.assertFalse(list(target.glob('test*')))
            self.assertTrue(any('visudo' in call.args[0] for call in run.call_args_list))
            self.assertEqual((root/'etc/sudoers.d/n810-setup-wifi').stat().st_mode&0o777,0o440)

            for name in ('n810-power','n810-radio'):
                policy=root/'etc/sudoers.d'/name
                self.assertEqual(policy.stat().st_mode&0o777,0o440)
            self.assertTrue((root/'usr/local/lib/n810-platform/rnode_spp_prepare.py').is_file())
            for name in ('n810-bluetooth-address','n810-bluetooth'):
                helper=root/'usr/local/sbin'/name
                self.assertEqual(helper.read_bytes(),(REPO/'platform/scripts'/name).read_bytes())
                self.assertTrue(helper.stat().st_mode & 0o111)
                self.assertGreater(helper.stat().st_size,100)
            self.assertIn(b'--ignore-install hci_nokia',(root/'usr/local/sbin/n810-bluetooth-address').read_bytes())
            self.assertEqual((root/'etc/modprobe.d/n810-bluetooth.conf').read_text(),'install hci_nokia /usr/local/sbin/n810-bluetooth-address --load-driver\n')
            self.assertFalse((root/'etc/n810/rnode-spp.json').exists())
            self.assertIn('BLUETOOTH_ENABLED=0',(root/'etc/default/bluetooth').read_text())


class DebianCryptoTests(unittest.TestCase):
    def test_only_meshcore_imports_are_adapted_and_recorded(self):
        import json
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root/'opt/pocket-htit/lib/python3.11/site-packages/meshcore'
            package.mkdir(parents=True)
            (package/'reader.py').write_text('from Crypto.Hash import SHA256\n')
            (package/'meshcore_parser.py').write_text('from Crypto.Cipher import AES\nfrom Crypto.Hash import HMAC, SHA256\n')
            original = (package/'reader.py').read_bytes()
            adapt_meshcore_debian(root)
            self.assertEqual((package/'reader.py').read_text(), 'from Cryptodome.Hash import SHA256\n')
            record = json.loads((package.parent/'n810-meshcore-debian.json').read_text())
            self.assertEqual(record['files']['reader.py']['upstream_sha256'], hashlib.sha256(original).hexdigest())
            before = (package/'meshcore_parser.py').read_bytes()
            with self.assertRaisesRegex(ValueError, 'imports changed'):
                adapt_meshcore_debian(root)
            self.assertEqual((package/'meshcore_parser.py').read_bytes(), before)
