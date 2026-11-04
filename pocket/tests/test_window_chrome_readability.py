import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from app_widgets import Canvas
from core import Host,Window,Cell
from paint import ink,FRAME_DEFERRED

class ReadabilityTests(unittest.TestCase):
    def test_pane_title_erases_previous_row_text(self):
        c=Canvas(50,5);c.put(0,2,'10 shown · remote · self (directory)')
        c.pane(0,2,50,3,'W7DK')
        self.assertEqual(c.lines()[2].strip(),'W7DK')
    def test_chrome_does_not_inherit_map_pixels_or_text(self):
        w=Window('Stations',2,2,40,12)
        h=Host(60,20,[w]);h.animate=False;h.shadow_enabled=False
        h.background_enabled=False
        palette=ink(10,250,20,background=(240,220,10))
        for x in range(2,42):h.backdrop[(x,2)]=Cell('Z',palette)
        title=h.titlebar(w,40)[0]
        for i,char in enumerate(title):
            cell=h.scene_cell(i+2,2,include_outline=False)
            self.assertEqual(cell.char,char)
            self.assertFalse(cell.color&FRAME_DEFERRED)
            self.assertNotEqual(cell.color&0xffffff,palette&0xffffff)
        plane=h.opaque_plane(w,40,12)
        self.assertEqual([c.color for c in plane[0]],[h.scene_cell(x+2,2,include_outline=False).color for x in range(40)])

    def test_full_window_app_respects_panel_work_area_and_repeated_open(self):
        w=Window('Station Map',4,3,60,18)
        h=Host(100,30,[w]);h.reserved_bottom=1
        h.full_window_apps.add('Station Map')
        h.activate('Station Map')
        self.assertEqual(w.rect,(0,0,100,29))
        saved=h.maximized['Station Map']
        h.activate('Station Map')
        self.assertEqual(w.rect,(0,0,100,29))
        self.assertEqual(h.maximized['Station Map'],saved)
