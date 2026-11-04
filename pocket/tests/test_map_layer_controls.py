import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from station_map_tools import StationMapTools
from types import SimpleNamespace
class Base:
    context=SimpleNamespace(target=None,map_catalog=None)
    width=100;height=30;show_repeaters=True;preview=True;full_overview=False
    def locator_hit(self,x,y):return False
    def key(self,key):
        if key=='s':self.side_overview=not getattr(self,'side_overview',False)
        return True
    def close(self):pass
    def session_state(self):return {}
    def restore_session(self,state):pass
    def lines(self):return [" "*self.width for _ in range(self.height)]
    def layer(self):return (0,2,self.width,self.height-3,[(" ",None)]*(self.width*(self.height-3)))
class Tests(unittest.TestCase):
    def test_details_visible_and_layers_toggle(self):
        form=StationMapTools(Base())
        form.sidebar_scroll=5
        form.show_repeater(dict(call='TEST',site='Hill',rx_mhz=146.8,tx_mhz=146.2,edition='20261101'))
        self.assertEqual(form.sidebar_scroll,0)
        self.assertIsNone(form.dialog)
        self.assertEqual(form.sidebar_tab,'details')
        self.assertIsNotNone(form.layer())
        self.assertIn('RX 146.8 MHz',' '.join(text for text,_,_ in form.detail_rows()))
        form.key('l');form.lines()
        row=next(row for row,key in form._sidebar_hits.items() if key=='r')
        form.pointer_event(('mouse',0,80,row,False),100)
        self.assertFalse(form.base.show_repeaters)
        form.key('2');self.assertNotIn('2m',form.base.repeater_bands)
        form.key('2');self.assertIn('2m',form.base.repeater_bands)
        form.key('n');form.key('p')
        self.assertTrue(form.base.station_labels);self.assertTrue(form.base.repeater_labels)
        saved=form.session_state()
        other=StationMapTools(Base());other.restore_session(saved)
        self.assertTrue(other.base.station_labels);self.assertTrue(other.base.repeater_labels)
