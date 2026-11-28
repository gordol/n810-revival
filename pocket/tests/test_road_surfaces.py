"""Regression cases for stacked roads, yielding and the civilian fleet."""
from pathlib import Path
import math
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

pocket=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(pocket/'graphics'),str(pocket/'shell')]
from pnw.seattle_places import BridgeRoads
from pnw.traffic import Traffic,vehicle_type
from pnw.vehicle_impact import Body,StreetObstacles,walk_past_obstacles


class RoadSurfaceTests(unittest.TestCase):
    def test_low_midspan_does_not_capture_walker_below_it(self):
        spans=[(1,'motorway',4.,(0,0),(0,10),10.,0.,.07),
               (1,'motorway',4.,(0,10),(0,30),20.,.7,0.),
               (1,'motorway',4.,(0,30),(0,40),10.,.7,-.07)]
        with patch('pnw.seattle_places.bridge_spans',return_value=spans):
            roads=BridgeRoads(lambda x,z:0.)
        for x in range(-8,9):
            self.assertEqual(roads.sample(x,20,0.,True),0.)
        for z in range(21):y=roads.sample(0,z,0.,True)
        self.assertAlmostEqual(y,.7)

    def test_ground_median_opens_only_on_ground_ramp(self):
        from pnw.seattle_places import ground_ramp_cells,inside_ground_ramp
        points=[(0,0),(16,0),(32,0)]
        index=ground_ramp_cells([('Ramp','motorway_link',points,3.,())],{frozenset(points[1:])})
        self.assertTrue(inside_ground_ramp(8,2,index))
        self.assertFalse(inside_ground_ramp(8,4,index))
        self.assertFalse(inside_ground_ramp(24,0,index))

    def test_first_hill_portland_ramp_uses_a_single_centered_lane(self):
        from pnw.terrain import location
        from pnw.traffic import routes,point
        x,z=location('sound',47.6058,-122.3292)
        route=routes()[0]
        candidates=[]
        for (a,b,dx,dz,start,lanes,deck),end in zip(route[0],route[1]):
            d=(x-a)*dx+(z-b)*dz
            if not 0<=d<=end-start:continue
            px,pz,_=point(route,start+d,0.)
            candidates.append((math.hypot(px-x,pz-z),start+d,lanes,deck))
        gap,at,lanes,deck=min(candidates)
        self.assertLess(gap,8)
        self.assertEqual(deck,-1)  # approach below the elevated lanes
        self.assertEqual(lanes,1)
        self.assertEqual(point(route,at,-1.8),point(route,at,1.8))

    def test_wall_blocks_inward_motion_and_allows_sliding_parallel(self):
        walls=StreetObstacles([],0)
        walls.cells[(0,0)]={(10.,0.,0.,20.,0.,1.)}
        x,z=walk_past_obstacles((9.,2.),(12.,5.),lambda x,z:0.,[walls])
        self.assertLess(x,9.8)
        self.assertAlmostEqual(z,5.)

    def test_target_stop_ignores_car_above_and_opposing_traffic(self):
        traffic=Traffic()
        def car(z,angle,height):return Body(0.,z,angle,0.,0.,0.,1500.,2.2,.95,elevation=height)
        traffic.bodies={1:car(5,0,5),2:car(8,math.pi,0),3:car(20,0,0)}
        self.assertEqual(traffic.car_ahead(SimpleNamespace(x=0,z=0,heading=0),0),3)

    def test_coupes_are_uncommon_and_patrol_vehicles_are_in_traffic(self):
        fleet=[vehicle_type(i) for i in range(1541)]
        self.assertLess(fleet.count(10)/len(fleet),.05)
        self.assertGreater((fleet.count(14)+fleet.count(15))/len(fleet),.65)
        self.assertIn(9,fleet)
