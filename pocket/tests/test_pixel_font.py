from pathlib import Path
import sys,json,unittest,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'graphics'))
from cells import Font
class PixelFont(unittest.TestCase):
 def test_explicit_ui_glyphs_preserve_original_font(self):
  if not (ROOT/'build/graphics/frontend.json').is_file():self.skipTest('run make graphics-native first')
  config=json.loads((ROOT/'build/graphics/frontend.json').read_text());font=Font(config['font']);old={c:font.glyph(c) for c in font.mapping}
  font.add_desktop_glyphs()
  for char,bits in old.items():self.assertEqual(font.glyph(char),bits)
  for char in '‹›┄┆⇧┃':self.assertEqual(len(font.glyph(char)),16);self.assertTrue(any(font.glyph(char)))
  self.assertNotEqual(font.glyph('┄'),font.glyph('─'));self.assertNotEqual(font.glyph('┆'),font.glyph('│'))
  with self.assertRaises(ValueError):font.glyph('\U0010ffff')

class SettingsGlyphs(unittest.TestCase):
 def test_settings_symbols_exist_without_native_build(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'fixture.psf'
   # A minimal PSF1 with explicit horizontal and vertical strokes.
   path.write_bytes(b'\x36\x04\x02\x10'+bytes([0x18])*4096+
                    b''.join((ord('─') if i==0 else ord('│') if i==1 else i).to_bytes(2,'little')+b'\xff\xff' for i in range(256)))
   font=Font(path);original=dict(font.mapping);font.add_desktop_glyphs()
   for char in '⇧┃‹›┄┆':
    self.assertEqual(len(font.glyph(char)),16);self.assertTrue(any(font.glyph(char)))
   self.assertEqual({c:font.mapping[c] for c in original},original)
   with self.assertRaises(ValueError):font.glyph('\U0010ffff')

if __name__=='__main__':unittest.main()
