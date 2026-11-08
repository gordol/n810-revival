"""Retry through the real app registry must replace the native view as well."""
import json,sys,unittest,weakref,gc
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'graphics'));sys.path.insert(0,str(ROOT/'shell'))
from full import Platform
from core import Host,Window
from app_registry import Registry

@unittest.skipUnless((ROOT/'build/graphics/frontend.json').exists(),'build with make graphics-native')
class PixelLifecycle(unittest.TestCase):
 def test_registered_room_retry_has_one_live_pixel_view(self):
  from run import DesktopWindow
  config=json.loads((ROOT/'build/graphics/frontend.json').read_text())
  host=Host(100,29,[Window('Surface room',2,2,60,20)],animate=False)
  host.app_forms={}
  registry=Registry().discover((('apps/surface-renderer/registration.py','descriptor'),))
  display=DesktopWindow.__new__(DesktopWindow)
  display.capture=lambda enabled:setattr(display,'captured',enabled)
  p=Platform(config['font'],config['gpu_library'],display,cell_renderer='cpu')
  p.configure_registry(registry);registry.bind(host)
  form=registry.forms['Surface room']
  try:
   self.assertTrue(registry.open('surface-room'),form.error)
   for _ in range(20):
    old=form.owner;previous=weakref.ref(old)
    display.captured=True;display.captured_target=old
    display.controls_for(old).motion.event('w','press',old.clock())
    self.assertEqual(p.pixel_apps,[old]);form.error='test retry';self.assertTrue(form.key('r'),form.error)
    self.assertTrue(old.closed);self.assertIsNot(form.owner,old)
    self.assertFalse(display.captured);self.assertIsNone(display.captured_target)
    self.assertNotIn(old,display.controls)
    self.assertEqual(p.pixel_apps,[form.owner]);del old;gc.collect()
    self.assertIsNone(previous())
  finally:form.close();p.pixel_apps.clear()

if __name__=='__main__':unittest.main()
