"""Responsive launcher placement must not override the user's menu edge."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from panel import Panels

class PanelPositionTests(unittest.TestCase):
    def test_menu_stays_on_saved_edge_through_width_changes_and_modes(self):
        for edge in ('top','bottom','left','right'):
            with self.subTest(edge=edge):
                panels=Panels(edge,mode='auto');menu=panels.panels[0]
                for columns in (100,200,80,160,100):
                    panels.layout(columns,30)
                    self.assertEqual(menu.dock,edge)
                    self.assertEqual(len({p.dock for p in panels.panels}),len(panels.panels))
                for mode in ('bar','auto','sidebar','dock','bar'):
                    panels.set_mode(mode);panels.layout(100,30)
                    self.assertEqual(menu.dock,edge)

    def test_explicit_launcher_dock_survives_layout(self):
        panels=Panels('bottom',mode='sidebar')
        launcher=next(p for p in panels.panels if p.widgets==['apps'])
        panels.selected=launcher;panels.rotate();edge=launcher.dock
        for width in (200,100,200):
            panels.layout(width,30);self.assertEqual(launcher.dock,edge)

    def test_top_launcher_reserves_its_height_without_overlaying_menu(self):
        panels=Panels('bottom',mode='auto');bounds=panels.layout(200,30)
        launcher=next(p for p in panels.panels if p.widgets==['apps'])
        self.assertEqual(launcher.dock,'top');self.assertEqual(launcher.rect[1:4:2],(0,3))
        self.assertEqual(bounds,(0,3,200,26))
        self.assertEqual(panels.panels[0].rect,(0,29,200,1))
if __name__=='__main__':unittest.main()
