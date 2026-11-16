"""Fresh image input must come from the source-backed ARM build."""
import tempfile
import unittest
import importlib.util
from pathlib import Path

from first_boot import configure_first_boot, configure_keyboard, configure_power_indicators


class KeyboardStaging(unittest.TestCase):
    def test_first_boot_keeps_power_key_from_shutting_down_and_orders_keyboard(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'root'
            for name in ('n810-fn-remap', 'n810-backlightd'):
                arm = Path(folder) / name
                arm.write_bytes(b'\x7fELF\x01' + b'\0' * 13 + b'\x28\0' + b'\0' * 16)
            configure_first_boot(root, Path(folder) / 'n810-fn-remap',
                                 Path(folder) / 'n810-backlightd')
            logind = (root / 'etc/systemd/logind.conf.d/10-n810-power-key.conf').read_text()
            self.assertEqual((root / 'etc/default/chrony').read_text(), 'DAEMON_OPTS="-4 -F 0"\n')
            self.assertIn('HandlePowerKey=ignore', logind)
            self.assertIn('HandlePowerKeyLongPress=ignore', logind)
            ssh = (root / 'etc/systemd/system/ssh.service.d/99-n810-host-key.conf').read_text()
            self.assertIn('ssh-keygen -q -t ed25519', ssh)
            self.assertNotIn('ssh-keygen -A', ssh)
            self.assertFalse((root / 'etc/systemd/system/ssh.service.d/10-generate-host-keys.conf').exists())
            keyboard = (root / 'etc/systemd/system/n810-keyboard.service').read_text()
            self.assertIn('Before=getty@tty1.service pocket-desktop.service', keyboard)
            self.assertTrue((root / 'etc/systemd/system/multi-user.target.wants/n810-display-keys.service').is_symlink())
            self.assertTrue((root / 'usr/local/sbin/n810-power-overlay').is_file())
    def test_stages_internal_keyboard_and_enables_units(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'root'
            arm = Path(folder) / 'n810-fn-remap'
            arm.write_bytes(b'\x7fELF\x01' + b'\0' * 13 + b'\x28\0' + b'\0' * 16)
            configure_keyboard(root, arm)
            self.assertEqual((root / 'usr/local/sbin/n810-fn-remap').read_bytes(), arm.read_bytes())
            self.assertTrue((root / 'usr/local/sbin/n810-keyboard').exists())
            self.assertIn('control keycode 103', (root / 'usr/local/share/n810/n810-console.map').read_text())
            for name in ('n810-fn-remap.service', 'n810-keyboard.service'):
                self.assertTrue((root / 'etc/systemd/system/multi-user.target.wants' / name).is_symlink())
            configure_keyboard(root)

    def test_rejects_missing_or_wrong_architecture(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'root'
            with self.assertRaisesRegex(ValueError, 'missing'):
                configure_keyboard(root)
            host = Path(folder) / 'host'
            host.write_bytes(b'\x7fELF\x02' + b'\0' * 30)
            with self.assertRaisesRegex(ValueError, '32-bit ARM'):
                configure_keyboard(root, host)

    def test_power_indicators_follow_tracked_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'root'
            arm = Path(folder) / 'n810-backlightd'
            arm.write_bytes(b'\x7fELF\x01' + b'\0' * 13 + b'\x28\0' + b'\0' * 16)
            configure_power_indicators(root, arm)
            self.assertEqual((root / 'usr/local/sbin/n810-backlightd').read_bytes(), arm.read_bytes())
            self.assertTrue((root / 'usr/local/sbin/n810-powerd').is_file())
            self.assertTrue((root / 'usr/local/sbin/n810-ledd').is_file())
            for name in ('n810-powerd.service', 'n810-ledd.service', 'n810-backlightd.service'):
                self.assertTrue((root / 'etc/systemd/system/multi-user.target.wants' / name).is_symlink())
            configure_power_indicators(root)

    def test_internal_root_stages_og_idle_policy_with_one_key_owner(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'root'
            arm = Path(folder) / 'arm'
            arm.write_bytes(b'\x7fELF\x01' + b'\0' * 13 + b'\x28\0' + b'\0' * 16)
            configure_power_indicators(root, arm, arm)
            self.assertEqual((root / 'usr/local/sbin/n810-wake').read_bytes(), arm.read_bytes())
            self.assertTrue((root / 'etc/systemd/system/multi-user.target.wants/n810-wake.service').is_symlink())
            lock = (root / 'etc/n810-idle.conf').read_text()
            self.assertNotIn('lock_only=1', lock)
            self.assertIn('idle_enabled=1', lock)
            self.assertIn('dim_seconds=60', lock)
            self.assertIn('off_seconds=300', lock)
            wants = root / 'etc/systemd/system/multi-user.target.wants'
            self.assertFalse((wants / 'n810-display-keys.service').exists())
            self.assertTrue((wants / 'n810-displayd.service').is_symlink())
            self.assertTrue((wants / 'n810-boot-mode.service').is_symlink())
            for helper in ('n810-mode', 'n810-bootreason', 'n810-cpu-policy', 'n810-displayd'):
                self.assertTrue((root / 'usr/local/sbin' / helper).stat().st_mode & 0o111)
            self.assertIn('topoff', (root / 'usr/local/sbin/n810-power-overlay').read_text())
            configure_power_indicators(root)

    def test_lcd_brightness_keys_are_bounded(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/n810-display-keys.py'
        spec = importlib.util.spec_from_file_location('n810_display_keys', script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            backlight = Path(folder)
            (backlight / 'max_brightness').write_text('20\n')
            (backlight / 'brightness').write_text('10\n')
            module.brightness_change(backlight, module.KEY_BRIGHTNESSUP)
            self.assertEqual((backlight / 'brightness').read_text(), '12\n')
            (backlight / 'brightness').write_text('1\n')
            module.brightness_change(backlight, module.KEY_BRIGHTNESSDOWN)
            self.assertEqual((backlight / 'brightness').read_text(), '1\n')


if __name__ == '__main__':
    unittest.main()
