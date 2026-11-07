import sys,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from terrain_sites import search
from native_terrain_profile import TerrainProfile

class SiteTests(unittest.TestCase):
    def test_real_candidates_are_bounded_ranked_and_target_unchanged(self):
        result=search('47.25,-122.50','47.60,-122.20')
        self.assertEqual(len(result['candidates'])+result['skipped'],13)
        self.assertGreater(len(result['candidates']),0)
        self.assertEqual(result['target'],(47.60,-122.20))
        for item in result['candidates']:
            self.assertLessEqual(item['offset_km'],2)
            self.assertFalse(item['profile']['coarse'])
            self.assertEqual(item['profile']['end'],result['target'])
        keys=[(c['los']=='clear',c['fresnel']=='clear',c['clearance_m'],-c['offset_km']) for c in result['candidates']]
        self.assertEqual(keys,sorted(keys,reverse=True))
    def test_coarse_region_does_not_offer_false_site_precision(self):
        with self.assertRaisesRegex(ValueError,'detailed elevations'):search('50,-123','50.1,-123')
    def test_cancel_stops_before_sampling(self):
        self.assertIsNone(search('47.25,-122.50','47.60,-122.20',cancelled=lambda:True))
    def test_app_search_and_candidate_selection(self):
        app=TerrainProfile();self.addCleanup(app.close)
        app.set_endpoint((47.25,-122.50),False);app.set_endpoint((47.60,-122.20),True)
        self.assertTrue(app.nearby());self.assertEqual(app.screen,'sites')
        until=time.monotonic()+5
        while app.pending and time.monotonic()<until:app.poll();time.sleep(.005)
        self.assertIsNotNone(app.sites,app.error)
        target=app.fields[1].text
        app.key('down');app.key('\r')
        self.assertEqual(app.screen,'profile');self.assertEqual(app.fields[1].text,target)
        self.assertIsNotNone(app.result)

if __name__=='__main__':unittest.main()

class CoverageTests(unittest.TestCase):
    def test_overlay_real_data_and_roof_height(self):
        from terrain_sites import viewshed
        low=viewshed('47.25,-122.5',radius_km=1,tx_height_m=2,rx_height_m=2)
        high=viewshed('47.25,-122.5',radius_km=1,tx_height_m=100,rx_height_m=2)
        self.assertEqual(len(low['cells']),112)
        self.assertEqual(low['center'],(47.25,-122.5))
        self.assertGreaterEqual(sum(c['los']=='clear' for c in high['cells']),sum(c['los']=='clear' for c in low['cells']))
        self.assertTrue(all(c['los'] in ('clear','blocked','unknown') for c in low['cells']))
    def test_coarse_coverage_stays_unknown(self):
        from terrain_sites import viewshed
        r=viewshed('50,-123',radius_km=1)
        self.assertTrue(all(c['los']=='unknown' for c in r['cells']))
    def test_radius_changes_are_visible_and_long_ranges_persist(self):
        app=TerrainProfile();self.addCleanup(app.close);app.toggle_mode()
        app.key('r')
        self.assertEqual(app.radius_km,10)
        self.assertIn('Radius 10 km R',app.lines()[1])
        self.assertIn('Radius 10 km selected',app.navigation_modal_hint()[1])
        app.key('r');app.key('r');self.assertEqual(app.radius_km,50)
        app.key('r');self.assertEqual(app.radius_km,100)
        self.assertIn('Radius 100 km R',app.lines()[1])
        restored=TerrainProfile();self.addCleanup(restored.close)
        restored.restore_session(app.session_state());self.assertEqual(restored.radius_km,100)
    def test_long_range_is_accepted_without_loading_on_cancel(self):
        from terrain_sites import viewshed
        self.assertIsNone(viewshed('47.25,-122.5',radius_km=100,cancelled=lambda:True))

    def test_los_preserves_camera_and_uses_latest_radius(self):
        app=TerrainProfile();self.addCleanup(app.close)
        app.set_endpoint((47.25,-122.5),False)
        app.map.center=(47.4,-122.3);app.map.span=150
        app.key('R');self.assertEqual(app.radius_km,10)
        self.assertTrue(app.key('L'))
        until=time.monotonic()+8
        while app.pending and time.monotonic()<until:app.poll();time.sleep(.005)
        self.assertIsNotNone(app.map.coverage,app.error)
        self.assertEqual(app.map.coverage['radius_km'],10)
        self.assertEqual(app.map.center,(47.4,-122.3));self.assertEqual(app.map.span,150)
    def test_l_after_radius_change_during_job_queues_latest_request(self):
        from concurrent.futures import Future
        app=TerrainProfile();self.addCleanup(app.close)
        app.set_endpoint((47.25,-122.5),False)
        old=Future();app.pending=old;app.job='coverage'
        app.key('r');self.assertEqual(app.radius_km,10)
        self.assertTrue(app.key('l'));self.assertTrue(app._queued_los)
        old.set_result(None);app.poll()
        until=time.monotonic()+8
        while app.pending and time.monotonic()<until:app.poll();time.sleep(.005)
        self.assertEqual(app.map.coverage['radius_km'],10)
        self.assertFalse(app._queued_los)

    def test_frequency_changes_fresnel_not_geometric_los(self):
        import math
        from path_profile import profile
        samples=[(0,0),(5000,0),(10000,0)]
        low=profile(samples,frequency_mhz=7.1,tx_height_m=15,rx_height_m=15)
        high=profile(samples,frequency_mhz=2400,tx_height_m=15,rx_height_m=15)
        self.assertEqual(low['sampled_los'],high['sampled_los'])
        self.assertEqual(low['sampled_fresnel'],'obstructed');self.assertEqual(high['sampled_fresnel'],'clear')
        self.assertAlmostEqual(low['samples'][1]['fresnel_radius_m']/high['samples'][1]['fresnel_radius_m'],math.sqrt(2400/7.1))
    def test_band_list_scrolls_and_fresnel_selector_is_visible(self):
        app=TerrainProfile();self.addCleanup(app.close);app.height=12
        app.key('f');app.key('end');text='\n'.join(app.lines())
        self.assertIn('10 GHz',text)
        app.key('home');self.assertIn('2200 m','\n'.join(app.lines()))
        app.select_band(next(i for i,(label,_) in enumerate(app.bands) if label.startswith('6 m')))
        self.assertEqual(app.fields[2].text,'50.125')
        app.toggle_mode();app.key('j');text='\n'.join(app.lines())
        self.assertIn('F60%',text);self.assertEqual(app.map.coverage_mode,'fresnel')

    def test_radius_alone_recalculates_enabled_overlay_and_keeps_camera(self):
        app=TerrainProfile();self.addCleanup(app.close)
        app.set_endpoint((47.25,-122.5),False);app.map.span=123;app.map.center=(47.3,-122.4)
        app.show_los();until=time.monotonic()+8
        while app.pending and time.monotonic()<until:app.poll();time.sleep(.005)
        self.assertEqual(app.map.coverage['radius_km'],5)
        app.key('r')
        self.assertIsNotNone(app.pending)
        until=time.monotonic()+8
        while app.pending and time.monotonic()<until:app.poll();time.sleep(.005)
        self.assertEqual(app.map.coverage['radius_km'],10)
        self.assertEqual(app.map.span,123);self.assertEqual(app.map.center,(47.3,-122.4))
    def test_rapid_radius_changes_keep_only_latest_automatic_request(self):
        from concurrent.futures import Future
        app=TerrainProfile();self.addCleanup(app.close)
        app.set_endpoint((47.25,-122.5),False);app._los_enabled=True
        app.pending=Future();old=app.pending;app.job='coverage'
        app.key('r');app.key('r');app.key('r');self.assertEqual(app.radius_km,50)
        old.set_result(None);app.poll();until=time.monotonic()+8
        while app.pending and time.monotonic()<until:app.poll();time.sleep(.005)
        self.assertEqual(app.map.coverage['radius_km'],50)

    def test_preset_selection_and_overlay_app(self):
        app=TerrainProfile();self.addCleanup(app.close)
        app.key('f');self.assertEqual(app.screen,'bands');app.key('down');app.key('\r')
        self.assertEqual(app.fields[2].text,'223.5')
        app.set_endpoint((47.25,-122.5),False);app.radius_km=1
        app.key('l');until=time.monotonic()+5
        while app.pending and time.monotonic()<until:app.poll();time.sleep(.005)
        self.assertIsNotNone(app.map.coverage,app.error)
        self.assertIn('Red clear',app.map.notice)
        until=time.monotonic()+5
        while time.monotonic()<until:
            app.lines()
            if app.map.image:break
            time.sleep(.01)
        self.assertIsNotNone(app.layer())
        app.set_endpoint((47.26,-122.5),False);self.assertIsNone(app.map.coverage)
