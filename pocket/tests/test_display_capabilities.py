# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native scene selection preserves framebuffer presentation without SDL APIs."""
from array import array
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import ctypes as C,importlib.util,json,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'graphics'));sys.path.insert(0,str(ROOT/'shell'))
import display_context

class Capabilities(unittest.TestCase):
 def test_framebuffer_never_creates_sdl_context(self):
  platform=NS(display=NS(lib=NS()))
  with patch('framebuffer_scene.Context',return_value='framebuffer') as create,patch('gpu_scene.Context',side_effect=AssertionError('SDL loaded')):
   self.assertEqual(display_context.create(platform),'framebuffer');create.assert_called_once_with(platform)
 def test_sdl_capability_uses_native_scene(self):
  lib=NS(**{name:object() for name in ('pocket_scene_open','pocket_scene_map','pocket_scene_present')})
  context=NS(backend='metal');platform=NS(display=NS(lib=lib))
  with patch('gpu_scene.Context',return_value=context) as create:
   self.assertIs(display_context.create(platform),context);create.assert_called_once_with(platform)
 def test_headless_desktop_uses_sdl_context(self):
  context=NS(backend='metal')
  with patch('gpu_scene.Context',return_value=context):self.assertIs(display_context.create(NS(display=None)),context)

class FramebufferMap(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory(prefix='framebuffer-map-');cls.addClassCleanup(cls.tmp.cleanup)
  target=Path(cls.tmp.name)/'map.so'
  subprocess.run(['cc','-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC',str(ROOT/'graphics/native/map_pixels.c'),'-lm','-o',str(target)],check=True)
  cls.lib=C.CDLL(str(target))
 def test_shared_scene_renders_terrain_vectors_and_explicit_labels(self):
  from framebuffer_scene import Context
  from scenes import MapScene,RasterScene
  from map_pixels import Mark
  renderer=NS(lib=self.lib,renderer_name='CPU',font=NS(glyph=lambda ch:bytes([128])+bytes(15)))
  ctx=Context(NS(renderer=renderer));scene=MapScene(1,1,array('I',[0xff0000,0x0000ff]),1,2,(),(Mark*0)())
  prepared=ctx.prepare_scene(scene);self.assertIsInstance(prepared,RasterScene)
  self.assertEqual(prepared.pixels[0],0xf800);self.assertEqual(prepared.pixels[8*8],0x001f)
  self.assertIs(ctx.raster(scene),prepared.pixels)
  lines=(((0,255,0),array('d',[0,0,7,7])),)
  image=ctx.raster(MapScene(1,1,scene.terrain,1,2,lines,(Mark*0)()))
  self.assertEqual(image[0],0x07e0);self.assertEqual(image[7*8+7],0x07e0)
  marked=MapScene(1,1,scene.terrain,1,2,(),(Mark*1)(Mark(0,ord('A'),(1<<48)|(0x00ff00<<24))))
  self.assertEqual(ctx.raster(marked)[0],0x07e0);self.assertEqual(ctx.raster(marked)[1],0)
  ctx.close()

@unittest.skipUnless((ROOT/'build/graphics/frontend.json').exists(),'build graphics first')
class FramebufferDesktop(unittest.TestCase):
 def test_nokia_attach_and_present_need_no_sdl_scene_symbols(self):
  import nokia
  from core import Host,Window
  config=json.loads((ROOT/'build/graphics/frontend.json').read_text());frames=[]
  display=NS(lib=NS(),events=lambda:(),present=lambda frame:frames.append(bytes(frame)),close=lambda:None)
  host=Host(100,30,[Window('A',2,2,30,9,lines=['Framebuffer native UI'])],animate=False)
  host.enable_native(config['native_library'])
  platform=nokia.NokiaPlatform(config['font'],config['gpu_library'],display,require_gpu=False,cell_renderer='cpu',diagnostics=True)
  with patch('gpu_scene.Context',side_effect=AssertionError('SDL scene requested')):
   try:
    platform.attach(host,None,NS(entries={},forms={}))
    while host.damage:
     _,changed,computed=host.flush(2048,serialize=False);platform.consume(changed,computed)
    self.assertTrue(platform.present(True));self.assertEqual(len(frames[-1]),800*480*2)
    self.assertEqual(platform.report['framebuffer_scene']['backend'],'framebuffer')
    self.assertNotIn('gpu_scene',platform.report)
   finally:platform.close()

if __name__=='__main__':unittest.main()
