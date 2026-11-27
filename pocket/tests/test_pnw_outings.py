"""Regional scenery registration and outing controls without live providers."""
import math
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs,urlparse

pocket=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(pocket/'graphics'),str(pocket/'shell'),str(pocket/'shell/apps/landscape-lab')]
import pnw_outings as pnw
from rainier_hike import ExploreMenu,SoundVehicle


class OutingTests(unittest.TestCase):
    def test_aerial_registration(self):
        args=parse_qs(urlparse(pnw.aerial_url()).query)
        x0,y0,x1,y1=map(float,args['bbox'][0].split(','))
        self.assertAlmostEqual((x1-x0)/(y1-y0),5/6)
        lat,_,_,_,nx,nz=pnw.GRIDS['sound']
        spacing=pnw.layout('sound')[2]
        for name,lat,lon in pnw.PLACES:
            x,z=pnw.location('sound',lat,lon)
            self.assertLess(abs(x),nx*spacing/2,name)
            self.assertLess(abs(z),nz*spacing/2,name)
            merc_x=lon*20037508.342789245/180
            self.assertAlmostEqual((merc_x-x0)/(x1-x0),.5+x/((nx-1)*spacing),places=7)

    def test_round_trips(self):
        duration=sum(math.dist(a,b) for a,b in zip(pnw.FERRY,pnw.FERRY[1:]))/45
        self.assertLess(math.dist(pnw.ride_pose('ferry',duration)[:2],pnw.FERRY[-1]),.001)
        self.assertLess(math.dist(pnw.ride_pose('ferry',2*duration)[:2],pnw.FERRY[0]),.001)
        self.assertAlmostEqual(pnw.ride_pose('wheel',50)[4]-pnw.ride_pose('wheel',0)[4],46)

    def test_boat_stops_at_land(self):
        boat=SoundVehicle('boat',SimpleNamespace(height=lambda x,z:0))
        start=boat.x,boat.z
        boat.advance(.1,lambda x,z:4,(-1e6,1e6,-1e6,1e6))
        self.assertEqual((boat.x,boat.z),start)
        self.assertEqual(boat.speed,0)

    def test_destinations_reachable(self):
        choices={item for group in ExploreMenu.groups.values() for item in group}
        self.assertTrue(set(pnw.OUTINGS)<=choices)
