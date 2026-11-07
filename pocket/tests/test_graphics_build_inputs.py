"""Graphical build inputs are repository source, not local captures or siblings."""
from pathlib import Path
import importlib.util,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'graphics'),str(ROOT/'shell')]

class GraphicsBuildInputs(unittest.TestCase):
 def test_packaged_font_conversion_preserves_catalog_glyphs(self):
  from font_preview import FontCatalog
  from extend_font import extend
  from cells import Font
  catalog=FontCatalog();row,original=catalog.glyphs('console-8x16')
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'console-font.psf';extend(catalog.root/row['file'],target)
   converted=Font(target)
   self.assertEqual((converted.width,converted.height),(8,16))
   for char,bits in original.items():self.assertEqual(converted.glyph(char),bits,char)
   for char in '┄┆':self.assertTrue(any(converted.glyph(char)))
 def test_build_and_launcher_do_not_refer_to_experimental_inputs(self):
  for name in ('build.py','build_nokia.py','gui.py','run.py','generate_room.py'):
   text=(ROOT/'graphics'/name).read_text()
   for old in ('mbx-driver/','outputs/','gpu-terminal-20261107','limactl'):
    self.assertNotIn(old,text,name)
 def test_required_local_native_sources_are_present(self):
  for name in ('cells.c','cells.h','present.c','present.h','desktop_context.h','desktop_input.c','room_pixels.c','mbx_cells.c','game.c','font_glyphs.m'):
   self.assertTrue((ROOT/'graphics/native'/name).is_file(),name)

if __name__=='__main__':unittest.main()
