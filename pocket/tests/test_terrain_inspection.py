import sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from native_terrain_profile import TerrainProfile
from terrain_qth import QTH

class InspectionTests(unittest.TestCase):
    def test_return_to_map_fits_path_and_preserves_obstruction(self):
        app=TerrainProfile();self.addCleanup(app.close)
        self.assertTrue(app.map.base.preview)
        app.set_endpoint((47.252900,-122.444300),False);app.set_endpoint((46.973167,-123.138167))
        app.calculate();self.wait(app)
        for pointer in (False,True):
            app.screen='profile';app.map.span=.01
            if pointer:app.pointer(2,0,app.width)
            else:app.key('m')
            self.assertEqual(app.screen,'map');self.assertGreater(app.map.span,50)
            self.assertEqual(app.map.inspect_point,app.result['bottleneck'])
    def test_offscreen_sample_is_reported_and_marked_at_map_edge(self):
        app=TerrainProfile();self.addCleanup(app.close)
        app.width=120;app.height=40
        app.set_endpoint((47.252900,-122.444300),False);app.set_endpoint((46.973167,-123.138167))
        app.calculate();self.wait(app)
        app.map.center=app.map.points[0];app.map.span=.5
        until=time.monotonic()+5
        while time.monotonic()<until:
            lines=app.lines()
            if app.map.image_view==(app.map.center,app.map.span) and app.layer():break
            time.sleep(.005)
        self.assertIn('OFF-SCREEN','\n'.join(lines))
        self.assertIn('X', ''.join(char for char,style in app.layer()[4].overlay.values()))
        camera=app.map.center,app.map.span
        app.key('x');self.assertEqual((app.map.center,app.map.span),camera)
        app.fit_path()
        until=time.monotonic()+5
        while time.monotonic()<until:
            lines=app.lines()
            if app.map.image_view==(app.map.center,app.map.span):break
            time.sleep(.005)
        self.assertIn('X marked on map','\n'.join(lines))
        self.assertIn('X', ''.join(char for char,style in app.layer()[4].overlay.values()))
    def test_extreme_zoom_has_contiguous_visible_path(self):
        from terrain_point_map import visible_path
        points=visible_path((-100000,-100000),(100000,100000),120,45)
        self.assertEqual(points[0],(0,0));self.assertEqual(points[-1],(44,44))
        self.assertTrue(all(max(abs(a[i]-b[i]) for i in (0,1))<=1 for a,b in zip(points,points[1:])))
    def test_map_obstruction_key_calculates_without_moving_camera(self):
        app=TerrainProfile();self.addCleanup(app.close)
        app.set_endpoint((5.5555,5.5555),False);app.set_endpoint((5.3386667,4.9473333))
        camera=app.map.center,app.map.span
        app.key('x');self.wait(app)
        self.assertEqual(app.screen,'map')
        self.assertEqual((app.map.center,app.map.span),camera)
    def test_callsign_profile_queues_behind_active_worker(self):
        from concurrent.futures import Future
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'qth.msgpack';QTH(path).save(5.5555,5.5555,height_m=15)
            app=TerrainProfile(qth_path=path);self.addCleanup(app.close)
            old=Future();app.pending=old;app.job='coverage'
            self.assertTrue(app.profile_to_location('VCAPK',(46.9731667,-123.1381667)))
            old.set_result(None);app.poll();self.wait(app)
            self.assertEqual(app.job,'profile');self.assertEqual(app.target_label,'VCAPK')
    def wait(self,app):
        until=time.monotonic()+5
        while app.pending and time.monotonic()<until:app.poll();time.sleep(.005)
        self.assertIsNotNone(app.result,app.error)
    def test_profile_and_map_share_exact_selected_sample(self):
        app=TerrainProfile();self.addCleanup(app.close)
        app.set_endpoint((5.5555,5.5555),False);app.set_endpoint((5.3386667,4.9473333))
        app.screen='profile';app.calculate();self.wait(app)
        point=app.result['bottleneck'];self.assertIn('coordinate',point)
        app.key('i');self.assertLessEqual(app.profile_zoom[1]-app.profile_zoom[0],500)
        self.assertIn('X ', '\n'.join(app.lines()))
        camera=app.map.center,app.map.span
        app.key('x');self.assertEqual(app.screen,'map')
        self.assertEqual((app.map.center,app.map.span),camera);self.assertEqual(app.map.inspect_point,point)
    def test_qth_survives_other_endpoints_and_new_instance(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'qth.msgpack';QTH(path).save(5.5555,5.5555,height_m=15)
            app=TerrainProfile(qth_path=path);self.addCleanup(app.close)
            app.set_endpoint((47.4,-122.3),False);app.clear_selection(clear_all=True)
            next_app=TerrainProfile(qth_path=path);self.addCleanup(next_app.close)
            self.assertEqual(next_app.map.qth,(5.5555,5.5555))
            self.assertEqual(next_app.fields[3].text,'15')
            next_app.resolve_station=lambda call:(46.9731667,-123.1381667) if call=='VCAPK' else None
            next_app.open_call()
            for char in 'VCAPK':next_app.key(char)
            next_app.key('\r');self.wait(next_app)
            self.assertEqual(next_app.result['start'],(5.5555,5.5555))
            self.assertEqual(next_app.target_label,'VCAPK')
    def test_near_qth_view_keeps_full_path_ray_geometry(self):
        app=TerrainProfile();self.addCleanup(app.close)
        app.set_endpoint((5.5555,5.5555),False);app.set_endpoint((5.3386667,4.9473333))
        app.screen='profile';app.calculate();self.wait(app);original=app.result
        app.key('z');self.assertEqual(app.profile_zoom,(0,1000));self.assertIs(app.result,original)
        self.assertLessEqual(app.selected_sample['distance_m'],1000)
    def test_graph_cursor_never_moves_fixed_obstruction(self):
        app=TerrainProfile();self.addCleanup(app.close)
        app.width=120;app.height=42
        app.set_endpoint((5.5555,5.5555),False);app.set_endpoint((5.3386667,4.9473333))
        app.screen='profile';app.calculate();self.wait(app)
        obstruction=dict(app.result['bottleneck']);app.lines()
        app.pointer(75,20,120)
        self.assertIsNotNone(app.selected_sample)
        self.assertEqual(app.result['bottleneck'],obstruction)
        app.lines();self.assertTrue(any(span[3]=='obstruction' and span[2]>=3 for span in app.spans()))
        app.key('x');self.assertEqual(app.map.inspect_point,obstruction)
