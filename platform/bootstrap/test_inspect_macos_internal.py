# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run the read-only collector against a disposable ext4 filesystem."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import inspect_macos_internal as collector


def tool(name):
    return shutil.which(name) or (str(Path('/opt/homebrew/opt/e2fsprogs/sbin') / name)
                                 if (Path('/opt/homebrew/opt/e2fsprogs/sbin') / name).is_file() else None)


class InspectTest(unittest.TestCase):
    def test_identity_change_stops_before_reading_filesystem(self):
        with patch.object(collector, 'disk_info', side_effect=[{'DeviceTreePath': 'one'},
                                                            {'DeviceTreePath': 'two'}]), \
             patch.object(collector.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'identity changed'):
                collector.inspect('/dev/disk99', 0x02100000, '/unused/debugfs')
            run.assert_called_once_with(['diskutil', 'unmountDisk', '/dev/disk99'], check=True)

    @unittest.skipUnless(tool('mke2fs') and tool('debugfs'), 'Requires e2fsprogs')
    def test_copies_logs_without_changing_filesystem(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staging = root / 'root'
            (staging / 'etc').mkdir(parents=True)
            (staging / 'etc/inittab').write_text('id:2:initdefault:\n')
            (staging / 'var/log').mkdir(parents=True)
            (staging / 'var/log/n810-fn-remap.log').write_text('fixture boot failure\n')
            image = root / 'root.ext4'
            with image.open('wb') as stream:
                stream.truncate(16 * 1024**2)
            subprocess.run([tool('mke2fs'), '-q', '-t', 'ext4', '-F', '-d', str(staging), str(image)], check=True)
            before = hashlib.sha256(image.read_bytes()).digest()
            real_run = subprocess.run
            operations = []

            def run(argv, **kwargs):
                if argv[0] == 'diskutil':
                    operations.append(argv[1])
                    return subprocess.CompletedProcess(argv, 0)
                self.assertEqual(argv[0], tool('debugfs'))
                self.assertEqual(argv[-1], '/dev/rdisk99s1')
                self.assertNotIn('-w', argv)
                return real_run([*argv[:-1], str(image)], **kwargs)

            with patch.object(collector, 'disk_info', return_value={'DeviceTreePath': 'fixture'}), \
                 patch.object(collector.subprocess, 'run', side_effect=run):
                output = collector.inspect('/dev/disk99', 0x02100000, tool('debugfs'))
            self.addCleanup(shutil.rmtree, output)
            self.assertEqual((output / 'log/n810-fn-remap.log').read_text(), 'fixture boot failure\n')
            self.assertEqual(before, hashlib.sha256(image.read_bytes()).digest())
            self.assertEqual(operations, ['unmountDisk', 'eject'])


if __name__ == '__main__':
    unittest.main()
