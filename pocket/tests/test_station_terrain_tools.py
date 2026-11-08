from reference_fixtures import activate
activate()
import sys,time,unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from station_workspace import StationMap,Context
from station_map_tools import StationMapTools
from native_terrain_profile import TerrainProfile
from pointer_events import PointerEvent,SourceStamp
from entity_actions import ContextActions

SOURCES=Path(__file__).resolve().parents[1]/'shell/vendor/packet-console'

class SharedMapTests(unittest.TestCase):
    def map(self):
        base=StationMap(Context(),SOURCES,lambda:None)
        base.center=(5.5555,5.5555)
        app=StationMapTools(base)
        self.addCleanup(base.renderer.close);self.addCleanup(app.close)
        # Functional interaction coverage includes cold reference-data loading.
        # Shared Docker mounts can take >5 s; UI latency is measured separately.
        until=time.monotonic()+60
        while time.monotonic()<until:
            app.lines()
            if base._image:return app
            time.sleep(.01)
        self.fail(base.renderer.error or 'Map did not load: '+base.renderer.loading_message())
    def test_shared_sidebar_live_layers_and_key_priority(self):
        app=self.map();app.width=120;app.height=45
        app.key('t');camera=app.base.center,app.base.span
        app.key('m');app.key('e')
        self.assertFalse(app.base.side_overview)
        app.key('s');app.lines()
        self.assertIsNone(app.dialog);self.assertTrue(app.base.side_overview)
        self.assertIsNotNone(app.base._locator_rect)
        self.assertTrue(app._sidebar_hits)
        app.key('r');self.assertFalse(app.base.show_repeaters)
        self.assertEqual(app.tool.radius_km,5)
        app.key('2');self.assertNotIn('2m',app.base.repeater_bands)
        app.lines();layer=app.layer();left=layer[2]-32
        # The complete sidebar is composed last, including below the locator.
        bottom=layer[3]-1
        from paint import ink
        self.assertEqual(layer[4][bottom*layer[2]+left+2][1]&0xffffff,ink(220,220,220,background=(14,23,28))&0xffffff)
        self.assertEqual((app.base.center,app.base.span),camera)
        row=next(y for y,key in app._sidebar_hits.items() if key=='r')
        app.pointer_event(PointerEvent(('mouse',0,115,row,False)),120)
        self.assertTrue(app.base.show_repeaters)
        app.key('escape');self.assertFalse(app.base.side_overview)
        self.assertTrue(app.terrain_active)

    @patch.dict('os.environ', {'POCKET_DESKTOP_TERRAIN':'0'})
    def test_nokia_locator_stays_readable_and_controls_scroll_below_it(self):
        app=self.map();app.width=98;app.height=27;app.key('s');app.lines()
        x,y,w,h,image=app.base._locator_rect
        self.assertEqual(w,30);self.assertEqual(h,15)
        self.assertEqual(x,app.width-32+1)
        layer=app.layer();colors={layer[4][(yy-layer[1])*layer[2]+xx][1] for yy in range(y,y+h) for xx in range(x,x+w)}
        self.assertGreaterEqual(len(colors),4) # Terrain, frame, and locator remain visually distinct.
        self.assertTrue(all(row>=y+h for row in app._sidebar_hits))
        self.assertNotIn('i',app._sidebar_hits.values())
        camera=app.base.center,app.base.span
        app.key('end');app.lines()
        self.assertIn('i',app._sidebar_hits.values())
        self.assertEqual((app.base.center,app.base.span),camera)
        scroll=app.sidebar_scroll
        app.pointer_event(PointerEvent(('mouse',64,95,25,False)),98)
        self.assertLess(app.sidebar_scroll,scroll)
        app.key('home');app.lines()
        self.assertIn('n',app._sidebar_hits.values())
        # The locator keeps its own navigation hit area above the controls.
        before=app.base.center
        app.pointer_event(PointerEvent(('mouse',0,x,y,False)),98)
        app.pointer_event(PointerEvent(('mouse',0,x+1,y+1,True)),98)
        self.assertNotEqual(app.base.center,before)

    def test_click_selects_station_into_sidebar_without_dropping_terrain_pin(self):
        app=self.map();base=app.base;base.preview=False
        lat,lon=base.center
        base.context.catalog(dict(revision=1,has_more=False,rows=[dict(call='TEST',position=dict(lat=lat,lon=lon),categories=[],symbol=None)]))
        base.context.select_station=lambda call:base.context.select(None,dict(call=call,position=(lat,lon))) or True
        app.lines()
        x,y,_,_=base._station_hits[0];x=round((x+.5)*base.width/base._image.width-.5);y=round((y+.5)*(base.height-3)/base._image.height-.5)+2
        app.pointer_event(PointerEvent(('mouse',0,x,y,False)),base.width)
        app.pointer_event(PointerEvent(('mouse',0,x,y,True)),base.width)
        self.assertEqual(base.context.target['call'],'TEST')
        self.assertEqual(app.sidebar_tab,'details');self.assertTrue(base.side_overview)
        self.assertFalse(app.terrain_active)
        self.assertIn('TEST',[text for text,_,_ in app.detail_rows()])

    def test_profile_action_reports_missing_position_and_escape_returns(self):
        app=self.map();app.key('s')
        self.assertFalse(app.profile_from_qth('MISSING'))
        self.assertTrue(app.terrain_active);self.assertEqual(app.tool.screen,'profile')
        self.assertIn('No observed position for MISSING','\n'.join(app.lines()))
        app.key('escape');self.assertEqual(app.tool.screen,'map')
        app.tool.screen='profile';app.base.side_overview=True;app.layers_visible=True
        app.key('m');self.assertEqual(app.tool.screen,'map')

    def test_station_profile_opens_with_qth_and_target(self):
        from unittest.mock import patch
        app=self.map();tool=app.ensure_tool()
        tool.qth=dict(latitude=5.5555,longitude=5.5555,height_m=15)
        app.resolve_station=lambda call:(5.33555,4.95555)
        app.key('s')
        with patch.object(tool,'calculate',return_value=True) as calculate:
            self.assertTrue(app.profile_from_qth('VCAPK'))
            calculate.assert_called_once()
        self.assertEqual(tool.map.points,[(5.5555,5.5555),(5.33555,4.95555)])
        self.assertEqual(tool.fields[3].text,'15');self.assertEqual(tool.screen,'profile')
        self.assertFalse(app.base.side_overview);self.assertFalse(app.layers_visible)

    def test_qth_marker_context_uses_exact_saved_coordinate(self):
        app=self.map();tool=app.ensure_tool();tool.map.qth=app.base.center
        tool.qth=dict(latitude=app.base.center[0],longitude=app.base.center[1],height_m=15)
        app.self_calls_provider=lambda:('TEST-1',)
        app.lines();image=tool.map.image;layer=app.layer()
        px,py=image.projection.project(tool.map.qth[1],tool.map.qth[0])
        x=round((px+.5)*layer[2]/image.width-.5)+layer[0]
        y=round((py+.5)*layer[3]/image.height-.5)+layer[1]
        # A station beneath any letter of QTH must not leak into its menu.
        from entity_actions import EntityRef
        from unittest.mock import patch
        with patch.object(app.base,'entities_at',return_value=(EntityRef('station','W8NGS-9'),)):
            refs=app.entities_at(x+5,y)
        self.assertEqual(len(refs),1)
        self.assertTrue(refs[0].payload['saved_qth'])
        actions=ContextActions();actions.register('map-point','LOS radius from here',lambda entity:None)
        self.assertEqual(actions.entries(refs)[0][0],'LOS radius from here · QTH TEST-1')
        self.assertEqual(refs[-1].payload['position'],tool.map.qth)
        self.assertEqual(tool.map.qth_label,'QTH TEST-1')

    def test_repeater_radius_uses_site_frequency_without_moving_qth(self):
        from unittest.mock import patch
        app=self.map();tool=app.ensure_tool();tool.map.qth=(5.5555,5.5555)
        camera=app.base.center,app.base.span
        with patch.object(tool,'show_los',return_value=True) as calculate:
            app.coverage_from_location('W7DK Hill',(47.25,-122.48),147.28)
            calculate.assert_called_once()
        self.assertEqual(tool.map.points[0],(47.25,-122.48))
        self.assertEqual(tool.map.qth,(5.5555,5.5555))
        self.assertEqual(tool.fields[2].text,'147.28');self.assertEqual(tool.fields[3].text,'10')
        self.assertEqual(tool.map.origin_label,'W7DK Hill')
        self.assertIn('assumed',tool.status);self.assertEqual((app.base.center,app.base.span),camera)

    def test_feature_disable_cancels_work_and_blocks_all_entry_points(self):
        from concurrent.futures import Future
        app=self.map();tool=app.ensure_tool();tool.pending=Future();tool.job='coverage'
        app.terrain_active=True;tool.map.coverage={'cells':[]}
        app.preferences_changed({'terrain-enabled':False})
        self.assertTrue(tool.closed);self.assertTrue(tool.cancelled.is_set())
        self.assertTrue(tool.pending.cancelled());self.assertIsNone(app.tool)
        self.assertFalse(app.terrain_active)
        self.assertFalse(app.enter_terrain('area',(5.56555,5.58555)))
        self.assertFalse(app.profile_from_qth('W7DK',(47.3,-122.4)))
        self.assertFalse(app.coverage_from_location('Repeater',(47.3,-122.4),146.5))
        self.assertNotIn('[ Terrain T ]','\n'.join(app.lines()))
        app.restore_session({'terrain_active':True,'terrain':{'fields':['5.56555,5.58555','','144','15','2'],'mode':'area'}})
        self.assertFalse(app.terrain_active)
        app.preferences_changed({'terrain-enabled':True});self.assertTrue(app.enter_terrain())
        self.assertIsNot(app.tool,tool)

    def test_context_availability_changes_without_re_registering(self):
        from entity_actions import EntityRef
        state={'enabled':True};actions=ContextActions()
        actions.register('station','Profile',lambda entity:None,available=lambda:state['enabled'])
        refs=(EntityRef('station','W7DK'),)
        self.assertEqual(len(actions.entries(refs)),1)
        state['enabled']=False;self.assertEqual(actions.entries(refs),[])

    def test_standalone_profile_obeys_map_feature_preference(self):
        enabled=[False];tool=TerrainProfile();self.addCleanup(tool.close)
        tool.enabled_provider=lambda:enabled[0]
        tool.set_endpoint((5.56555,5.58555),False)
        self.assertFalse(tool.show_los());self.assertFalse(tool.calculate());self.assertFalse(tool.nearby())
        self.assertIsNone(tool.pending);self.assertIn('disabled','\n'.join(tool.lines()))
        enabled[0]=True;tool.lines();self.assertEqual(tool.screen,'map')

    def test_shared_renderer_camera_modes_and_clear(self):
        app=self.map();renderer=app.renderer;center=app.base.center
        app.key('t');self.assertIs(app.tool.map.renderer,renderer);self.assertEqual(app.tool.map.center,center)
        lines=app.lines();self.assertIn('Preview',lines[0]);self.assertIn('Overview',lines[0])
        app.key('v');self.assertFalse(app.base.preview)
        app.key('v');self.assertTrue(app.base.preview)
        app.key('o');self.assertTrue(app.base.full_overview)
        app.key('o');self.assertFalse(app.base.full_overview)
        app.tool.set_endpoint((47.25,5.5855),False);app.tool.set_endpoint((47.3,-122.4),True)
        app.key('c');self.assertEqual(app.tool.map.points,[None,None])
        app.key('t');self.assertEqual(app.tool.map.mode,'area')
        app.tool.map.choose((47.25,5.5855));self.assertIsNone(app.tool.map.points[1])
        self.assertIn('Radius',app.lines()[1]);self.assertNotIn('[To B]',app.lines()[1])
        app.key('h');self.assertEqual(app.tool.screen,'house-settings')
        text='\n'.join(app.lines());self.assertIn('Roof antenna',text);self.assertNotIn('To lat,lon',text)
        state=app.session_state();self.assertEqual(state['terrain']['mode'],'area')
    def test_map_location_actions_and_keyboard_location(self):
        app=self.map();refs=app.entities_at(35,14)
        self.assertEqual(refs[-1].kind,'map-point')
        self.assertIn('position',refs[-1].payload)
        actions=ContextActions();actions.register('map-point','House LOS',lambda entity:app.enter_terrain('area',entity.payload['position']))
        actions.entries(refs)[0][1]();self.assertEqual(app.tool.map.mode,'area')
        self.assertEqual(app.selected_entities()[-1].kind,'map-point')
    def test_restoring_terrain_when_adding_house_never_moves_shared_camera(self):
        app=self.map();app.base.center=(47.4,-122.3);app.base.span=1.25
        app.restore_session(dict(terrain=dict(fields=['47.25,5.5855','','144.39','15','10'],
            radius_km=50,center=[46.8,-121.7],span=180,mode='area')))
        app.enter_terrain('area',(47.41,-122.31))
        self.assertEqual(app.base.center,(47.4,-122.3));self.assertEqual(app.base.span,1.25)
        self.assertEqual(app.tool.radius_km,50)

    def test_saved_pin_and_mode_are_visible_when_station_map_reopens(self):
        app=self.map();camera=app.base.center,app.base.span
        app.restore_session(dict(terrain=dict(fields=['5.5555,5.5555','','915','15','10'],radius_km=50,mode='area')))
        self.assertTrue(app.terrain_active)
        app.lines();self.assertEqual(app.tool.map.points[0],(5.5555,5.5555))
        self.assertEqual(app.tool.map.mode,'area');self.assertEqual(app.tool.radius_km,50)
        self.assertEqual((app.base.center,app.base.span),camera)
        self.assertIsNotNone(app.layer())

    def test_house_zoom_and_source_timed_double_click(self):
        app=self.map();app.key('t');base=app.base;base.preview=False
        for _ in range(60):app.key('+')
        self.assertLess(base.span,.025)
        base.span=2;app.lines()
        # The exact Station Map gesture implementation receives source timing.
        for i,(released,ns) in enumerate(((False,0),(True,40_000_000),(False,150_000_000),(True,190_000_000))):
            event=PointerEvent(('mouse',0,35,14,released),stamp=SourceStamp(ns,'test'))
            app.pointer_event(event,base.width)
        self.assertLess(base.span,2)

if __name__=='__main__':unittest.main()
