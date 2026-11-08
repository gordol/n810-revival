from reference_fixtures import activate
activate()
import sys,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from terrain_worker import coverage
from terrain_sites import viewshed

class WorkerTests(unittest.TestCase):
    def test_process_preserves_results_and_streams_progress(self):
        progress=[]
        expected=viewshed('47.25,-122.5',radius_km=1)
        actual=coverage('47.25,-122.5',radius_km=1,progress=progress.append)
        self.assertEqual(actual,expected)
        self.assertTrue(progress);self.assertTrue(progress[-1]['complete'])
    def test_cancellation_stops_long_job_after_first_progress(self):
        progress=[];started=time.monotonic()
        result=coverage('47.25,-122.5',radius_km=100,grid_steps=24,
                        progress=progress.append,cancelled=lambda:bool(progress))
        self.assertIsNone(result);self.assertTrue(progress)
        self.assertLess(time.monotonic()-started,5)

    def test_visible_raster_is_bounded_and_reuses_exact_path_tests(self):
        from unittest.mock import patch
        viewport=((47.25,-122.5),2.,12,6)
        with patch('terrain_sites.cached_path',return_value=dict(los='clear',fresnel='clear',resolution_m=11)) as classify:
            result=viewshed('47.25,-122.5',radius_km=5,viewport=viewport,refine_only=True)
        self.assertEqual(len(result['cells']),72)
        self.assertEqual(classify.call_count,72)
        self.assertTrue(all('raster_km' in cell for cell in result['cells']))
        distances=[(cell['position'][0]-47.25)**2+((cell['position'][1]+122.5)*.68)**2 for cell in result['cells']]
        self.assertLess(distances[0],distances[-1])

    def test_refinement_preserves_broad_results_and_waits_for_confirmed_zoom(self):
        from native_terrain_profile import TerrainProfile
        from unittest.mock import patch
        app=TerrainProfile();self.addCleanup(app.close)
        app._los_enabled=True;app.map.coverage=dict(cells=[dict(position=(47.,-122.),los='clear')])
        app._coverage_view=app.coverage_view();app.map.span/=2
        with patch.object(app,'show_los',return_value=True) as compute:
            app.map.base.target_box.choose(app.map.center,app.map.span)
            app.poll();compute.assert_not_called()
            app.map.base.target_box.cancel();app.poll();compute.assert_called_once_with(refine=True)
        app._retained_coverage=app.map.coverage
        merged=app.merge_coverage(dict(cells=[dict(position=(47.1,-122.1),los='clear')]))
        self.assertEqual(len(merged['cells']),2)

    def test_completed_view_cache_tracks_settings_and_rejects_corruption(self):
        import os,tempfile
        import terrain_cache
        from unittest.mock import patch
        result=dict(complete=True,center=(47.25,-122.5),cells=[dict(position=(47.25,-122.5),los='clear',raster_km=(.1,.2))])
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,POCKET_LOS_CACHE=folder):
            key=terrain_cache.identity('47.25,-122.5',dict(radius_km=5,frequency_mhz=144))
            self.assertNotEqual(key,terrain_cache.identity('47.25,-122.5',dict(radius_km=5,frequency_mhz=915)))
            terrain_cache.write(key,result);self.assertEqual(terrain_cache.read(key),result)
            (Path(folder)/(key+'.msgpack')).write_bytes(b'broken')
            self.assertIsNone(terrain_cache.read(key))

    def test_visible_cells_match_detailed_profiles_on_fixture_terrain(self):
        from terrain_elevation import calculate
        start='47.25290000,-122.44430000'
        result=viewshed(start,radius_km=1,frequency_mhz=915,tx_height_m=15,
                        viewport=((47.25290000,-122.44430000),1.,12,6),refine_only=True)
        for cell in result['cells'][::max(1,len(result['cells'])//4)]:
            end=','.join(str(v) for v in cell['position'])
            full=calculate(start,end,frequency_mhz=915,tx_height_m=15,rx_height_m=2,count=4097)
            self.assertEqual(cell['los'],full['sampled_los'])
            self.assertEqual(cell['fresnel'],full['sampled_fresnel'])
