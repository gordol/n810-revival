import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('symbols', Path(__file__).with_name('n810-aprs-symbols.py'))
symbols = importlib.util.module_from_spec(spec)
spec.loader.exec_module(symbols)


class SymbolDisplay(unittest.TestCase):
    def test_tables_are_distinct(self):
        self.assertEqual(symbols.display_symbol('/', 'j')['name'], 'Jeep')
        self.assertEqual(symbols.display_symbol('\\', 'j')['name'], 'Work zone')
        self.assertEqual(symbols.display_symbol('/', '>')['name'], 'Car')

    def test_overlay_retains_identity_without_inventing_meaning(self):
        for overlay in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789':
            row = symbols.display_symbol(overlay, '#')
            self.assertEqual((row['table'], row['code'], row['base_table'], row['overlay']), (overlay, '#', '\\', overlay))
            self.assertEqual(row['name'], 'Digipeater')
        self.assertIsNone(symbols.display_symbol('\\', '#')['overlay'])

    def test_unknown_and_invalid(self):
        for table, code in [('/', 'D'), ('\\', 'B'), ('a', '#'), ('', '#'), (None, '#'), ('/', '\n'), ('/', 'xx'), ('/', None)]:
            row = symbols.display_symbol(table, code)
            self.assertFalse(row['known'])
            self.assertEqual(row['glyph'], '?')
            self.assertEqual((row['table'], row['code']), (table, code))

    def test_glyphs_exist_in_bundled_font(self):
        import struct
        font = Path(__file__).resolve().parents[1] / 'console-icons/n810-ui-512.psf'
        data = font.read_bytes()
        magic, version, header_size, flags, count, char_size, height, width = struct.unpack_from('<8I', data)
        self.assertEqual(magic, 0x864ab572)
        self.assertTrue(flags & 1, 'Font must contain a Unicode table')
        entries = data[header_size + count * char_size:].split(b'\xff')
        self.assertEqual(len(entries), count + 1)
        repertoire = set()
        for entry in entries[:-1]:
            # PSF2 FE introduces multi-character sequences, not standalone glyphs.
            repertoire.update(entry.split(b'\xfe', 1)[0].decode('utf-8'))
        for table in (symbols.PRIMARY, symbols.ALTERNATE):
            for code, (glyph, name) in table.items():
                self.assertIn(glyph, repertoire, (code, name, glyph))
        self.assertIn('?', repertoire)

    def test_all_entries_are_single_cell_safe_and_independent(self):
        import unicodedata
        for table in ('/', '\\'):
            for number in range(33, 127):
                row = symbols.display_symbol(table, chr(number))
                self.assertEqual(len(row['glyph']), 1)
                self.assertNotIn(unicodedata.east_asian_width(row['glyph']), ('W', 'F'))
                self.assertFalse(unicodedata.combining(row['glyph']))
                self.assertEqual(row['glyph_kind'], 'terminal_approximation')
        first = symbols.display_symbol('/', '>')
        first['name'] = 'changed'
        self.assertEqual(symbols.display_symbol('/', '>')['name'], 'Car')


if __name__ == '__main__':
    unittest.main()
