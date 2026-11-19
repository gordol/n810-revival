"""Check missing transitive helpers, privilege groups and duplicate event owners."""
from pathlib import Path
import tempfile
import unittest
from system_contract import COMMANDS,FILES,validate

class ContractTests(unittest.TestCase):
    def root(self,folder):
        root=Path(folder)
        for name in COMMANDS|FILES:
            p=root/name.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text('fixture\n');p.chmod(0o755 if name in COMMANDS else 0o440)
        (root/'etc/group').write_text(''.join(f'{group}:x:{i+1000}:nokia\n' for i,group in enumerate(('n810-power','n810-radio','dialout','bluetooth'))))
        for runlevel in (2,3,4,5):
            directory=root/f'etc/rc{runlevel}.d';directory.mkdir()
            (directory/'S03n810-wake').symlink_to('../init.d/n810-wake')
        return root
    def test_missing_menu_fails_before_image_is_packaged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.root(folder);self.assertEqual(set(validate(root)),COMMANDS|FILES)
            (root/'usr/local/sbin/n810-console-power-menu').unlink()
            with self.assertRaisesRegex(ValueError,'Missing system dependency.*console-power-menu'):validate(root)
    def test_group_and_event_owner_are_part_of_the_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.root(folder);(root/'etc/rc2.d/S03n810-display-keys').touch()
            with self.assertRaisesRegex(ValueError,'Duplicate'):validate(root)
            (root/'etc/rc2.d/S03n810-display-keys').unlink();(root/'etc/group').write_text('')
            with self.assertRaisesRegex(ValueError,'system group'):validate(root)
    def test_absolute_linux_symlinks_do_not_escape_into_host(self):
        with tempfile.TemporaryDirectory() as folder:
            root=self.root(folder);p=root/'usr/bin/fuser';p.unlink();p.symlink_to('/missing-on-target')
            with self.assertRaisesRegex(ValueError,'fuser'):validate(root)
