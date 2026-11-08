from reference_fixtures import activate
activate()
import sys,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from native_terrain_profile import TerrainProfile

class PointMapTests(unittest.TestCase):
    def app(self):
        app=TerrainProfile();self.addCleanup(app.close)
        until=time.monotonic()+5
        while time.monotonic()<until:
            app.lines()
            if app.map.image:return app
            time.sleep(.01)
        self.fail(app.map.renderer.error or 'No map frame')
    def test_two_map_clicks_calculate_fixture_profile_and_return_to_map(self):
        app=self.app();self.assertEqual(app.screen,'map')
        for x,y in ((35,14),(53,17)):
            expected=app.map.position_at(x,y)
            app.pointer(x,y,app.width);app.pointer(x,y,app.width,released=True)
            selected=app.map.points[0 if x==35 else 1]
            self.assertEqual(selected,expected)
        self.assertNotEqual(app.fields[0].text,app.fields[1].text)
        app.lines();self.assertIsNotNone(app.layer())
        app.key('p');self.assertEqual(app.screen,'profile')
        until=time.monotonic()+5
        while app.pending and time.monotonic()<until:app.poll();time.sleep(.005)
        self.assertIsNotNone(app.result,app.error)
        self.assertIn('fictional-fine',app.result['source'])
        app.key('m');self.assertEqual(app.screen,'map')
        app.lines();self.assertIsNotNone(app.layer())
    def test_drag_pans_without_changing_endpoints(self):
        app=self.app();app.map.base.preview=False;before=app.map.center
        app.pointer(30,12,app.width);app.pointer(42,15,app.width,button=32)
        app.pointer(42,15,app.width,released=True)
        self.assertNotEqual(before,app.map.center)
        self.assertEqual(app.map.points,[None,None])
    def test_endpoint_can_be_reselected(self):
        app=self.app();app.key('b')
        app.pointer(35,14,app.width);app.pointer(35,14,app.width,released=True)
        self.assertIsNone(app.map.points[0]);self.assertIsNotNone(app.map.points[1])
    def test_blocked_and_unknown_cells_leave_the_map_untouched(self):
        app=self.app();app.map.mode='area'
        app.map.coverage=dict(step_km=.5,cells=[dict(position=app.map.center,los='blocked',fresnel='unknown')])
        app.lines();self.assertEqual(app.map.layer()[4].overlay,{})
        app.map.coverage['cells'][0]['los']='unknown'
        app.lines();self.assertEqual(app.map.layer()[4].overlay,{})
    def test_sparse_clear_endpoint_never_becomes_a_strip(self):
        app=self.app();app.map.mode='area'
        app.map.coverage=dict(step_km=5,cells=[dict(position=app.map.center,los='clear',fresnel='clear',sample_spacing_m=5000)])
        app.lines();marks=app.map.layer()[4].overlay
        self.assertEqual(len(marks),1)
        self.assertEqual(next(iter(marks.values()))[0],'•')

    def test_red_tint_preserves_half_block_colors_instead_of_grey_bars(self):
        from paint import ink,terminal_background
        original=ink(20,100,30,background=(15,60,90))
        glyph,style=terminal_background(' ',ink(180,35,45,background=(180,35,45)),'▀',original,.55)
        self.assertEqual(glyph,'▀')
        fore=(style>>24)&0xffffff;back=style&0xffffff
        self.assertNotEqual(fore,back)
        self.assertGreater((fore>>16)&255,(fore>>8)&255)
        self.assertNotEqual(fore,0xd6d3d6)

    def test_close_disposes_map_renderer(self):
        app=self.app();app.close()
        self.assertIsNone(app.map.renderer.completion_wakeup)
        if app.map.renderer.pool is not None:
            with self.assertRaises(RuntimeError):app.map.renderer.pool.submit(lambda:None)

if __name__=='__main__':unittest.main()
