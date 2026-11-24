"""A child can complete the offline trail using one tap per stop."""
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'graphics'),str(root/'shell')]
from river_walk import BUSHES, FOX, BerryTrail, site, wet


class RiverTrailTests(unittest.TestCase):
    def test_four_guided_stops_and_no_double_pick(self):
        owner=SimpleNamespace(x=0.,z=0.,yaw=math.pi)
        trail=BerryTrail()
        trail.visit(*FOX)
        self.assertFalse(trail.fed)
        for leg in range(4):
            trail.guiding=True
            for _ in range(600):
                trail.advance(owner,.05)
                if not trail.guiding:break
            self.assertFalse(trail.guiding)
            trail.visit(owner.x,owner.z)
            self.assertEqual(len(trail.picked),min(leg+1,3))
            self.assertEqual(trail.fed,leg==3)
        self.assertGreater(owner.pitch,0.)

    def test_mapped_site_and_dry_game_route(self):
        field,segments=site()
        self.assertEqual(field.nx,257)
        self.assertTrue(550<field.height(0,0)<570)
        self.assertTrue(wet(15,8,segments))
        for x,z in ((0,0),*BUSHES,FOX):
            self.assertFalse(wet(x,z,segments))
