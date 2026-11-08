from reference_fixtures import activate
activate()
"""Reproduce loss of local LOS when extending radius and using dense terminals."""
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from terrain_sites import viewshed
from offline_map import raster_size

class ResolutionTests(unittest.TestCase):
    def test_expanding_radius_retains_every_local_result(self):
        start='47.19,-122.53'
        small=viewshed(start,radius_km=1,tx_height_m=15,rx_height_m=10)
        large=viewshed(start,radius_km=50,tx_height_m=15,rx_height_m=10)
        local=lambda result:{tuple(c['position']):(c['los'],c['fresnel']) for c in result['cells'] if c['outer_radius_km']<=1}
        self.assertEqual(local(small),local(large))
        self.assertGreater(sum(c['los']=='clear' for c in small['cells']),0)
    def test_dense_sampling_adds_points_not_larger_red_blocks(self):
        result=dict(los='clear',fresnel='clear',resolution_m=10)
        with patch('terrain_sites.cached_path',return_value=result):
            small=viewshed('47.19,-122.53',radius_km=10,grid_steps=6)
            dense=viewshed('47.19,-122.53',radius_km=10,grid_steps=24)
        self.assertGreater(len(dense['cells']),len(small['cells'])*10)
        self.assertLess(min(c['step_km'] for c in dense['cells']),.05)
    def test_dense_terminal_renders_beyond_old_420_by_140_cap(self):
        self.assertEqual(raster_size(650,240),(650,240))
        self.assertEqual(raster_size(100,30),(100,30))
        w,h=raster_size(10000,10000)
        self.assertLessEqual(w*h,2097152)
