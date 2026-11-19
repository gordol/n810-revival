"""Field-pack radio references remain separate from hardware upload plans."""
from pathlib import Path
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shell'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shell/owner-service"))
from field_banks import load


class FieldPackRadios(unittest.TestCase):
    def test_model_specific_references_and_legacy_pack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in ('radios/X6100', 'belka'):
                path = root / folder / 'frequencies.csv'
                path.parent.mkdir(parents=True)
                path.write_text('station,hz,mode,bank,tx_hz\nN0CALL,55555000,USB,Local,55555000\n')
            groups = dict(load(root))
            title, hz, detail, plan = groups['X6100 Local'][0]
            self.assertEqual((title, hz, detail, plan), ('N0CALL', 55555000, 'USB · TX 55.555 MHz', None))
            self.assertIn('Belka Local', groups)
            modern = root / 'radios/Belka/frequencies.csv'
            modern.parent.mkdir()
            modern.write_text('station,hz,mode\nN0CALL,55555000,AM\n')
            groups = dict(load(root))
            self.assertNotIn('Belka Local', groups)
            self.assertEqual(groups['Belka Frequencies'][0][2:], ('AM', None))


class MacRadioRecovery(unittest.TestCase):
    class Radio:
        def __init__(self):
            self.bank = 0
            self.settings = bytes(range(22))
            self.beacon = b'\x02\x10' + bytes(48)
            self.name = b'\xb0\xa1'
            self.dead = False

        def request(self, command, payload):
            if self.dead:
                raise ConnectionError('Bluetooth lost')
            if command == 20:
                return (0x80000000 | self.bank << 6).to_bytes(4, 'big')
            if command == 60:
                self.bank = payload[0]
            elif command == 11:
                self.settings = payload
            elif command == 34:
                self.beacon = payload
            elif command == 59:
                self.name = payload[1:]
            if command == 10:
                return self.settings
            if command == 33:
                return self.beacon
            if command == 73:
                return payload + self.name + b'\0'
            return b''

    def run_download(self, radio, device, die_on):
        import contextlib
        import json
        import mac_uvpro
        import uvpro_bank

        @contextlib.contextmanager
        def connection():
            yield radio, device, 'AA:BB'

        def read_bank(index, address):
            if index == die_on:
                radio.dead = True
            yield 10, b''
            return {'bank_names': ['a', 'b'], 'banks': [{'index': index}]}

        owner = type('Owner', (), {'atomic': staticmethod(lambda path, value: Path(path).write_text(json.dumps(value)))})
        with unittest.mock.patch.object(mac_uvpro, 'connection', connection), \
                unittest.mock.patch.object(mac_uvpro, 'enabled', return_value=True), \
                unittest.mock.patch.object(mac_uvpro, 'owner_module', return_value=owner), \
                unittest.mock.patch.object(mac_uvpro.time, 'sleep'), \
                unittest.mock.patch.object(uvpro_bank, 'read_bank', read_bank):
            return mac_uvpro.download_all(lambda text: None)

    def test_interrupted_download_is_recovered_on_reconnect(self):
        radio = self.Radio()
        original = (radio.bank, radio.settings, radio.beacon)
        with tempfile.TemporaryDirectory() as directory:
            device = Path(directory)
            with self.assertRaises(ConnectionError):
                self.run_download(radio, device, die_on=1)
            self.assertTrue((device / 'restore-pending.json').exists())
            self.assertNotEqual(radio.bank, original[0])
            radio.dead = False
            self.run_download(radio, device, die_on=None)
            self.assertEqual((radio.bank, radio.settings, radio.beacon), original)
            self.assertFalse((device / 'restore-pending.json').exists())

    def test_rename_accepts_existing_gbk_name(self):
        import mac_uvpro
        radio = self.Radio()
        owner = type('Owner', (), {'atomic': staticmethod(lambda path, value: None)})

        import contextlib

        @contextlib.contextmanager
        def connection():
            yield radio, Path('.'), 'AA:BB'

        with unittest.mock.patch.object(mac_uvpro, 'connection', connection), \
                unittest.mock.patch.object(mac_uvpro, 'owner_module', return_value=owner), \
                unittest.mock.patch.object(mac_uvpro, 'load_catalog', return_value=({}, {'bank_names': ['x', 'y']})):
            mac_uvpro.rename_bank(0, '\u554a', 'ABC')
        self.assertEqual(radio.name, b'ABC')
