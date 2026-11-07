import sys,unittest,time,threading
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from terrain_sites import viewshed,cached_path
from terrain_elevation import classify_path,calculate
from native_terrain_profile import TerrainProfile

class StreamingTests(unittest.TestCase):
    def test_900_mhz_fresnel_radius_matches_independent_midpoint_formula(self):
        from path_profile import profile
        for distance in (1000,10000,52000):
            result=profile([(0,0),(distance/2,0),(distance,0)],frequency_mhz=900,tx_height_m=100,rx_height_m=100)
            expected=(299792458/(900*1e6)*distance/4)**.5
            self.assertAlmostEqual(result['samples'][1]['fresnel_radius_m'],expected)
        self.assertGreater(expected,60)
    def test_frequency_heights_radius_and_fresnel_view_restore(self):
        app=TerrainProfile();self.addCleanup(app.close)
        app.restore_session(dict(fields=['5.5555,5.5555','','915','15','10'],radius_km=50,mode='area',coverage_mode='fresnel'))
        restored=TerrainProfile();self.addCleanup(restored.close);restored.restore_session(app.session_state())
        self.assertEqual([f.text for f in restored.fields[2:]],['915','15','10'])
        self.assertEqual(restored.radius_km,50);self.assertEqual(restored.map.coverage_mode,'fresnel')

    def test_streams_nearby_results_before_completion(self):
        import os,tempfile
        cache=tempfile.TemporaryDirectory();self.addCleanup(cache.cleanup)
        environment=patch.dict(os.environ,POCKET_LOS_CACHE=cache.name);environment.start();self.addCleanup(environment.stop)
        app=TerrainProfile();self.addCleanup(app.close)
        app.set_endpoint((5.5555,5.5555),False);app.radius_km=20
        published=threading.Event();release=threading.Event();self.addCleanup(release.set)
        original=app.publish_coverage
        def publish(snapshot):
            original(snapshot)
            if not published.is_set():published.set();release.wait(3)
        app.publish_coverage=publish
        app.show_los();self.assertTrue(published.wait(3))
        self.assertFalse(app.pending.done());app.poll()
        self.assertIsNotNone(app.map.coverage)
        self.assertFalse(app.map.coverage['complete'])
        self.assertLess(max(c['outer_radius_km'] for c in app.map.coverage['cells']),20)
        self.assertIn('sites tested',app.map.notice)
        release.set();until=time.monotonic()+30
        while app.pending and time.monotonic()<until:app.poll();time.sleep(.005)
        self.assertTrue(app.map.coverage['complete'])
    def test_repeated_and_extended_radius_reuse_completed_paths(self):
        cached_path.cache_clear()
        with patch('terrain_sites.classify_path',return_value=dict(los='clear',fresnel='clear',samples=2)) as classify:
            a=viewshed('5.5555,5.5555',radius_km=5)
            calls=classify.call_count
            viewshed('5.5555,5.5555',radius_km=5)
            self.assertEqual(classify.call_count,calls)
            b=viewshed('5.5555,5.5555',radius_km=10)
            self.assertEqual(classify.call_count,len(b['cells']))
        cached_path.cache_clear()
    def test_fast_classifier_agrees_with_detailed_real_profiles(self):
        start='5.5555,5.5555'
        for end in ('5.5605,5.5555','5.5555,5.5655','5.5655,5.5755','5.6155,5.5855','5.6655,5.6855'):
            fast=classify_path(start,end,frequency_mhz=144.39,tx_height_m=15,rx_height_m=10)
            full=calculate(start,end,frequency_mhz=144.39,tx_height_m=15,rx_height_m=10,count=4097)
            self.assertEqual(fast['los'],full['sampled_los'],end)
            self.assertEqual(fast['fresnel'],full['sampled_fresnel'],end)
