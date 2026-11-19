"""Field-pack radio references remain separate from hardware upload plans."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shell'))
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
