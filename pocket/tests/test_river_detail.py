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
                self.assertEqual(len(mask),512*512)
                self.assertEqual(len(spans),count)
            else:
                self.assertEqual(terrain,base)
                self.assertIsNone(mask)
                count=len(spans)
            del vertices

    def test_shadows_follow_the_tree_and_light(self):
        mask=bytearray(512*512)
        shade_tree(mask,0,0,14)
        self.assertGreater(mask[258*512+259],0)
        self.assertEqual(mask[249*512+249],0)

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
