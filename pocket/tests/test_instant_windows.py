"""Window geometry changes complete before the next presentation."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window

class InstantWindows(unittest.TestCase):
    def test_open_restore_and_roll_are_immediate_with_animation_enabled(self):
        h=Host(100,30,[Window('Example',5,3,50,18)],animate=True,clock=lambda:0.)
        h.background_enabled=False
        w=h.window('Example');w.visible=False
        h.activate(w.name)
        self.assertEqual(h.bounds(w),(5,3,50,18))
        h.roll(w.name)
        self.assertEqual(h.bounds(w),w.rect)
        self.assertEqual(h.bounds(w)[3],1)
        h.activate(w.name)
        self.assertEqual(h.bounds(w),(5,3,50,18))
        h.visibility(w.name)
        self.assertFalse(h.shown(w))
        h.activate(w.name)
        self.assertTrue(h.shown(w))
        self.assertEqual(h.bounds(w),(5,3,50,18))
        self.assertFalse(h.animations)
        self.assertFalse(h.visual)
        while h.damage:h.flush(3000)
        h.advance()
        self.assertFalse(h.damage)
        self.assertTrue(h.animate)

    def test_window_animation_is_opt_in_and_master_toggle_is_respected(self):
        h=Host(100,30,[Window('Example',5,3,50,18)],animate=True,clock=lambda:0.)
        h.window_animations=True
        h.roll('Example')
        self.assertIn('Example',h.animations)
        h.settle()
        h.animate=False
        h.roll('Example')
        self.assertFalse(h.animations)

    def test_window_animation_preference_round_trip_and_default(self):
        from panel import Panels
        from session import capture,restore
        h=Host(100,30,[Window('Example',5,3,50,18)])
        panels=Panels()
        h.window_animations=True
        data=capture(h,panels)
        h.window_animations=False
        restore(data,h,panels)
        self.assertTrue(h.window_animations)
        del data['preferences']['window_animations']
        restore(data,h,panels)
        self.assertFalse(h.window_animations)

if __name__=='__main__':unittest.main()
