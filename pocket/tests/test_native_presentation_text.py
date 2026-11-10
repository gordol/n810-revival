# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native Mac glyph density and scene fallback, without services or a device."""
from pathlib import Path
from types import SimpleNamespace as NS
import ctypes as C
import shutil,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'graphics'))
from presentation_text import supported

class ScenePolicy(unittest.TestCase):
 def test_unchanged_bitmap_mode_needs_no_native_presentation_api(self):
  from mbx import Renderer
  renderer=Renderer.__new__(Renderer);renderer.deferred_text=False
  self.assertFalse(renderer.defer_text(False))

 def host(self,windows,**kw):
  return NS(windows=[NS(name=name) for name in windows],shown=lambda w:True,launcher_lines=[],drag=None,**kw)
 def test_raw_rgb565_capture_keeps_complete_text(self):
  self.assertFalse(supported(self.host(['Details']),[],raw_capture=True))
 def test_ordinary_translucent_cells_are_supported(self):
  host=self.host(['Map','Details']);host.window_opacity=.88;host.window_fill=False
  self.assertTrue(supported(host,[]))
 def test_single_pixel_view_chrome_supported_but_upper_windows_fall_back(self):
  app=NS(name='Doom');host=self.host(['Connections','Doom'])
  self.assertTrue(supported(host,[app]))
  host.windows.append(NS(name='Translucent details'));host.window_opacity=.88
  self.assertFalse(supported(host,[app]));host.window_fill=False
  self.assertFalse(supported(host,[app]))
 def test_launcher_drag_and_multiple_images_keep_complete_scene(self):
  app=NS(name='Map');host=self.host(['Map'])
  host.launcher_lines=['menu'];self.assertFalse(supported(host,[app]))
  host.launcher_lines=[];host.drag=True;self.assertFalse(supported(host,[app]))
  host.drag=None;self.assertFalse(supported(host,[app,NS(name='Doom')]))


class MapTextCapability(unittest.TestCase):
 def test_semantic_annotations_are_one_shared_mark_set(self):
  from array import array
  from map_pixels import View
  class Plane:
   base=[('┼',0)]*4
   overlay={0:('A',(1<<48)|(0xffffff<<24))}
  features=NS(terrain=array('I',[0]*8),sample_width=2,sample_height=4,vectors=(),labels={})
  surface=NS(unavailable_reason='',viewport=lambda:object(),features=lambda *args:features,overlay_vectors=())
  scene=View(None,None).build((0,0,2,2,Plane()),surface)
  self.assertEqual([(m.index,m.ch) for m in scene.marks],[(0,ord('A'))])
  self.assertEqual(len(scene.terrain),8)

@unittest.skipUnless(sys.platform=='darwin' and shutil.which('sdl2-config'),'Mac CoreText/SDL test')
class NativeText(unittest.TestCase):
 def test_native_1x_2x_antialiasing_clipping_and_buffer_bounds(self):
  with tempfile.TemporaryDirectory() as folder:
   target=Path(folder)/'native-text'
   flags=subprocess.check_output(['sdl2-config','--cflags','--libs'],text=True).split()
   subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-I'+str(ROOT/'graphics/native'),str(ROOT/'graphics/native/test_native_text.c'),str(ROOT/'graphics/native/native_text.m'),'-framework','CoreText','-framework','CoreGraphics','-framework','CoreFoundation',*flags,'-o',str(target)],check=True)
   result=subprocess.run([str(target)],capture_output=True,text=True,check=True)
   self.assertIn('1x:',result.stdout);self.assertIn('2x:',result.stdout)

if __name__=='__main__':unittest.main()
