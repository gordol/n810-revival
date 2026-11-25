"""Contracts shared by map generation, adaptive quality and the native scene."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

root=Path(__file__).resolve().parents[1]
for folder in ('graphics','shell','shell/apps/landscape-lab'):
    sys.path.insert(0,str(root/folder))

from rainier_pixels import build_world
from river_detail import RiverQuality, shade_tree


class RiverDetailTests(unittest.TestCase):
    def test_profiles_fit_native_buffers_and_keep_encounters(self):
        for high in (False,True):
            _,_,vertices,terrain,indices,spans,base,mask=build_world(high)
            self.assertLessEqual(len(vertices)//7,2_000_000)
            self.assertLessEqual(len(indices),2_000_000)
            from river_walk import channel
            water_count=6*(len(channel().rows)-1)
            self.assertTrue(all(abs(value-.35)<1e-6 for value in vertices[6:7*water_count:7]))
            self.assertNotAlmostEqual(vertices[7*water_count+6],.35)
            self.assertEqual(terrain%3,0)
            self.assertEqual(base%3,0)
            if high:
                self.assertGreater(terrain,base)
                self.assertEqual(len(mask),1024*1024)
                self.assertEqual(len(spans),count)
            else:
                self.assertEqual(terrain,base)
                self.assertEqual(len(mask),1024*1024)
                count=len(spans)
            del vertices

    def test_cached_valley_restores_game_inputs_and_rebuilds_bad_or_old_cache(self):
        import tempfile
        from array import array
        from river_scene_cache import valley_world
        plants=[('blueberry',1.,2.)]
        sample=(None,None,array('f',[0.]*42),3,array('I',[0,0,0]),[(3,1,3,0,3)],3,bytearray(1024**2))
        def generate(high,sites):
            sites[:]=plants
            return sample
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,XDG_CACHE_HOME=tmp),patch(
            'rainier_pixels.ENCOUNTERS',[None]),patch('rainier_pixels.build_world',side_effect=generate) as build:
            with patch('river_scene_cache.source_key',return_value='first'):
                valley_world(True,[])
                restored=[]
                world=valley_world(True,restored)
                self.assertEqual(world[2:5],sample[2:5])
                self.assertEqual(world[6:],sample[6:])
                self.assertEqual(restored,plants)
                build.assert_called_once()
                next(Path(tmp).rglob('*.zip')).write_bytes(b'interrupted')
                valley_world(True,[])
            with patch('river_scene_cache.source_key',return_value='new'):
                valley_world(True,[])
            self.assertEqual(build.call_count,3)

    def test_binoculars_prioritize_in_frame_wildlife_beyond_walking_range(self):
        from geometry import Vec
        from rainier_pixels import encounters
        from river_walk import site
        field,_=site()
        crowd=tuple((f'near{i}',2.,5.,1.) for i in range(50))+(('distant',0.,500.,1.),)
        spans=[(0,1,1,0,3)]*len(crowd)
        camera=(0,field.height(0,500),0,0,0)
        with patch('rainier_pixels.ENCOUNTERS',crowd):
            for optics,expected in ((None,False),((camera,.5,8),True)):
                seen=[]
                draws=encounters(field,Vec(0,0,0),spans,0,subjects=seen,optics=optics)
                self.assertLessEqual(len(draws),48)
                self.assertEqual('distant' in [s[0] for s in seen],expected)

    def test_bluff_cycles_unpicked_patches_then_fox_with_clear_terrain(self):
        import math
        from rainier_pixels import RainierView,surface
        from river_walk import BERRY_BLUFF,BUSHES,FOX,BerryTrail,channel,site
        view=RainierView.__new__(RainierView)
        view.lens=view.regional=False
        view.binoculars=True
        view.album=[]
        view.zoom=4.
        view.trail=BerryTrail()
        view.trail.picked.add(BUSHES[0])
        field=channel().bed_field(site()[0])
        view.world=(field,)
        view.camera=(0,0,0,0)
        view.bluff_target=None
        for tx,tz in (BUSHES[1],BUSHES[2],FOX,BUSHES[1]):
            self.assertTrue(view.scene_tap(2,28,40,30))
            x,z,yaw,pitch=view.camera=view.trip_pose
            self.assertEqual((x,z),BERRY_BLUFF)
            self.assertEqual(view.bluff_target,(tx,tz))
            self.assertAlmostEqual(yaw,math.atan2(tx-x,tz-z))
            for i in range(100):
                t=i/100
                ray_y=surface(field,x,z)+1.25-math.tan(pitch)*math.hypot(tx-x,tz-z)*t
                self.assertGreater(ray_y,surface(field,x+(tx-x)*t,z+(tz-z)*t))
        self.assertEqual(view.trail.picked,{BUSHES[0]})
        self.assertFalse(view.trail.fed)

    def test_canopy_height_is_centered_on_the_tree(self):
        mask=bytearray(512*512)
        shade_tree(mask,0,0,14)
        self.assertGreater(mask[256*512+256],mask[256*512+258])
        self.assertEqual(mask[249*512+249],0)

    def test_regional_forest_survives_travel_and_stops_above_treeline(self):
        from geometry import HeightField,Vec
        from rainier_habitat import regional_stand
        field=HeightField(3,3,Vec(-512,0,-512),512.,512.,(900.,)*9)
        ground=lambda f,x,z:900.
        trees,mask=regional_stand(field,900,0,0,ground,None)
        other,adjacent=regional_stand(field,900,96,0,ground,None)
        self.assertTrue(trees and other)
        self.assertGreater(max(trees[::7]),400)  # Beyond the detailed near stand.
        self.assertLess(len(trees)//7,250000)
        overlap=[(z+256)*512+x+256 for z in range(-70,70) for x in range(10,75)]
        self.assertTrue(any(mask[k] for k in overlap))
        self.assertTrue(all(mask[k]==adjacent[k-96] for k in overlap))
        alpine,mask=regional_stand(field,3000,0,0,lambda f,x,z:3000.,None)
        self.assertFalse(alpine or any(mask))

    def test_sustained_slowdown_only(self):
        with patch.dict(os.environ,POCKET_RIVER_QUALITY='auto'), patch('os.sysconf',return_value=65536):
            quality=RiverQuality()
        for t in (0,.05,.16,5.,5.05):quality.frame(t)
        self.assertTrue(quality.high)
        for i in range(25):quality.frame(6.+i*.1)
        self.assertFalse(quality.high)
        with patch.dict(os.environ,POCKET_RIVER_QUALITY='high'):
            fixed=RiverQuality()
        for i in range(40):fixed.frame(i*.1)
        self.assertTrue(fixed.high)
