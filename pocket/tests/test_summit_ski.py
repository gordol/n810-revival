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

    def test_long_courses_jump_bypass_and_brake_on_landing(self):
        from summit_ski import COURSES
        game=SkiRun()
        for course in COURSES[1:]:
            game.action('course')
            self.assertIs(game.course,course)
            lip,lane=course.jumps[0]
            def height(x,z):return 3000.
            for offset,expected in ((0,1),(7,0)):
                game.reset()
                game.action('brake')
                game.distance=lip-2
                game.lane=lane+offset
                game.speed=8
                airborne=False
                for _ in range(80):
                    game.advance(.05,height)
                    if game.air_y is not None and not airborne:
                        self.assertGreater(game.lift,0.)
                        game.action('brake')
                        airborne=True
                self.assertEqual(game.landings,expected)
                self.assertEqual(game.mode,'braked' if expected else 'ski')
                self.assertEqual(game.lift,0.)
            game.distance=course.length-.01
            game.advance(.1,height)
            self.assertEqual(game.mode,'bottom')
            self.assertEqual(game.finish_action,'reset')
