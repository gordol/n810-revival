"""Native map lines clip to the viewport without glyph gaps or stray writes."""
from pathlib import Path
import ctypes as C
import subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class NativeMap(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temporary=tempfile.TemporaryDirectory(prefix='map-pixels-');cls.addClassCleanup(cls.temporary.cleanup)
  path=Path(cls.temporary.name)/'map.so'
  subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC',str(ROOT/'graphics/native/map_pixels.c'),'-lm','-o',str(path)],check=True)
  cls.lib=C.CDLL(str(path));cls.lib.pocket_map_lines.argtypes=[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_uint]
 def test_clipped_diagonal_and_rejected_nonfinite_input(self):
  out=(C.c_uint16*72)(*([0x5aa5]*72));pixels=C.byref(out,8)
  lines=(C.c_double*8)(-100,-100,100,100,-200,7,200,7)
  self.assertEqual(self.lib.pocket_map_lines(pixels,64,8,8,lines,2,0xffff),0)
  for y in range(8):self.assertEqual(out[4+y*8+y],0xffff)
  self.assertEqual(list(out)[60:68],[0xffff]*8)
  self.assertEqual(list(out)[:4],[0x5aa5]*4);self.assertEqual(list(out)[-4:],[0x5aa5]*4)
  before=list(out);bad=(C.c_double*4)(0,0,float('nan'),1)
  self.assertEqual(self.lib.pocket_map_lines(pixels,64,8,8,bad,1,0),-1);self.assertEqual(list(out),before)
  self.assertEqual(self.lib.pocket_map_lines(pixels,63,8,8,lines,2,0),-1);self.assertEqual(list(out),before)
if __name__=='__main__':unittest.main()
