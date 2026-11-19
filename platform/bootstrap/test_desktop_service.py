"""A timed-out desktop stop must not kill the GPU owner or start a replacement."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'device/pocket-desktop.init'

class DesktopServiceTests(unittest.TestCase):
    def test_timeout_preserves_owner_record_and_aborts_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pid=root/'owner.pid';pid.write_text('123\n')
            fake=root/'start-stop-daemon'
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\nexit 2\n');fake.chmod(0o755)
            script=root/'service';script.write_text(SCRIPT.read_text().replace('/run/pocket-desktop.pid',str(pid)));script.chmod(0o755)
            calls=root/'calls'
            result=subprocess.run(['sh',str(script),'restart'],env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'],CALLS=str(calls)),capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertTrue(pid.exists())
            self.assertEqual(len(calls.read_text().splitlines()),1)
            self.assertNotIn('KILL',calls.read_text())
            self.assertIn('restart cancelled',result.stderr)

if __name__=='__main__':unittest.main()
