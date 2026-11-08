"""Doom's graphical path validates its ABI before launch and bounds native writes."""
from pathlib import Path
import ctypes as C
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'graphics'),str(ROOT/'shell')]
from doom_pixels import Engine,engine_module

class DoomPixels(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temporary=tempfile.TemporaryDirectory(prefix='doom-bridge-test-')
  cls.addClassCleanup(cls.temporary.cleanup)
  output=Path(cls.temporary.name)/'bridge.so'
  subprocess.run(['cc','-std=c11','-shared','-fPIC',str(ROOT/'shell/apps/doom-app/bridge.c'),'-o',str(output)],check=True)
  cls.lib=C.CDLL(str(output));cls.lib.convert_pixels.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t]+[C.c_uint]*6
 def test_native_letterbox_colors_and_write_guards(self):
  frame=engine_module.Frame()
  for y in range(200):
   for x in range(320):frame.pixels[y*320+x]=0xff0000 if x<160 else 0x00ff00
  output=(C.c_uint16*40)(*([0x5aa5]*40))
  self.assertEqual(self.lib.convert_pixels(C.byref(frame),C.byref(output,8),32,8,4,2,1,4,2),0)
  self.assertEqual(list(output)[:4],[0x5aa5]*4);self.assertEqual(list(output)[-4:],[0x5aa5]*4)
  self.assertEqual(list(output)[4:12],[0]*8)
  self.assertEqual(list(output)[12:20],[0,0,0xf800,0xf800,0x07e0,0x07e0,0,0])
  before=list(output)
  for dimensions in [(8,4,7,1,2,2),(8,4,2,3,4,2),(4097,4,0,0,1,1),(8,4,0,0,0,1)]:
   self.assertEqual(self.lib.convert_pixels(C.byref(frame),C.byref(output,8),32,*dimensions),-1)
   self.assertEqual(list(output),before)
 def test_old_bridge_rejected_before_process_or_frame_allocation(self):
  class Symbol:
   def __call__(self):return C.sizeof(engine_module.Frame)
  class OldBridge:
   bridge_now_ns=Symbol();frame_size=Symbol();snapshot=Symbol();convert=Symbol()
  with tempfile.TemporaryDirectory() as state,patch('ctypes.CDLL',return_value=OldBridge()),patch.object(engine_module.subprocess,'Popen') as spawn:
   with self.assertRaisesRegex(ValueError,'make doom'):Engine(None,Path(state),resource_root=Path(state))
   spawn.assert_not_called();self.assertEqual(list(Path(state).iterdir()),[])

if __name__=='__main__':unittest.main()
