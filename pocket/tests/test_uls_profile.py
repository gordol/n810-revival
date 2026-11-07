import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'shell'))
from native_uls import ULSLookup
from terrain_elevation import calculate,elevation,grid
from native_terrain_profile import TerrainProfile
from uls_directory import lookup


class ULSTests(unittest.TestCase):
    def test_escape_leaves_controls_without_changing_query_or_result(self):
        from native_navigation import navigation
        app=ULSLookup(database='/example')
        self.addCleanup(app.close)
        nav=navigation(app)
        nav.key('\x1b')
        self.assertEqual(app.navigation_focus(),'window')
        nav.key('\x1b')
        self.assertEqual(app.navigation_focus(),'window')
        self.assertEqual(app.call.text,'')
        nav.key('\t')
        self.assertEqual(app.navigation_focus(),'call')

    def test_lookup_is_background_and_render_does_not_query(self):
        calls=[]
        def query(path,call):
            calls.append((path,call))
            return dict(station=call,base_callsign=call,record=None,source_data_date='2026-11-01',source_age_days=1)
        app=ULSLookup(database='/example',query=query)
        self.addCleanup(app.close)
        app.lines();self.assertFalse(calls)
        app.select_callsign('N0CALL-7')
        end=time.monotonic()+3
        while app.pending and time.monotonic()<end:app.poll();time.sleep(.001)
        self.assertFalse(app.pending)
        self.assertEqual(calls,[('/example','N0CALL-7')])
        self.assertIn('No FCC license found','\n'.join(app.lines()))
        for _ in range(10):app.lines()
        self.assertEqual(len(calls),1)

    def test_database_path_only_in_settings(self):
        app=ULSLookup(database='/private/fcc.sqlite');self.addCleanup(app.close)
        self.assertNotIn('/private/fcc.sqlite','\n'.join(app.lines()))
        app.key('\t');app.key('\r');self.assertIn('/private/fcc.sqlite','\n'.join(app.lines()))
        app.key('escape');self.assertNotIn('/private/fcc.sqlite','\n'.join(app.lines()))

    def test_station_keyboard_lookup_does_not_open_map(self):
        from types import SimpleNamespace
        from station_workspace import Stations,Context
        context=Context();context.target={'call':'W1AW'}
        directory=SimpleNamespace(context=context)
        opened=[];app=Stations(directory,lambda:opened.append('map'));self.addCleanup(app.close)
        app.sync=lambda:None;app.calls=('W1AW',);app.open_uls=lambda call:opened.append(call)
        from native_navigation import native_key
        self.assertTrue(native_key(app,'u'));self.assertEqual(opened,['W1AW'])

    def test_filtered_station_lookup_works_outside_the_filter_editor(self):
        from types import SimpleNamespace
        from station_workspace import Stations,Context
        from native_navigation import native_key,navigation
        context=Context();context.target={'call':'W1AW'}
        app=Stations(SimpleNamespace(context=context),lambda:self.fail('Lookup opened map'))
        self.addCleanup(app.close)
        app.sync=lambda:None;app.calls=('W1AW',);app.query='W1'
        app.list.query='W1';opened=[];app.open_uls=opened.append
        for pane in ('stations','details'):
            navigation(app).select(pane)
            self.assertTrue(native_key(app,'u'))
        self.assertEqual(opened,['W1AW','W1AW'])
        navigation(app).select('filter')
        native_key(app,'u')
        self.assertEqual(app.query,'W1u')
        self.assertEqual(opened,['W1AW','W1AW'])

    def test_real_database_known_club_and_ssid(self):
        path=ROOT/'data/uls.sqlite'
        if not path.exists():self.skipTest('Real prepared FCC snapshot not installed')
        row=lookup(path,'W1AW-7')
        self.assertEqual(row['record']['name'],'ARRL HQ OPERATORS CLUB')
        self.assertEqual(row['record']['callsign'],'W1AW')
        self.assertEqual(row['station'],'W1AW-7')
        self.assertEqual(row['source_data_date'],'2026-11-01')

    def test_missing_database_never_created(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'missing.sqlite'
            with self.assertRaises(ValueError):lookup(path,'N0CALL')
            self.assertFalse(path.exists())

    def test_message_context_uses_aprs_callsign_not_mesh_identity(self):
        from native_messages import Messages
        app=Messages('N0DEM')
        app.update(['12:00:00 W1AW-7>APRS ctl=03 pid=f0 :N0DEM    :Hello'])
        self.assertEqual(app.selected_entities()[0].key,'W1AW-7')
        app.protocol='reticulum'
        self.assertEqual(app.selected_entities(),())


class ProfileTests(unittest.TestCase):
    def test_grid_uses_existing_usgs_asset_and_exact_sample_centers(self):
        metadata,values=grid()
        self.assertIn('USGS',metadata['source'])
        self.assertEqual(elevation(metadata['latitude_first'],metadata['longitude_first']),values[0])
        self.assertIsNone(elevation(0,0))

    def test_real_path_profile_retains_geography_and_source(self):
        result=calculate('46.72,-121.90','46.90,-121.60',count=129)
        self.assertEqual(result['missing_samples'],0)
        self.assertIn('USGS',result['source'])
        self.assertGreater(max(row['elevation_m'] for row in result['samples']),2000)
        self.assertGreater(result['distance_m'],20000)
        self.assertIsNotNone(result['adaptive_sampling'])

    def test_no_synthetic_fallback_outside_coverage(self):
        with self.assertRaisesRegex(ValueError,'No synthetic fallback'):
            calculate('40.2,-122.5','40.3,-122.5')

    def test_profile_app_worker_and_render(self):
        app=TerrainProfile();self.addCleanup(app.close)
        app.set_endpoint((46.72,-121.90),end=False);app.set_endpoint((46.90,-121.60))
        self.assertTrue(app.calculate())
        end=time.monotonic()+3
        while app.pending and time.monotonic()<end:app.poll();time.sleep(.001)
        self.assertIsNotNone(app.result,app.error)
        app.screen='profile'
        text='\n'.join(app.lines())
        self.assertIn('USGS',text);self.assertIn('LOS',text)
        self.assertIn('*',text);self.assertFalse(app.pending)


if __name__=='__main__':unittest.main()
