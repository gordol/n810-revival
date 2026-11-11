"""Guard the macOS card writer against selecting an internal or partial disk."""
import importlib.util
from pathlib import Path
import plistlib
import subprocess
import unittest
from unittest.mock import patch

path = Path(__file__).with_name('write_card.py')
spec = importlib.util.spec_from_file_location('write_card', path)
writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(writer)


class CardWriterTest(unittest.TestCase):
    def info(self, **changes):
        record = dict(RemovableMedia=True, WholeDisk=True,
                      BusProtocol='Secure Digital', TotalSize=32_000_000_000)
        record.update(changes)
        return subprocess.CompletedProcess([], 0, plistlib.dumps(record))

    def test_accepts_only_removable_whole_sd_disk(self):
        with patch.object(writer, 'run', return_value=self.info()):
            self.assertEqual(writer.card_info('disk4')['TotalSize'], 32_000_000_000)
            for name in ('disk4s1', '/dev/disk4', 'disk0;echo bad'):
                with self.assertRaises(ValueError):
                    writer.card_info(name)
        for change in (dict(RemovableMedia=False), dict(WholeDisk=False),
                       dict(BusProtocol='USB')):
            with patch.object(writer, 'run', return_value=self.info(**change)):
                with self.assertRaises(ValueError):
                    writer.card_info('disk4')


if __name__ == '__main__':
    unittest.main()
