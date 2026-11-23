#!/usr/bin/env python3
"""Check atomic display status transitions using fixture files and a one-second policy."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


class DisplayPublicationTest(unittest.TestCase):
    def test_steady_state_and_transitions(self):
        daemon = Path(__file__).with_name("n810-displayd")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in {"config": "lcd_sample_seconds=1", "blank": "0",
                                "brightness": "24", "max_brightness": "127",
                                "lux": "60", "capacity": "100", "online": "1"}.items():
                (root / name).write_text(value + "\n")
            paths = {"DISPLAY_CONFIG": root / "config", "SCREEN_FB": root,
                     "SCREEN_BACKLIGHT": root, "BATTERY_SYSFS": root, "CHARGER_SYSFS": root,
                     "AMBIENT_PATH": root / "lux", "DISPLAYD_RUN_DIR": root / "run",
                     "SCREEN_RUN_DIR": root / "screen"}
            env = dict(os.environ, **{"N810_" + k: str(v) for k, v in paths.items()})
            process = subprocess.Popen(["sh", str(daemon)], env=env)
            status = root / "run/status"
            effective = root / "screen/effective-brightness"

            def wait_for(prefix):
                end = time.monotonic() + 5
                while time.monotonic() < end:
                    self.assertIsNone(process.poll())
                    if status.exists() and status.read_text().startswith(prefix):
                        return
                    time.sleep(.05)
                self.fail(f"Timed out waiting for {prefix}")

            try:
                wait_for("state=active lux=60 ")
                timestamps = (status.stat().st_mtime_ns, effective.stat().st_mtime_ns)
                time.sleep(2.1)
                self.assertEqual(timestamps, (status.stat().st_mtime_ns, effective.stat().st_mtime_ns))
                status.unlink()
                wait_for("state=active ")
                (root / "blank").write_text("1\n")
                wait_for("state=blank framebuffer=1 ")
                (root / "brightness").write_text("invalid\n")
                (root / "blank").write_text("0\n")
                wait_for("state=sensor-fault ")
                (root / "brightness").write_text("24\n")
                (root / "lux").write_text("3\n")
                wait_for("state=active lux=3 ")
                self.assertEqual(effective.read_text(), (root / "brightness").read_text())
            finally:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
