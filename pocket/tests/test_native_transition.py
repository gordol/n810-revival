"""Portable transitions preserve pixels without round-tripping the whole front."""
import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window,Cell
from native_runtime import select
from native_cells import Front
class NativeTransitionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.library=os.environ.get('POCKET_TEST_NATIVE') or select(build=False)['library']
  if not cls.library:raise unittest.SkipTest('native library unavailable')
 def make(self):
  h=Host(40,15,[Window('Connections',2,2,28,10),Window('Other',3,3,20,8)])
  h.window('Other').desktop=1;h.background_enabled=False;h.shadow_enabled=False;h.window_opacity=1;h.animate=True
  h.clock=lambda:0.;h.content('Connections',1,('retained content',));h.content('Other',1,('other desktop',))
  self.assertTrue(h.enable_native(self.library));h.flush(600)
  return h
 def test_slide_pixels_match_legacy_conversion_and_front_is_retained(self):
  a,b=self.make(),self.make();front=a.front
  for target in (1,0):
   a.clock=b.clock=lambda:0.
   a.switch(target)
   with patch.object(b._native,'scene_snapshot',return_value=None):b.switch(target)
   # Reference uses the previous eager Python-front conversion.
   b.front=list(b.front);b._native.front=None;b._native.planes.clear()
   for now in (.02,.08,.14,.20):
    a.clock=b.clock=lambda now=now:now
    a.invalidate((0,0,40,15));b.invalidate((0,0,40,15))
    left=a.flush(600);right=b.flush(600)
    self.assertEqual(left,right)
    self.assertEqual(list(a.front),list(b.front))
    self.assertIs(a.front,front)
 def test_switch_snapshots_geometry_once_and_preserves_scene(self):
  h=self.make();expected=tuple(h.scene_cell(x,y) for y in range(h.height) for x in range(h.width))
  with patch.object(h,'bounds',wraps=h.bounds) as bounds:
   h.switch(1)
   self.assertLess(bounds.call_count,20)
  self.assertEqual(tuple(h.slide[0]),expected)
 def test_native_snapshot_matches_fresh_scene_with_pending_content(self):
  from native_scene import flux
  for ascii_mode in (False,True):
   h=self.make();h.ascii=ascii_mode
   h.backdrop=h.scene_cells(flux(h._native.lib,h.width,h.height,3,False,1.,.15,2))
   h.content('Connections',2,('new content before repaint',))
   expected=tuple(h.scene_cell(x,y) for y in range(h.height) for x in range(h.width))
   front=h.front
   with patch.object(h,'scene_cell',side_effect=AssertionError('portable snapshot')):
    h.switch(1)
   self.assertEqual(tuple(h.slide[0]),tuple(Cell(h.glyphs.cell(c.char,h.ascii),c.color) for c in expected))
   self.assertIs(h.front,front)
 def test_unsupported_snapshot_preserves_portable_path(self):
  h=self.make();h.shadow_enabled=True
  expected=tuple(h.scene_cell(x,y) for y in range(h.height) for x in range(h.width))
  h.switch(1)
  self.assertEqual(h.slide[0],expected)
 def test_portable_transition_does_not_iterate_whole_native_front(self):
  h=self.make();h.switch(1);h.clock=lambda:.05
  with patch.object(Front,'__iter__',side_effect=AssertionError('whole-front conversion')):
   h.flush(64)
   h.clock=lambda:.3;h.flush(600)
  self.assertEqual(h.render_backend,'native')
if __name__=='__main__':unittest.main()
