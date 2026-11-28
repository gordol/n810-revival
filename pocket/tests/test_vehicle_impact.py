import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'graphics'))
from pnw.vehicle_impact import Body, collide


class ImpactTests(unittest.TestCase):
    def test_offset_hit_transfers_momentum_and_spins(self):
        car=Body(.6,0,0,0,25,0,1500,2.2,.95)
        other=Body(0,3.9,0,0,0,0,1500,2.2,.95)
        self.assertGreater(collide(car,other),0)
        self.assertGreater(other.vz,0)
        self.assertGreater(abs(other.spin),.1)
        self.assertGreater(other.damage,0)
        self.assertAlmostEqual(car.vz+other.vz,25)
        z=other.z
        other.coast(.1)
        self.assertGreater(other.z,z)

    def test_heavy_vehicle_absorbs_less_speed(self):
        def hit(mass):
            a=Body(0,0,0,0,19,0,1500,2.2,.95)
            b=Body(0,4,0,0,0,0,mass,2.2,.95)
            collide(a,b)
            return b.vz
        self.assertLess(hit(10000),hit(1500))
