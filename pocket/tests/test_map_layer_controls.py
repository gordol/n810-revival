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
    def test_host_selects_semantic_map_presentation_once(self):
        choices=[];base=Base();base.renderer=SimpleNamespace(set_presentation=choices.append)
        form=StationMapTools(base);form.set_map_presentation('semantic')
        self.assertEqual(choices,['semantic'])
        self.assertEqual(form._map_presentation,'semantic')

    def test_sidebar_toggle_notifies_saved_view(self):
        form=StationMapTools(Base());changes=[]
        form._session_callback=lambda:changes.append(form.session_state()['layers_visible'])
        form.key('s');form.key('s')
        self.assertEqual(changes,[True,False])

    def test_regular_map_footer_names_escape_destination(self):
        from native_navigation import native_presentation
        form=StationMapTools(Base())
        rows,_=native_presentation(form,form.lines(),(),100,30)
        self.assertIn('Esc Stations',rows[-1])

    def test_semantic_surface_keeps_annotations_without_tui_grid(self):
        from offline_map import GridPlane,PathPlane,Plane
        base=Base();image=SimpleNamespace(projection=SimpleNamespace(center=(47.,-122.),span=4.))
        base._shown_image=image;base.maidenhead_grid='auto';base.renderer=SimpleNamespace(supports_semantic_image=lambda image:True)
        cells=((' ',0),)*4
        retained=(0,2,2,2,Plane(PathPlane(GridPlane(cells,{0:('┆',1)}),{2:('•',1)}),{1:('A',2)}))
        base.layer=lambda:retained
        form=StationMapTools(base);surface=form.map_surface()
        self.assertIs(surface.image,image)
        self.assertEqual(surface.grid_mode,'auto')
        self.assertEqual(surface.layer[4][0],(' ',0))
        self.assertEqual(surface.layer[4][1],('A',2))
        self.assertEqual(surface.layer[4][2],(' ',0))
        self.assertEqual(surface.key,form.map_surface().key)
        base.layer=lambda:(0,2,2,2,Plane(PathPlane(GridPlane(cells,{0:('┆',1)}),{2:('•',1)}),{1:('A',2)}))
        self.assertEqual(surface.key,form.map_surface().key)
        base.layer=lambda:(0,2,2,2,Plane(PathPlane(GridPlane(cells,{0:('┆',1)}),{2:('•',1)}),{1:('B',2)}))
        self.assertNotEqual(surface.key,form.map_surface().key)
        base.renderer.supports_semantic_image=lambda image:False
        unavailable=form.map_surface()
        self.assertIn('no native semantic layers',unavailable.unavailable_reason)
        with self.assertRaises(ValueError):unavailable.features(None,None)

    def test_sidebar_owns_fixed_width_outside_moving_map(self):
        base=Base();base.side_overview=True
        base._shown_image=SimpleNamespace(projection=SimpleNamespace(center=(47.,-122.),span=4.))
        base.maidenhead_grid='off';base.renderer=SimpleNamespace(supports_semantic_image=lambda image:True)
        form=StationMapTools(base)
        surface=form.map_surface()
        self.assertEqual(surface.content_width,68)

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

    def test_click_saved_qth_without_repeater_does_not_crash(self):
        from entity_actions import EntityRef
        base=Base();base.side_overview=False;base.center=(0.,0.);base.span=10.
        base.target_box=SimpleNamespace(revision=0)
        base.pointer_event=lambda *args:True
        form=StationMapTools(base)
        point=dict(saved_qth=True,position=(0.,0.),label='QTH')
        form.entities_at=lambda *args:(EntityRef('map-point','qth',point),)
        form.pointer_event(('mouse',0,20,10,False),100)
        form.pointer_event(('mouse',0,20,10,True),100)
        self.assertEqual(form.detail_point,point);self.assertIsNone(form.detail_repeater)
        self.assertEqual(form.sidebar_tab,'details')
