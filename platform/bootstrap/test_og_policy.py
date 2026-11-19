"""Check source-backed OG boot metadata and guarded CPU selection on fake sysfs."""
from pathlib import Path
import importlib.machinery
import importlib.util
import struct
import json
import hashlib
from build_internal_image import checked_package
import tempfile
import unittest
from unittest.mock import patch


def load(name):
    source = Path(__file__).resolve().parents[1] / 'scripts' / name
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), str(source))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(module)
    return module


class OGPolicyTest(unittest.TestCase):
    def test_boot_reason_records_are_bounded_and_unambiguous(self):
        decode = load('n810-bootreason').decode
        record = struct.pack('<HH', 0x4f80, 12) + b'charger' + bytes(5)
        self.assertEqual(decode(record), 'charger')
        self.assertIsNone(decode(b''))
        for invalid in (record + record, record[:-1], record + b'x', bytes(16385),
                        struct.pack('<HH', 0x4f80, 12) + b'BAD' + bytes(9)):
            with self.subTest(invalid=invalid[:20]):
                with self.assertRaises(ValueError):
                    decode(invalid)

    def test_internal_image_rejects_stale_kernel_boot_policy(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder)
            config = package / 'kernel.config'
            config.write_text('CONFIG_CPU_FREQ_DEFAULT_GOV_POWERSAVE=y\nCONFIG_CPU_FREQ_GOV_POWERSAVE=y\n')
            report = {'root_device': 'PARTUUID=12345678-01', 'cpu_boot_governor': 'powersave',
                      'files': {'kernel.config': hashlib.sha256(config.read_bytes()).hexdigest()}}
            (package / 'BUILD.json').write_text(json.dumps(report))
            self.assertEqual(checked_package(package)[1], '12345678')
            report['cpu_boot_governor'] = 'performance'
            (package / 'BUILD.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError, 'powersave'):
                checked_package(package)

    def test_explicit_performance_selection_restores_display(self):
        cpu = load('n810-cpu-policy')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            values = {'scaling_available_frequencies': '330000 400000 480000',
                      'scaling_available_governors': 'powersave performance',
                      'scaling_cur_freq': '330000', 'scaling_min_freq': '330000',
                      'scaling_max_freq': '400000', 'scaling_governor': 'powersave'}
            for name, value in values.items():
                (root / name).write_text(value)
            mode, overlay = root / 'mode', root / 'overlay'
            mode.write_text('1'); overlay.write_text('1')
            result = cpu.select('performance', root, mode, overlay)
            self.assertEqual(result['maximum_khz'], 480000)
            self.assertEqual(result['governor'], 'performance')
            self.assertEqual(mode.read_text().strip(), '1')
            self.assertEqual(overlay.read_text().strip(), '1')
            before = cpu.status(root)
            wrong = dict(before, governor='powersave')
            with patch.object(cpu, 'status', side_effect=[before, wrong]):
                with self.assertRaises(OSError):
                    cpu.select('performance', root, mode, overlay)
            self.assertEqual(cpu.status(root), before)
            self.assertEqual(mode.read_text().strip(), '1')
            self.assertEqual(overlay.read_text().strip(), '1')
