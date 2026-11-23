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

    def test_termux_input_control(self):
        from unittest.mock import patch
        from mobile_shell import TouchInput
        panel = MobilePanels(phone_input=True)
        panel.layout(40,24)
        panel.render({})
        self.assertEqual(panel.pointer(0,39,23,False),'launch:window:Touch input')
        form = TouchInput()
        form.lines()
        with patch('mobile_shell.subprocess.run') as run:
            for y, mode in ((3,'Simulated touchscreen'), (5,'Trackpad')):
                self.assertTrue(form.pointer(4,y,40))
                self.assertEqual(run.call_args.args[0], ['termux-x11-preference','touchMode='+mode])
                self.assertFalse(form.pointer(4,y,40,released=True))
            run.side_effect = FileNotFoundError()
            form.key('up')
            form.key('\r')
            self.assertIn('Could not switch',form.message)
