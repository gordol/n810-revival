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

    def test_market_street_arrival_faces_the_arcade(self):
        import pike_market
        from seattle_places import arcade_origin
        center=arcade_origin()
        x,z,yaw,pitch=pike_market.arrival(center)
        self.assertGreater(x,center[0])
        self.assertGreater(z,center[1])
        self.assertAlmostEqual(x+38*math.sin(yaw),center[0])
        self.assertAlmostEqual(z+38*math.cos(yaw),center[1])
        self.assertLess(pitch,0)

    def test_counter_shoppers_can_browse_and_player_orders_queue(self):
        from market_life import FishCounter,actors
        counter=FishCounter()
        self.assertIsNone(counter.advance(5))
        self.assertEqual(counter.advance(12),0)
        counter.order(12.1)
        counter.order(12.2)
        self.assertEqual(counter.waiting,1)
        self.assertEqual(counter.advance(17),0)
        self.assertIsNone(counter.advance(44))
        self.assertNotIn(2,[a[0] for a in actors(44,lambda x,z:0,None)])
        arc=actors(14,lambda x,z:0,1.275)
        self.assertGreater(next(a[2] for a in arc if a[0]==2),2.)

    def test_delivery_yields_on_its_mapped_route(self):
        from market_life import Delivery
        from seattle_places import delivery_route
        delivery=Delivery()
        start=delivery_route()[0]
        for i in range(10):
            van=delivery.advance(i*.1,start,[],lambda x,z:5)
        self.assertEqual((van[1],van[3]),start)
        for i in range(10,20):
            delivery.advance(i*.1,(0,0),[],lambda x,z:5)
        self.assertGreater(delivery.distance,0)

    def test_needle_profile_uses_published_heights(self):
        from seattle_places import DECK_HEIGHT,TIP_HEIGHT,space_needle
        levels=set()
        space_needle(lambda x,z:20,lambda pts,color:levels.update(p[1]-20 for p in pts))
        self.assertAlmostEqual(max(levels),TIP_HEIGHT)
        self.assertTrue(any(abs(y-DECK_HEIGHT)<1e-5 for y in levels))

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
