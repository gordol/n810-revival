"""Fresh, fictional area through the actual OSM, terrain and map-reader pipeline."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'shell'))
import maps
import test_elevation_pipeline as fixtures

HAS_GIS=bool(importlib.util.find_spec('osmium') and importlib.util.find_spec('shapely'))


class MapBuildTests(unittest.TestCase):
    def test_area_selection_is_explicit_and_saved_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'data'
            with patch('urllib.request.urlopen',side_effect=AssertionError('Unexpected network')):
                with self.assertRaises(SystemExit):maps.main(['plan','--output',str(output)])
                self.assertFalse(output.exists())
                maps.main(['configure','--bbox','1','1','1.0064','1.0064','--output',str(output)])
                maps.main(['plan','--output',str(output)])
            self.assertEqual(json.loads((output/'map-area.json').read_text())['bbox'],[1,1,1.0064,1.0064])

    @unittest.skipUnless(HAS_GIS,'OSM build integration needs the maps build-host dependencies')
    def test_fresh_osm_build_and_cached_elevation_feed_the_real_renderer_without_mirrors(self):
        fixture=fixtures.PipelineTests();fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.pack()
        source=fixture.root/'fixture.osm'
        source.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6" generator="fictional-test-fixture">
 <node id="1" lat="0.999" lon="1.0032" version="1"/>
 <node id="2" lat="1.008" lon="1.0032" version="1"/>
 <node id="3" lat="1.001" lon="1.001" version="1"/>
 <node id="4" lat="1.005" lon="1.002" version="1"/>
 <node id="5" lat="1.003" lon="1.0015" version="1"><tag k="place" v="town"/><tag k="name" v="Fixture town"/></node>
 <way id="10" version="1"><nd ref="1"/><nd ref="2"/><tag k="natural" v="coastline"/></way>
 <way id="11" version="1"><nd ref="3"/><nd ref="4"/><tag k="highway" v="primary"/><tag k="name" v="Fixture road"/></way>
</osm>''')
        options=['--output',str(fixture.data)]
        with patch('urllib.request.urlopen',side_effect=AssertionError('Unexpected network')),patch('shutil.copyfile',side_effect=AssertionError('Duplicate resource copy')):
            maps.main(['configure',*options,'--source',str(source),'--bbox','1','1','1.0064','1.0064'])
            maps.main(['download',*options])
            maps.main(['build',*options])
            maps.main(['terrain',*options])
            with patch.object(maps,'run',side_effect=AssertionError('Unchanged inputs rebuilt')),patch.object(maps,'build_views',side_effect=AssertionError('Duplicate build')):
                maps.main(['build',*options])
        self.assertTrue((fixture.data/'maps/walk-layers.n8w').is_file())
        self.assertFalse(list(fixture.data.rglob('terrain-next.n8t')))
        self.assertFalse((fixture.data/'elevation-lakewood').exists())
        from offline_map import Renderer
        with patch.dict(os.environ,{'POCKET_DATA_ROOT':str(fixture.data),'XDG_CACHE_HOME':str(fixture.root/'cache')}):
            renderer=Renderer();self.addCleanup(renderer.close)
            deadline=time.monotonic()+30;image=None
            while time.monotonic()<deadline:
                image=renderer.frame((1.0032,1.0032),.5,30,12,True,True)
                if image or renderer.error:break
                time.sleep(.01)
            self.assertIsNotNone(image,renderer.error)
            self.assertEqual(renderer.maps,fixture.data/'maps')
            self.assertIn('Local DEM',image.legend)
            self.assertTrue(image.cells)

if __name__=='__main__':unittest.main()
