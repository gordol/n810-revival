"""Exercise bootloader capture without rebooting or writing a physical device."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import ab_capture
import ab_install


class Listener(unittest.TestCase):
    def test_listener_starts_before_reboot_and_survives_ssh_disconnect(self):
        events = []
        def read(port):
            events.append(('scan', port))
            return '173' if len(events) == 4 else None
        child = MagicMock()
        child.poll.return_value = 255
        def reboot():
            events.append('reboot')
            child.__enter__.return_value = child
            return child
        with patch.object(ab_capture, 'current_instance', read):
            self.assertEqual(ab_capture.capture(15, reboot), '173')
        self.assertEqual(events, [('scan', 15), 'reboot', ('scan', 15), ('scan', 15)])

    def test_held_bootloader_and_missed_window(self):
        reboot = MagicMock()
        with patch.object(ab_capture, 'current_instance', return_value='25'):
            self.assertEqual(ab_capture.capture(15, reboot), '25')
        reboot.assert_not_called()
        with patch.object(ab_capture, 'current_instance', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'Hold Home/Swap'):
                ab_capture.capture(15, reboot, timeout=0)

    def test_mac_port_and_update_pid_must_match_the_same_node(self):
        tree = [{'IORegistryEntryChildren': [
            dict(locationID=12, idVendor=1057, idProduct=261, sessionID=99),
            dict(locationID=15, idVendor=1057, idProduct=262, sessionID=9)]}]
        self.assertIsNone(ab_capture.mac_instance(tree, 15))
        self.assertEqual(ab_capture.mac_instance(tree, 12), '99')

    def test_linux_port_uses_current_bus_and_address(self):
        with tempfile.TemporaryDirectory() as directory:
            port = Path(directory)
            for name, value in [('idVendor', '0421'), ('idProduct', '0105'),
                                ('busnum', '002'), ('devnum', '089')]:
                (port/name).write_text(value)
            self.assertEqual(ab_capture.linux_instance(port), '2:89')
            (port/'idProduct').write_text('0096')
            self.assertIsNone(ab_capture.linux_instance(port))


class FlashReceipt(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.kit = Path(folder.name)
        (self.kit/'AB.json').write_text('{}')
        self.path = self.kit/'RECOVERY-INSTALL.json'
        self.receipt = dict(state='recovery_written', readback_verified=True,
                            kit_sha256=ab_install.digest(self.kit/'AB.json'), usb_location=15)
        self.path.write_text(json.dumps(self.receipt))
        (self.kit/'SD-INSTALL.json').write_text(json.dumps(self.receipt))
        pin = Path(ab_install.__file__).resolve().parents[1]/'flasher/usb-host.patch'
        (self.kit/'BUILD.json').write_text(json.dumps({
            'identity': {'usb_host_patch_sha256': ab_install.digest(pin)}}))
        for name, value in [('_flasher_command', []), ('port_from_receipt', 15), ('capture', '91')]:
            patcher = patch.object(ab_install, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_flash(self):
        return ab_install.flash_recovery(self.kit, self.kit/'flasher', 'key', 'host')

    def test_storage_identity_mismatch_blocks_reboot(self):
        with patch.object(ab_install, 'probe', return_value={'cid': 'wrong'}), \
                patch.object(ab_install.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(ValueError, 'MMC identity'):
                ab_install.reboot_installer(self.kit, 'key', 'host', {'cid': 'expected'})
        launch.assert_not_called()

    def test_verified_ssh_reboot_rechecks_running_installer(self):
        identity = dict(node='mmcblk0', cid='a'*32, sectors=3932160)
        with patch.object(ab_install, 'probe', return_value=identity), \
                patch.object(ab_install, 'environment_guard', return_value='test -f /fixture\n'), \
                patch.object(ab_install, 'ssh', return_value=['ssh', 'fixture']), \
                patch.object(ab_install.subprocess, 'Popen') as launch:
            ab_install.reboot_installer(self.kit, 'key', 'host', identity)
        command = launch.call_args.args[0][-1]
        self.assertIn('/sys/block/mmcblk0/device/cid', command)
        self.assertIn(identity['cid'], command)
        self.assertLess(command.index('/fixture'), command.index('reboot -f'))

    def test_written_kernel_with_lost_ack_is_not_flashed_twice(self):
        message = 'Flashing image...\nDone\nRebooting device...\nError: NOLO_REBOOT failed'
        with patch.object(ab_install, '_run_flasher', side_effect=RuntimeError(message)):
            with self.assertRaisesRegex(RuntimeError, 'reboot acknowledgement failed'):
                self.run_flash()
        self.assertEqual(json.loads(self.path.read_text())['state'], 'kernel_flashed_reboot_unconfirmed')

    def test_success_binds_write_and_prevents_repeat(self):
        with patch.object(ab_install, '_run_flasher', return_value='Flashing image...\nDone\nRebooting device...') as run:
            self.assertEqual(self.run_flash()['state'], 'recovery_kernel_flashed')
            self.assertEqual(run.call_args.args[1][:2], ['-P', '91'])
            with self.assertRaisesRegex(ValueError, 'already attempted'):
                self.run_flash()
            run.assert_called_once()

    def test_miss_is_retryable_but_interrupted_write_is_not(self):
        with patch.object(ab_install, '_run_flasher', side_effect=RuntimeError('POCKET_CAPTURE_MISSED')):
            with self.assertRaisesRegex(RuntimeError, 'Hold Home/Swap'):
                self.run_flash()
        self.assertEqual(json.loads(self.path.read_text()), self.receipt)
        with patch.object(ab_install, '_run_flasher', side_effect=RuntimeError('lost USB')):
            with self.assertRaisesRegex(RuntimeError, 'lost USB'):
                self.run_flash()
        self.assertEqual(json.loads(self.path.read_text())['state'], 'kernel_flash_in_progress')

    def test_failed_receipt_is_rejected_before_capture(self):
        self.path.write_text(json.dumps(dict(self.receipt, readback_verified=False)))
        with self.assertRaisesRegex(ValueError, 'verified write receipts'):
            self.run_flash()
        ab_install.capture.assert_not_called()
