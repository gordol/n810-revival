from pathlib import Path
import sys,json,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'graphics'))
from cells import Font
class PixelFont(unittest.TestCase):
 def test_explicit_ui_glyphs_preserve_original_font(self):
  config=json.loads((ROOT/'build/graphics/frontend.json').read_text());font=Font(config['font']);old={c:font.glyph(c) for c in font.mapping}
  font.add_desktop_glyphs()
  for char,bits in old.items():self.assertEqual(font.glyph(char),bits)
  for char in '‹›┄┆':self.assertEqual(len(font.glyph(char)),16);self.assertTrue(any(font.glyph(char)))
  self.assertNotEqual(font.glyph('┄'),font.glyph('─'));self.assertNotEqual(font.glyph('┆'),font.glyph('│'))
  with self.assertRaises(ValueError):font.glyph('\U0010ffff')
if __name__=='__main__':unittest.main()
