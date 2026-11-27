"""Exercise a whole descent and return loop without a device or terrain download."""
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'graphics'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from pnw.summit_ski import LENGTH,SkiRun,location


class SkiTests(unittest.TestCase):
    def test_glide_brake_carve_runout_and_return(self):
        run=SkiRun()
        def ground(x,z):return 3200+.24*(x+z)
        run.action('brake')
        run.steer=.8
        for _ in range(100):run.advance(.05,ground)
        self.assertGreater(run.lane,0)
        self.assertGreater(run.speed,5.5)
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
        from pnw.summit_ski import COURSES
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

    def test_assisted_small_drags_and_release(self):
        ground=lambda x,z:3200+.4*(x+z)
        def glide(assist,steer,speed=5.5):
            run=SkiRun()
            run.assist=assist
            run.action('brake')
            run.speed=speed
            run.steer=steer
            for _ in range(20):run.advance(.05,ground)
            return run
        self.assertEqual(glide(True,.10).lane,glide(True,0.).lane)
        gentle=glide(True,.45)
        self.assertGreater(gentle.lane,0.)
        self.assertAlmostEqual(gentle.lane,glide(True,.45,25.).lane)
        self.assertLess(gentle.lane,glide(False,.45).lane*.35)
        self.assertGreater(glide(True,1.).lane,3*gentle.lane)
        gentle.steer=0.
        released=gentle.lane
        for _ in range(12):gentle.advance(.05,ground)
        self.assertLess(gentle.lane-released,.15)

    def test_taps_start_retarget_and_resume(self):
        run=SkiRun()
        ground=lambda x,z:3000.
        run.tap_slope(.8,.5)
        self.assertEqual(run.mode,'ski')
        run.tap_slope(.8,.5)
        for _ in range(30):run.advance(.05,ground)
        self.assertGreater(run.lane,0.)
        run.tap_slope(.1,.5)
        for _ in range(70):run.advance(.05,ground)
        self.assertLess(run.lane,0.)
        run.action('brake')
        run.tap_slope(.5,.4)
        self.assertEqual(run.mode,'ski')
        self.assertIsNone(run.tap_lane)
        run.steer=1.
        run.advance(.05,ground)
        self.assertIsNone(run.tap_lane)

    def test_one_tap_follows_every_gate_with_assist(self):
        from pnw.summit_ski import COURSES
        for course in COURSES:
            run=SkiRun((course,))
            run.tap_slope(.92,.35)
            for _ in range(10000):
                run.advance(.09,lambda x,z:3500.-x*math.sin(course.heading)-z*math.cos(course.heading))
                if run.mode=='bottom':break
            self.assertEqual((run.mode,run.score),('bottom',len(course.gates)))
