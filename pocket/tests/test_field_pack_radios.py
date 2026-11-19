"""Field-pack radio references remain separate from hardware upload plans."""
from pathlib import Path
import sys
import tempfile
import unittest
import unittest.mock
from types import SimpleNamespace

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

    def test_malformed_csv_is_reported_without_aborting_radio_manager_startup(self):
        from radio_manager import RadioManager
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=root/'uv-pro/broken.csv'
            path.parent.mkdir()
            path.write_text('title,rx_freq,tx_freq,tx_sub_audio,bandwidth,rx_modulation,tx_dis,tx_modulation,tx_power,rx_sub_audio,scan,talk around,pre_de_emph_bypass,sign,mute\n'+
                            'Test,1,1,0,12500,0,1,0,L,0,1,0,0,0,0,extra\n')
            with unittest.mock.patch.dict('os.environ',{'POCKET_FIELD_PACK':str(root)}):
                manager=RadioManager(SimpleNamespace())
            self.assertEqual(manager.field_groups,[])
            self.assertIn('Invalid column count in broken.csv',manager.message)


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
            mac_uvpro._recover_pending(radio, device)
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

    def test_pending_recovery_restores_and_clears_verified_state(self):
        import json
        import mac_uvpro
        radio = self.Radio()
        original = (radio.bank, radio.settings, radio.beacon)
        radio.bank = 1
        radio.settings = b'\x55' * 22
        radio.beacon = radio.beacon[:1] + bytes([radio.beacon[1] & ~0x10]) + radio.beacon[2:]
        with tempfile.TemporaryDirectory() as directory:
            device = Path(directory)
            (device / 'restore-pending.json').write_text(json.dumps({
                'bank': original[0], 'settings': original[1].hex(), 'beacon': original[2].hex(),
            }))
            with unittest.mock.patch.object(mac_uvpro.time, 'sleep'):
                mac_uvpro._recover_pending(radio, device)
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

    def test_direct_mac_rejects_remote_sources_and_explicit_endpoints(self):
        import mac_uvpro

        class LocalSource:
            local_selected = True

        with unittest.mock.patch.dict('os.environ', {'POCKET_FIELD_PACK': '/tmp/field-pack'}), \
                unittest.mock.patch('mac_tray.enabled', return_value=True):
            self.assertTrue(mac_uvpro.enabled(LocalSource()))
            self.assertFalse(mac_uvpro.enabled(object()))
            self.assertFalse(mac_uvpro.enabled(LocalSource(), '/run/radio-control.sock'))

    def test_terminal_backspace_erases_upload_destination(self):
        from types import SimpleNamespace
        from radio_manager import RadioManager
        for key in ('\x7f', '\b'):
            manager = object.__new__(RadioManager)
            manager.__dict__.update(
                page=6, bank=0, index=0, field_groups=[('Bank', [(None, None, None, None)])],
                field_target='12', state=SimpleNamespace(source=None, read_client=None,direct_mac=lambda:False),
                bank_name_editor=None,
            )
            self.assertTrue(manager.key(key))
            self.assertEqual(manager.field_target, '1')


class UploadLocationGuard(unittest.TestCase):
    def test_enabled_reporting_channel_is_not_overwritten(self):
        import json
        import uvpro_bank
        layouts = json.loads((Path(__file__).resolve().parents[1] / 'shell/vendor/packet-console/radio-read-layouts.json').read_bytes())

        def pack(layout, values):
            value = total = 0
            for name, width, _ in layout:
                value = (value << width) | values.get(name, 0)
                total += width
            return value.to_bytes(total // 8, 'big')

        settings = pack(layouts['Settings'], {'auto_share_loc_ch': 1})
        beacon = pack(layouts['BSSSettings'], {'should_share_location': 1, 'location_share_interval': 10})
        status = (0x80000000).to_bytes(4, 'big')
        sent = []

        def download(*args):
            if False:
                yield None
            return {'channels': 2}

        job = uvpro_bank.upload(
            {'bank': 0, 'channels': [['N0CALL', 146800000, 146800000, 0, 0, 0, 0]]},
            'AA:BB', Path('/tmp/backups'), lambda *args: None,
        )
        reply = None
        with unittest.mock.patch.object(uvpro_bank, 'download', download):
            with self.assertRaisesRegex(ValueError, 'Automatic location reporting uses this channel'):
                while True:
                    try:
                        command, payload, *_ = job.send(reply)
                    except StopIteration:
                        break
                    sent.append(command)
                    reply = {20: status, 10: settings, 33: beacon, 13: bytes(25)}[command]
        self.assertNotIn(14, sent)
