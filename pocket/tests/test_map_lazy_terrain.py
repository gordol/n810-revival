from reference_fixtures import maps
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Flat and close RGB views must not decode the filtered elevation pack."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lazy_terrain_map',ROOT/'shell/vendor/packet-console/n810-map-next.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class LazyTerrainTests(unittest.TestCase):
 def test_flat_and_close_rgb_do_not_read_filtered_pack(self):
  for span,terrain in ((2.,True),(100.,False)):
   with self.subTest(span=span,terrain=terrain):
    engine=m.Engine(maps(),style='rgb')
    with patch.object(m,'Terrain',side_effect=AssertionError('unneeded terrain decode')):
     cells,legend=engine.prepare(m.Viewport((5.53555,5.58555),span,30,12),terrain=terrain)
    self.assertEqual(len(cells),360);self.assertFalse(engine._terrain_loaded)
 def test_filtered_pack_is_loaded_once_when_requested(self):
  engine=m.Engine(maps(),style='rgb')
  with patch.object(m,'Terrain',return_value=object()) as load:
   first=engine.terrain;self.assertIs(first,engine.terrain);load.assert_called_once()
  self.assertIsNone(engine._atlas)

class TerrainCoverageTests(unittest.TestCase):
 def test_uncovered_layers_are_skipped_before_decoding_level_arrays(self):
  terrain=m.Terrain.__new__(m.Terrain);terrain.nodata=-32768
  terrain.layers=[dict(bbox=[10.,10.,11.,11.],levels=[])]
  rows,shades,selected=terrain.sample(m.Viewport((47.,-122.),2.,30,12))
  self.assertEqual(selected,[])
  self.assertTrue(all(value==terrain.nodata for row in rows for value in row))
  self.assertTrue(all(value==255 for row in shades for value in row))

if __name__=='__main__':unittest.main()
