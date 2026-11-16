#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("build_logged.py")


class BuildLogTests(unittest.TestCase):
    def test_failure_stdout_stderr_and_private_input(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "logs/build.log"
            code = ("import sys; secret=sys.stdin.readline(); "
                    "print('build output'); print('assembly error', file=sys.stderr); "
                    "sys.exit(17 if secret.strip() == 'private-input' else 99)")
            result = subprocess.run([sys.executable, str(SCRIPT), "--log", str(log),
                                     "--", sys.executable, "-c", code],
                                    input="private-input\n", text=True, capture_output=True)
            self.assertEqual(result.returncode, 17)
            self.assertIn("build output", log.read_text())
            self.assertIn("assembly error", log.read_text())
            self.assertIn("Build exit status: 17", log.read_text())
            self.assertNotIn("private-input", log.read_text() + result.stdout)
            if os.name == "posix":
                self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_success_and_existing_log_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "build.log"
            command = [sys.executable, str(SCRIPT), "--log", str(log),
                       "--", sys.executable, "-c", "print('finished')"]
            result = subprocess.run(command, capture_output=True)
            self.assertEqual(result.returncode, 0)
            before = log.read_bytes()
            result = subprocess.run(command, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(log.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
