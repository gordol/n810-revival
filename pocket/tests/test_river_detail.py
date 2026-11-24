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
