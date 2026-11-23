"""Touch navigation geometry in the phone shell."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shell'))
from mobile_shell import Home, MobilePanels


class MobileTests(unittest.TestCase):
    def test_tiles_follow_rotation_and_only_offer_available_apps(self):
        launches = []
        apps = ('Stations', 'Offline Data', 'Field Log')
        home = Home(SimpleNamespace(focus_order=apps), launches.append)
        for width, height in ((43, 35), (92, 14)):
            home.width, home.height = width, height
            home.lines()
            for _, name, left, top, right, bottom in home.tiles():
                for x, y in ((left, top), (right-1, bottom-1)):
                    self.assertTrue(home.pointer(x, y, width))
                    self.assertEqual(launches[-1], 'window:'+name)
                    self.assertFalse(home.pointer(x, y, width, released=True))
        self.assertCountEqual(home.apps, apps)

    def test_bottom_navigation_includes_padding(self):
        panel = MobilePanels()
        for width, height in ((45,40), (90,20), (40,14)):
            _, _, _, work = panel.layout(width, height)
            panel.render({})
            for y in range(work,height):
                self.assertEqual(panel.pointer(0,0,y,False),'launch:window:Pocket Home')
                self.assertEqual(panel.pointer(0,width//2,y,False),'key:,')
                self.assertEqual(panel.pointer(0,width-1,y,False),'key:d')
