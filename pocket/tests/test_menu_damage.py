"""Menu damage keeps exact priority and pixels with bulk native set operations."""
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window
from native_runtime import select
class MenuDamageTests(unittest.TestCase):
 def host(self,native=False):
  h=Host(50,20,[Window('Connections',4,3,30,12)]);h.background_enabled=False;h.animate=False;h.shadow_enabled=False
  if native:
   library=os.environ.get('POCKET_TEST_NATIVE') or select(build=False)['library']
   if not library: self.skipTest('native library unavailable')
   self.assertTrue(h.enable_native(library))
  h.flush(1000);return h
 def test_selection_matches_reference_with_partial_damage_and_moved_menu(self):
  for native in (False,True):
   h=self.host(native);h.launcher_anchor=(45,18,2,1);h.set_launcher(('Applications','Find:','Connections','','Esc closes'))
   h.ui_damage.update((0,999));h.damage.update((0,999));h.damage.difference_update((901,902))
   for inside in (False,True):
    for budget in (1,64,1000,None):
     bounds=h.launcher_bounds() if inside else None
     if bounds:
      x,y,w,z=bounds;candidates=(yy*h.width+xx for yy in range(y,y+z) for xx in range(x,x+w))
     else:candidates=sorted(h._launcher_dirty)
     expected=[i for i in candidates if i in h.ui_damage and i in h.damage]
     if budget is not None:expected=expected[:budget]
     self.assertEqual(h.launcher_damage(budget,inside),expected)
 def test_open_close_restores_exact_native_and_portable_pixels(self):
  a,b=self.host(),self.host(True)
  for lines in (('Applications','Find:','Connections','','Esc closes'),(),('Applications','Find:','Help'),()):
   for h in (a,b):
    h.set_launcher(lines)
    for _ in range(100):
     h.flush(64)
     if not h._launcher_dirty:break
    self.assertFalse(h._launcher_dirty)
   self.assertEqual(list(a.front),list(b.front))
if __name__=='__main__':unittest.main()
