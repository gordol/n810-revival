"""The first-install VT must recover when one kernel ioctl fails."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / 'platform/n810/bootstrap_desktop.py'
SPEC = importlib.util.spec_from_file_location('bootstrap_desktop', SOURCE)
DESKTOP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DESKTOP)


class DisplayRecoveryTest(unittest.TestCase):
    def test_restores_vt_and_update_mode_after_kdsetmode_error(self):
        calls = []

        def ioctl(fd, request, value=None, *unused):
            calls.append(('ioctl', fd, request, value))
            if request == 0x4b3a:
                raise OSError('KDSETMODE failed')

        with tempfile.TemporaryDirectory() as folder:
            mode = Path(folder) / 'update_mode'
            with patch.object(DESKTOP.fcntl, 'ioctl', side_effect=ioctl), \
                 patch.object(DESKTOP.os, 'close', side_effect=lambda fd: calls.append(('close', fd))):
                with self.assertRaisesRegex(RuntimeError, 'Display restoration failed'):
                    DESKTOP.restore_display(10, 11, 12, 0, 1, mode, '1\n')
            self.assertEqual(mode.read_text(), '1\n')
        self.assertIn(('ioctl', 12, 0x5606, 1), calls)
        self.assertIn(('ioctl', 12, 0x5607, 1), calls)
        self.assertEqual(calls[-3:], [('close', 10), ('close', 11), ('close', 12)])


if __name__ == '__main__':
    unittest.main()
