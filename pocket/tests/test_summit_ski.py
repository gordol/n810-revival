"""Exercise a whole descent and return loop without a device or terrain download."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'graphics'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from summit_ski import LENGTH,SkiRun,location


class SkiTests(unittest.TestCase):
    def test_glide_brake_carve_runout_and_return(self):
        run=SkiRun()
        def ground(x,z):return 3200+.24*(x+z)
        run.action('brake')
        run.steer=.8
        for _ in range(100):run.advance(.05,ground)
        self.assertGreater(run.lane,0)
        self.assertLessEqual(run.speed,8)
        run.action('brake')
        d=run.distance
        run.advance(.1,ground)
        self.assertEqual(run.distance,d)
        run.action('brake')
        for _ in range(1200):
            run.advance(.05,ground)
            if run.mode=='bottom':break
        self.assertEqual((run.mode,run.distance,run.speed),('bottom',LENGTH,0))
        self.assertTrue(run.tracks)
        run.action('climb')
        for _ in range(15):
            run.action('reach')
            for _ in range(26):pose=run.advance(.05,ground)
        self.assertEqual(run.mode,'ready')
        self.assertEqual(pose[:2],location(0.))
