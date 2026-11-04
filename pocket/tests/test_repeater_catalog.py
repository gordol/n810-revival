import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from repeater_catalog import annotate
from offline_map import Image
from unittest.mock import patch
from entity_actions import EntityRef,ContextActions

class Tests(unittest.TestCase):
    def test_markers_have_own_entities(self):
        class View:
            def project(self,lon,lat):return lon,lat
        row=dict(id='1',call='TEST',rx_mhz=224.18,lat=2,lon=3)
        image=Image(40,10,tuple((' ',0) for _ in range(400)),'',(),0)
        overlay={}
        with patch('repeater_catalog.load',return_value=(row,)):
            hits=annotate(image,View(),overlay,set())
        self.assertEqual(overlay[83][0],'R');self.assertEqual(hits[0][3],row)
        actions=ContextActions();actions.register('repeater','Details',lambda ref:ref.payload)
        self.assertEqual(actions.entries((EntityRef('repeater','1',row),))[0][1](),row)

    def test_hidden_labels_keep_selectable_markers(self):
        class View:
            def project(self,lon,lat):return lon,lat
        row=dict(id='1',call='TEST',rx_mhz=146.8,lat=2,lon=3)
        image=Image(40,10,tuple((' ',0) for _ in range(400)),'',(),0)
        overlay={}
        with patch('repeater_catalog.load',return_value=(row,)):
            hits=annotate(image,View(),overlay,set(),show_labels=False)
        self.assertEqual(len(overlay),1)
        self.assertEqual(hits,((3,2,1,row),))
