"""Opaque UI text must not need a GL context or alter untouched cells."""
import ctypes as C
from pathlib import Path
import struct,unittest

LIB=Path(__file__).resolve().parents[1]/'build/graphics/renderer.so'

@unittest.skipUnless(LIB.exists(),'build with make graphics-native')
class NativeCellRaster(unittest.TestCase):
 def setUp(self):
  self.lib=C.CDLL(str(LIB))
  self.lib.pocket_mbx_open_cells.argtypes=[C.c_int,C.c_int];self.lib.pocket_mbx_open_cells.restype=C.c_void_p
  self.lib.pocket_mbx_blank.argtypes=[C.c_void_p]
  self.lib.pocket_mbx_stage_batch.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p,C.c_uint,C.c_void_p,C.c_uint,C.c_uint]
  self.lib.pocket_mbx_font_coverage.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint]
  self.lib.pocket_mbx_render.argtypes=[C.c_void_p,C.c_void_p]
  self.lib.pocket_mbx_jobs.argtypes=[C.c_void_p];self.lib.pocket_mbx_jobs.restype=C.c_uint
  self.lib.pocket_mbx_close.argtypes=[C.c_void_p]
  self.handle=self.lib.pocket_mbx_open_cells(0,1);self.assertTrue(self.handle)
  self.lib.pocket_mbx_blank(self.handle)
  self.canvas=(C.c_uint16*(800*480))()
  self.codes=(C.c_uint32*1)(65);self.bits=C.create_string_buffer(bytes([0x81]*16));self.palette=(C.c_uint32*1)(0xffff)
 def tearDown(self):self.lib.pocket_mbx_close(self.handle)
 def stage(self,index):
  raw=struct.pack('<IIQ',index,65,0)
  self.assertEqual(self.lib.pocket_mbx_stage_batch(self.handle,C.c_char_p(raw),len(raw),self.codes,self.bits,1,self.palette,1,0),1)
 def render(self):self.assertEqual(self.lib.pocket_mbx_render(self.handle,self.canvas),0)
 def test_exact_bitmap_and_zero_gpu_jobs(self):
  self.stage(101);self.render()
  for y in range(16):self.assertEqual(list(self.canvas[(16+y)*800+8:(16+y)*800+16]),[65535,0,0,0,0,0,0,65535])
  self.assertEqual(self.lib.pocket_mbx_jobs(self.handle),0)
 def test_retained_frame_changes_only_damaged_cells(self):
  self.stage(101);self.render();first=bytes(self.canvas);self.render();self.assertEqual(first,bytes(self.canvas))
  self.stage(102);self.render()
  changed=[i for i,(a,b) in enumerate(zip(first,bytes(self.canvas))) if a!=b]
  self.assertTrue(changed);self.assertTrue(all(16<=((i//2)%800)<24 and 16<=((i//2)//800)<32 for i in changed))
 def test_grayscale_coverage_is_mixed_into_opaque_background(self):
  coverage=C.create_string_buffer(bytes([128]*128))
  self.assertEqual(self.lib.pocket_mbx_font_coverage(self.handle,self.codes,coverage,1),0)
  self.stage(0);self.render();self.assertEqual(self.canvas[0],(16<<11)|(32<<5)|16)

if __name__=='__main__':unittest.main()
