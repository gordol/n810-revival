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

    def test_market_walks_close_without_teleports_or_pivot_snaps(self):
        from market_life import actors
        def walkers(age):
            return [a for a in actors(age,lambda x,z:0,None) if a[0]==0]
        previous=walkers(0)
        for i in range(1,901):
            current=walkers(i*.1)
            for last,now in zip(previous,current):
                self.assertLess(math.hypot(now[1]-last[1],now[3]-last[3]),.22)
                self.assertLess(abs(math.remainder(now[4]-last[4],360)),18)
            previous=current

    def test_seeded_shopper_keeps_identity_and_purchase(self):
        from market_life import BOUQUET,actors,shopper
        def visitor(age):
            identity=shopper('flower table',0)
            return next(row for row in actors(age,lambda x,z:0,None)
                        if row[0]==0 and row[6]&~BOUQUET==identity)
        self.assertEqual(0,visitor(1)[6]&BOUQUET)
        self.assertEqual(visitor(1)[6]|BOUQUET,visitor(2)[6])
        self.assertEqual(visitor(2)[6],visitor(39)[6])
        self.assertNotEqual(shopper('market',1,'Seattle'),shopper('market',1,'Tacoma'))

    def test_plaza_dog_tracks_walker_on_sloping_ground(self):
        from market_life import plaza_walkers
        ground=lambda x,z:.1*x-.04*z
        for age in (0,9,70):
            owner,dog,*others=plaza_walkers(age,ground)
            self.assertEqual((owner[0],dog[0]),(0,7))
            self.assertAlmostEqual(dog[2],ground(dog[1],dog[3]))
            self.assertAlmostEqual(owner[2]-dog[2],dog[6])
            self.assertAlmostEqual(math.hypot(owner[1]-dog[1],owner[3]-dog[3]),math.hypot(.76,.30))
            self.assertEqual(len(others),3)

    def test_workers_rest_independently_and_reach_in_sequence(self):
        from market_life import actors
        def poses(age,since):
            return [a[5] for a in actors(age,lambda x,z:0,since) if a[0]==1]
        idle=poses(5,None)
        self.assertTrue(all(12<=pose<=13 for pose in idle))
        self.assertNotAlmostEqual(idle[0],idle[1])
        self.assertTrue(all(a!=b for a,b in zip(idle,poses(6,None))))
        self.assertAlmostEqual(poses(10,.8)[0],15.)
        self.assertAlmostEqual(poses(11,1.75)[1],17.)

    def test_staff_stand_on_the_rendered_slab_and_street_matches_mesh(self):
        from market_life import actors
        from pike_market import build,floor_height,offset
        from seattle_places import arcade_origin
        center=arcade_origin()
        def terrain(x,z):
            return 30+.11*(x-center[0])+.06*(z-center[1])
        def floor(x,z):return floor_height(center,terrain,x,z)
        people=[row for row in actors(4,floor,None) if row[0] in (0,1)]
        for _,x,y,z,*_ in people:self.assertAlmostEqual(y,floor(x,z))
        tiles=[]
        def capture(points,color,material=0.):
            if material==.237:tiles.append(points)
        build(center,terrain,capture)
        for x,y,z in [tuple(sum(p[k] for p in tile[:3])/3 for k in range(3)) for tile in tiles[::47]]:
            self.assertAlmostEqual(floor(x,z),y)
        for u,v in ((1.7,3.35),(3.4,6.25)):
            self.assertAlmostEqual(floor(*offset(center,u,v)),terrain(*center)+.065,places=3)

    def test_baked_people_have_a_supporting_shoe_in_each_pose(self):
        import struct
        import zlib
        for name in ('sam','maya'):
            path=pocket/'graphics'/'assets'/'people'/f'{name}.zlib'
            data=zlib.decompress(path.read_bytes())
            magic,nv,ni,frames,w,h=struct.unpack_from('<4s5I',data)
            self.assertEqual((magic,frames),(b'NPC3',16))
            offset=24
            for frame in range(frames):
                lx,left,_,rx,right,_=struct.unpack_from('<6f',data,offset+frame*24)
                self.assertAlmostEqual(min(left,right),0)
                self.assertGreaterEqual(max(left,right),0)
                if frame<12:
                    self.assertLess(abs(lx-rx),.245)
                    self.assertLess(max(left,right),.08)
            grip,crown=(5593,10534) if name=='sam' else (5226,10445)
            start=offset+frames*24+ni*4+nv*12
            for frame in range(frames):
                base=start+nv*12*frame
                hand=struct.unpack_from('<h',data,base+grip*12+2)[0]
                head=struct.unpack_from('<h',data,base+crown*12+2)[0]
                self.assertLess(hand+1200,head)
            self.assertEqual(len(data),start+nv*12*frames+w*h*4)

    def test_market_levels_are_walkable_offline(self):
        import market_visit
        for key in market_visit.FLOORS:
            field,_,mesh,count,*_=pnw.build_world(key)
            x,z,*_=market_visit.arrival(key)
            self.assertEqual((x,z),market_visit.walk_inside(key,x,z))
            self.assertEqual(len(mesh),7*count)
            self.assertEqual(field.height(x,z),0.)
            self.assertNotEqual(market_visit.walk_inside(key,0,8),(0,8))
            self.assertEqual(market_visit.walk_inside(key,2,1),(2,1))

    def test_downunder_landings_connect_adjacent_floors(self):
        from market_visit import stairs, stair_exit
        for floor,upper,lower in [('down5','market','down4'),('down4','down5','down3'),('down3','down4',None)]:
            self.assertIsNone(stair_exit(floor,-1,-9))
            self.assertEqual(stair_exit(floor,-1,-12.3),upper)
            self.assertEqual(stair_exit(floor,1,-12.3),lower)
            self.assertGreater(stairs(floor,-1,-12.3),stairs(floor,-1,-8))
            if lower:self.assertLess(stairs(floor,1,-12.3),stairs(floor,1,-8))

    def test_overlook_steps_descend_toward_the_waterfront(self):
        import market_visit
        x,z=market_visit.site('overlook')
        heights=[market_visit.deck_height(lambda *_:18.,x,z+i) for i in range(16,-38,-1)]
        self.assertEqual(sorted(heights,reverse=True),heights)
        self.assertGreater(heights[0]-heights[-1],4.)

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

    def test_bakery_displays_and_approach_are_on_the_street(self):
        import json
        from market_visit import storefront_point
        records=json.loads((pocket/'graphics/assets/seattle/buildings.json').read_text())
        for way in ('367894552','367894553'):
            outline=records[way][2]
            points=[pnw.location('sound',lat/1e7,lon/1e7) for lon,lat in outline]
            for across in (4,-6.6):
                for depth in (-1.95,-5.):
                    x,z=storefront_point(across,depth)
                    crossings=sum((az>z)!=(bz>z) and x<ax+(bx-ax)*(z-az)/(bz-az)
                                  for (ax,az),(bx,bz) in zip(points,points[1:]+points[:1]))
                    self.assertEqual(crossings%2,0,way)

    def test_shoppers_face_their_travel_direction_and_stay_grounded(self):
        from market_life import street_walkers
        from market_visit import site
        ground=lambda x,z:.06*x-.04*z
        for district in ('gum','bakery','overlook'):
            at=site(district)
            for age in range(32):
                before=street_walkers(age,ground,*at)
                after=street_walkers(age+.01,ground,*at)
                self.assertTrue(before)
                for a,b in zip(before,after):
                    self.assertAlmostEqual(a[2],ground(a[1],a[3]))
                    if a[0]==7:continue
                    self.assertEqual(a[6],b[6])
                    dx,dz=b[1]-a[1],b[3]-a[3]
                    heading=math.radians(a[4])
                    self.assertGreater(dx*math.sin(heading)+dz*math.cos(heading),.008)
        self.assertFalse(street_walkers(0,ground,0,0))

    def test_needle_profile_uses_published_heights(self):
        from seattle_places import DECK_HEIGHT,TIP_HEIGHT,space_needle
        levels=set()
        space_needle(lambda x,z:20,lambda pts,color:levels.update(p[1]-20 for p in pts))
        self.assertTrue(any(abs(y-DECK_HEIGHT-1.04)<1e-5 for y in levels))
        self.assertAlmostEqual(max(levels),TIP_HEIGHT)
        self.assertTrue(any(abs(y-DECK_HEIGHT)<1e-5 for y in levels))

    def test_round_trips(self):
        duration=pnw.CROSSING+pnw.DOCK_TIME
        self.assertEqual(pnw.ferry_stop(0),'colman')
        self.assertIsNone(pnw.ferry_stop(duration/2))
        self.assertEqual(pnw.ferry_stop(duration+1),'bainbridge')
        self.assertLess(math.dist(pnw.ride_pose('ferry',duration)[:2],pnw.FERRY[-1]),.001)
        self.assertLess(math.dist(pnw.ride_pose('ferry',2*duration)[:2],pnw.FERRY[0]),.001)
        self.assertAlmostEqual(pnw.ride_pose('wheel',50)[4]-pnw.ride_pose('wheel',0)[4],46)

    def test_runway_departure_and_tacoma_touchdown(self):
        ground=lambda x,z:0.
        limits=(-1e6,1e6,-1e6,1e6)
        plane=SoundVehicle('thun',SimpleNamespace(height=ground))
        self.assertEqual(plane.roll_state,'parked')
        plane.descending=True
        for _ in range(150):plane.advance(.1,ground,limits)
        self.assertIsNone(plane.roll_state)
        self.assertGreater(plane.clearance,25.)
        x,z,plane.heading,_,_=plane.runways[1]
        plane.x,plane.z=x,z
        plane.altitude=12.
        plane.speed=32.;plane.descending=True
        for _ in range(130):plane.advance(.1,ground,limits)
        self.assertEqual(plane.roll_state,'parked')
        self.assertAlmostEqual(plane.speed,0.)
        self.assertIsNotNone(plane.runway_at(plane.x,plane.z))

    def test_boat_stops_at_land(self):
        boat=SoundVehicle('boat',SimpleNamespace(height=lambda x,z:0))
        start=boat.x,boat.z
        boat.advance(.1,lambda x,z:4,(-1e6,1e6,-1e6,1e6))
        self.assertEqual((boat.x,boat.z),start)
        self.assertEqual(boat.speed,0)

    def test_destinations_reachable(self):
        choices={item for group in ExploreMenu.groups.values() for item in group}
        self.assertTrue(set(pnw.OUTINGS)<=choices)
