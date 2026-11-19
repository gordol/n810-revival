from pathlib import Path
import sys,unittest
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'graphics'),str(Path(__file__).resolve().parents[1]/'shell')]
from pixel_scene import Context
class PanelRunsTests(unittest.TestCase):
    def model(self):
        context=object.__new__(Context);context.panels={};context.damage_rect=lambda *args:None
        return context
    def text(self,c,width):
        row=['?']*width
        for (x,y),(label,fg,bg) in c.panels.items():row[x:x+len(label)]=label
        return ''.join(row)
    def test_closed_task_does_not_survive_new_panel_runs(self):
        c=self.model();c.panel_text(0,0,'menu ',1,0);c.panel_text(5,0,'Surface room',2,0);c.panel_text(17,0,'   ',1,0)
        c.panel_text(0,0,'menu                ',1,0)
        self.assertEqual(self.text(c,20),'menu                ')
        self.assertEqual(len(c.panels),1)
        c.panel_text(5,0,'Help',2,0)
        self.assertEqual(self.text(c,20),'menu Help           ')
        c.panel_text(0,0,'menu                ',1,0)
        self.assertEqual(len(c.panels),1)
    def test_partial_update_preserves_both_edges_and_other_rows(self):
        c=self.model();c.panel_text(0,0,'abcdefghij',1,0);c.panel_text(0,1,'other',2,0)
        c.panel_text(3,0,'XYZ',3,0)
        self.assertEqual(c.panels[0,0][0],'abc');self.assertEqual(c.panels[6,0][0],'ghij')
        self.assertEqual(c.panels[0,1][0],'other')
        self.assertFalse(c.panel_text(3,0,'XYZ',3,0))
if __name__=='__main__':unittest.main()
