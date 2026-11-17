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


class OverlayBorderTests(unittest.TestCase):
    def host(self):
        return Host(70, 20, [], ascii=True, animate=False, background_async=False)

    def test_docked_menus_omit_the_attached_edge_and_preserve_hit_rows(self):
        host = self.host()
        host.origin = (4, 1)
        host.overlay_screen = (78, 22)
        lines = ('Applications', 'Find:', '> Example', '', 'Esc closes')
        for dock, missing_edge, origin in (
            ('top', 0, (12, 0)), ('right', 1, (34, 6)),
            ('bottom', 2, (12, 13)), ('left', 3, (0, 6)),
        ):
            with self.subTest(dock=dock):
                host.place_launcher((12, 6, 1, 1), dock)
                host.set_launcher(lines)
                bounds = host.launcher_bounds()
                self.assertEqual(bounds, (*origin, 36, 7))
                edges = tuple(edge != missing_edge for edge in range(4))
                self.assertEqual(host.launcher_edges(bounds), edges)
                x, y = origin
                top, right, bottom, left = edges
                self.assertEqual(host.launcher_pointer_row(x+left, y+top+2), 0)
                self.assertEqual(host.overlay_cell(x+left, y+top+2).char, '>')
                if right:
                    self.assertEqual(host.launcher_pointer_row(x+35, y+top+2), -1)

    def test_floating_and_screen_edges_with_all_preference_modes(self):
        host = self.host()
        host.set_launcher(('Applications', 'Find:', '> Example'))
        host.place_launcher((10, 3, 1, 1))
        self.assertEqual(host.launcher_edges(host.launcher_bounds()), (True,)*4)
        host.place_launcher((0, 20, 1, 1))
        self.assertEqual(host.launcher_edges(host.launcher_bounds()), (True, True, False, False))
        host.set_preference('overlay_borders', 'All edges')
        self.assertEqual(host.launcher_rows()[0], ('+'+'-'*34+'+', 0))
        host.set_preference('overlay_borders', 'Off')
        self.assertEqual(host.launcher_bounds()[2:], (36,3))
        self.assertEqual(host.launcher_rows()[0], ('Applications'.ljust(36), 1))

    def test_help_uses_the_same_border_and_font_fallback(self):
        host = self.host()
        host.toggle_help()
        x,y,width,_ = host.floating_overlay_bounds(host.help_lines)
        self.assertEqual(host.overlay_cell(x,y).char, '+')
        self.assertEqual(host.overlay_cell(x+width-1,y).char, '+')
        self.assertEqual(host.overlay_cell(x+1,y+1).char, 'H')
        host.set_preference('overlay_borders', 'Off')
        self.assertEqual(host.overlay_cell(x,y).char, 'H')

    def test_legacy_session_defaults_and_new_value_round_trips(self):
        from panel import Panels
        from session import capture, restore

        host, panels = self.host(), Panels()
        state = capture(host, panels)
        state['preferences'].pop('overlay_borders')
        host.set_preference('overlay_borders', 'Off')
        restore(state, host, panels)
        self.assertEqual(host.overlay_borders, 'Exposed edges')
        state['preferences']['overlay_borders'] = 'All edges'
        restore(state, host, panels)
        self.assertEqual(capture(host, panels)['preferences']['overlay_borders'], 'All edges')

if __name__=='__main__':unittest.main()
