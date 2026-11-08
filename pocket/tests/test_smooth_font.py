"""Smooth text keeps graphics glyphs exact and respects native layer bounds."""
from pathlib import Path
import ctypes as C,json,struct,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'graphics'),str(ROOT/'shell')]
class FontCoverage(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  config=ROOT/'build/graphics/frontend.json'
  if not config.exists():raise unittest.SkipTest('build graphics first')
  cls.config=json.loads(config.read_text())
 def test_font_contexts_do_not_mutate_shared_font_class(self):
  import cells
  from font_supplement import load
  base=cells.Font;console=load(self.config['font'])
  if not Path(self.config['font']).with_suffix('.smooth').exists():self.skipTest('CoreText font build unavailable')
  smooth=load(self.config['font'],'smooth');crisp=load(self.config['font'],'crisp')
  self.assertEqual(crisp.coverage,{});self.assertEqual(crisp.glyph('F'),smooth.glyph('F'))
  self.assertIs(cells.Font,base);self.assertEqual(console.coverage,{})
  self.assertEqual(set(smooth.coverage),{chr(n) for n in range(32,127)})
  for ch in '─│┌┐└┘▀▄█':self.assertEqual(smooth.glyph(ch),console.glyph(ch))
  f=smooth.coverage['F'];rows=[sum(f[y*8:y*8+8]) for y in range(16)];ink=[n for n in rows if n]
  self.assertGreater(sum(ink[:4]),sum(ink[-4:]))
  self.assertTrue(any(0<a<255 for a in f))
 def test_coverage_edges_transparency_and_destination_guards(self):
  lib=C.CDLL(self.config['gpu_library'])
  lib.pocket_pixel_layer_new.argtypes=[C.c_uint,C.c_uint];lib.pocket_pixel_layer_new.restype=C.c_void_p
  lib.pocket_pixel_layer_font_coverage.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint]
  lib.pocket_pixel_layer_build.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p,C.c_uint,C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_uint]
  lib.pocket_pixel_layer_over.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint]
  lib.pocket_pixel_layer_free.argtypes=[C.c_void_p]
  handle=lib.pocket_pixel_layer_new(1,1);self.assertTrue(handle)
  codes=(C.c_uint32*1)(65);font=(C.c_ubyte*16)();palette=(C.c_uint32*1)(65535)
  coverage=(C.c_ubyte*128)(*([0,32,64,96,128,160,224,255]*16));records=struct.pack('<IIQ',0,65,0)
  lib.pocket_pixel_canvas_size(8,16)
  try:
   self.assertEqual(lib.pocket_pixel_layer_font_coverage(handle,codes,coverage,1),0)
   bad=(C.c_uint32*1)(0x2588)
   self.assertEqual(lib.pocket_pixel_layer_font_coverage(handle,bad,coverage,1),-1)
   self.assertEqual(lib.pocket_pixel_layer_build(handle,records,16,codes,font,1,palette,1,0,1,255),0)
   pixels=(C.c_uint16*136)(*([0x55aa]*136));mask=(C.c_ubyte*128)(*([1]*128))
   self.assertEqual(lib.pocket_pixel_layer_over(C.byref(pixels,8),mask,handle,0,0,0,0,0),0)
   row=list(pixels)[4:12];self.assertEqual(row[0],0);self.assertEqual(row[-1],65535)
   self.assertGreater(len(set(row)),4);self.assertEqual(row,sorted(row))
   self.assertEqual(list(pixels)[:4],[0x55aa]*4);self.assertEqual(list(pixels)[-4:],[0x55aa]*4)
  finally:lib.pocket_pixel_layer_free(handle);lib.pocket_pixel_canvas_size(800,480)
if __name__=='__main__':unittest.main()
