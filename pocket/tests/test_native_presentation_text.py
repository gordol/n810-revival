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
 def test_disabled_path_keeps_one_buffer_and_one_marks_pass(self):
  import map_pixels
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as folder:
   library=Path(folder)/'map.so'
   subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC',str(ROOT/'graphics/native/map_pixels.c'),'-lm','-o',str(library)],check=True)
   lib=C.CDLL(str(library))
   lib.pocket_map_base.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p,C.c_uint,C.c_uint]
   lib.pocket_map_marks.argtypes=[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_void_p]
   class Plane:
    base=[('█',(1<<48)|(0xffffff<<24)|0x101010)]*4
    overlay={0:('A',(1<<48)|(0xffffff<<24)|0x101010)}
   for enabled,expected in ((False,1),(True,2)):
    app=map_pixels.View.__new__(map_pixels.View);app.lib=lib;app.presentation_text=enabled
    app.font=NS(glyph=lambda ch:bytes([255])*16)
    app.base=NS(renderer=NS(engine=NS(),module=NS(Viewport=lambda *args:NS())))
    projection=NS(center=(0,0),span=1)
    with patch.object(map_pixels,'segments',return_value=[]),patch.object(lib,'pocket_map_marks',wraps=lib.pocket_map_marks) as marks:
     normal,deferred,labels=app.build((0,0,2,2,Plane()),projection)
     self.assertEqual(marks.call_count,expected);self.assertEqual(len(labels),1)
     if enabled:self.assertIsNot(normal,deferred);self.assertNotEqual(normal[0],deferred[0])
     else:self.assertIs(normal,deferred)

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
