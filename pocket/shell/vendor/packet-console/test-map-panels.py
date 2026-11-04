import importlib.util,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('map_panels_tests',Path(__file__).with_name('n810-map-panels.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class Tests(unittest.TestCase):
    def test_independent_visibility_and_focus(self):
        p=m.PanelState();p.toggle('packets');p.toggle('inspector')
        self.assertEqual(p.visible,{'packets','inspector'});self.assertEqual(p.focus,'inspector')
        self.assertEqual(p.focus_next(),'map');self.assertEqual(p.focus_next(),'packets')
        p.toggle('inspector');self.assertEqual(p.visible,{'packets'});self.assertEqual(p.focus,'packets')
        p.map_only();self.assertEqual(p.visible,set());self.assertEqual(p.focus,'map')
    def test_shared_state_has_app_independent_names(self):
        p=m.PanelState(names=('probes','packets'));p.toggle('probes');p.toggle('packets')
        self.assertEqual(p.visible,{'probes','packets'});p.focus_map();self.assertEqual(p.focus,'map')
        with self.assertRaises(ValueError):p.toggle('unknown')
    def test_bounds_and_panel_nonoverlap_across_sizes(self):
        for width in (24,40,65,83,84,100,160):
            for height in (12,16,29,40):
                rects=m.layout(width,height,{'packets','inspector'})
                self.assertEqual(rects['map'],(0,0,width,height))
                for x,y,w,h in rects.values():self.assertTrue(0<=x<=x+w<=width and 0<=y<=y+h<=height)
                if 'packets' in rects and 'inspector' in rects:
                    x,y,w,h=rects['packets'];a,b,c,d=rects['inspector']
                    self.assertTrue(x+w<=a or a+c<=x or y+h<=b or b+d<=y)
    def test_side_by_side_and_narrow_stack(self):
        r=m.layout(100,29,{'packets','inspector'});self.assertEqual(r['packets'][1],r['inspector'][1]);self.assertLess(r['packets'][0],r['inspector'][0])
        r=m.layout(60,29,{'packets','inspector'});self.assertLess(r['packets'][1],r['inspector'][1])
    def test_one_panel_and_empty_layout(self):
        self.assertEqual(m.layout(0,0),{})
        r=m.layout(100,29,{'inspector'});self.assertNotIn('packets',r);self.assertGreater(r['inspector'][0],1)
        r=m.layout(100,29,{'packets'});self.assertEqual(r['packets'][0],1)

if __name__=='__main__':unittest.main()
