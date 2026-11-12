"""The privileged helper must reap a timed-out flasher, not leave it armed."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import prepare_macos_helper as helper


class HelperTimeout(unittest.TestCase):
    def test_watchdog_terminates_the_flash_process(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            build = root / 'build'
            build.mkdir()
            output = root / 'helper'
            pid_file = root / 'flasher.pid'
            binary = build / '0xFFFF'
            binary.write_text('#!/bin/sh\nprintf "%s\\n" "$$" > "' + str(pid_file) +
                              '"\nexec /bin/sleep 60\n')
            binary.chmod(0o755)
            lock = json.loads(Path(helper.__file__).with_name('source.lock.json').read_text())
            (build / 'BUILD.json').write_text(json.dumps({
                'identity': {'usb_only': True, 'nolo_only': True,
                             'source_revision': lock['revision'], 'source_sha256': lock['sha256']},
                'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}))
            with patch.object(helper.platform, 'system', return_value='Darwin'), \
                 patch.object(helper, 'DEST', str(output)), \
                 patch.object(helper.subprocess, 'check_output', return_value='0xFFFF:\n'), \
                 patch.object(helper.subprocess, 'run'):
                helper.prepare(build, output)
            script = output / 'helper'
            script.write_text(script.read_text().replace('/bin/sleep "$limit"', '/bin/sleep 1'))
            subprocess.run(['/bin/sh', '-n', str(script)], check=True)
            result = subprocess.run(['/bin/sh', str(script), '-m', 'kernel:/fixture', '-f', '-r'], timeout=5,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode, 0)
            pid = int(pid_file.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


if __name__ == '__main__':
    unittest.main()
