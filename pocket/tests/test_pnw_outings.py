"""Regional scenery registration and outing controls without live providers."""
import math
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from urllib.parse import parse_qs,urlparse

pocket=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(pocket/'graphics'),str(pocket/'shell'),str(pocket/'shell/apps/landscape-lab')]
from pnw import outings as pnw
from pnw import terrain as pnw_terrain
from pnw.outings import ExploreMenu,SoundVehicle


class OutingTests(unittest.TestCase):
    def test_termux_workers_run_with_only_their_staged_script(self):
        from io import BytesIO
        import os
        import subprocess
        import tempfile
        from unittest.mock import patch
        from PIL import Image
        from pnw.cockpit import panel
        def encoded(size,fmt):
            buf=BytesIO()
            Image.new('RGB',size,(128,12,0)).save(buf,fmt)
            return buf.getvalue()
        tile=encoded((256,256),'PNG')
        aerial=encoded(pnw_terrain.IMAGE_SIZE,'JPEG')
        real_run=subprocess.run
        def isolated(args,**opts):
            self.assertEqual(args[:3],['proot-distro','login','pocket-maps'])
            return real_run([sys.executable,'-I',*args[args.index('/usr/bin/python3')+1:]],**opts)
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,POCKET_TERMUX='1',XDG_DATA_HOME=tmp),patch(
                'pnw.terrain.urlopen',side_effect=lambda url,timeout:BytesIO(tile if 'terrarium' in url else aerial)),patch(
                'pnw.terrain.subprocess.run',side_effect=isolated) as runner:
            for region in ('sound','hoh'):
                self.assertEqual(set(pnw_terrain.elevations(region)),{12})
            self.assertEqual(len(pnw_terrain.sound_aerial()),1280*1536*3)
            panel.cache_clear()
            try:
                self.assertEqual(len(panel()),1000*244*4)
                panel.cache_clear()
                self.assertEqual(len(panel()),1000*244*4)
                self.assertNotEqual(panel(True),panel())
            finally:panel.cache_clear()
            self.assertEqual(runner.call_count,5)

    def test_streamed_imagery_and_relief_restore_offline(self):
        from io import BytesIO
        import os
        import tempfile
        from unittest.mock import patch
        from PIL import Image
        from geometry import HeightField,Vec
        field=HeightField(2,2,Vec(-8192,0,-8192),16384,16384,(800,)*4,'meters')
        color=BytesIO()
        Image.new('RGB',(1024,1024),(34,87,51)).save(color,'JPEG')
        dem=BytesIO()
        Image.new('F',(129,129),1100.).save(dem,'TIFF')
        def fetch(url,timeout):
            return BytesIO(dem.getvalue() if '3DEPElevation' in url else color.getvalue())
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,XDG_DATA_HOME=tmp,POCKET_TERMUX='0'):
            with patch('pnw.terrain.urlopen',side_effect=fetch) as requests:
                rgb,(fine,vertices)=pnw_terrain.flight_patch((0,0),field)
            self.assertEqual(requests.call_count,2)
            self.assertEqual(fine.values[0],800.)
            self.assertEqual(fine.height(0,0),1100.)
            self.assertEqual(len(vertices)//7,6*128*128)
            with patch('pnw.terrain.urlopen',side_effect=AssertionError('network used')):
                rgb2,(fine2,mesh2)=pnw_terrain.flight_patch((0,0),field)
            self.assertEqual((rgb,fine.values,vertices),(rgb2,fine2.values,mesh2))

            with patch('pnw.terrain.urlopen',side_effect=OSError('offline')):
                fallback,_=pnw_terrain.load_surface((0,0),field,'Aerial',2048)
            self.assertEqual(fallback,rgb)

    def test_jet_instruments_leave_the_canopy_free_of_touch_targets(self):
        from pnw.scene import RainierView
        for kind in ('jet','hangar-jet'):
            view=RainierView.__new__(RainierView)
            view.outing=kind
            jet=view.glider=SoundVehicle(kind,SimpleNamespace(height=lambda x,z:0.))
            for w,h in ((36,58),(96,27)):
                self.assertEqual(jet.controls(w,h),[])
                self.assertTrue(view.footer(w//3,w))
                self.assertIn('fast',[action for action,_,_ in jet.controls(w,h)])
                view.footer(w//3,w)

    def test_aircraft_crosses_prepared_boundary_while_boat_stays_inside(self):
        ground=lambda x,z:0.
        for mode in ('jet','boat'):
            vehicle=SoundVehicle(mode,SimpleNamespace(height=ground))
            vehicle.x=vehicle.z=vehicle.heading=0.
            vehicle.advance(.5,ground,(-1.,1.,-1.,1.))
            if mode=='boat':self.assertEqual(vehicle.z,1.)
            else:self.assertGreater(vehicle.z,1.)

    def test_neighborhood_prioritizes_center_and_reuses_tiles_after_crossing(self):
        from unittest.mock import patch
        imagery=pnw_terrain.FlightImagery()
        self.addCleanup(imagery.close)
        width=pnw_terrain.PATCH_WIDTH
        def settle(x,source):
            imagery.update(x,0,None,source)
            for i in range(60):
                if not imagery.jobs:return
                self.assertLessEqual(len(imagery.jobs),2)
                for job in imagery.jobs.values():job.result()
                imagery.update(x,0,None,source)
            self.fail('Tile queue did not finish')
        with patch('pnw.terrain.load_surface',return_value=(b'image',None)) as load:
            imagery.update(0,0,None)
            self.assertEqual(next(iter(imagery.jobs)),((0,0),'Aerial',2048))
            settle(0,'Aerial')
            sizes=[size for key,source,size in imagery.resident.values()]
            self.assertEqual([sizes.count(n) for n in (2048,1024,512)],[1,8,16])
            settle(width,'Drawn terrain')
            load.reset_mock()
            settle(2*width,'Drawn terrain')
            self.assertEqual(load.call_count,5)
            self.assertEqual(len(imagery.resident),25)

    def test_horizon_keeps_landmarks_and_releases_tiles_under_memory_pressure(self):
        from unittest.mock import patch
        horizon=pnw_terrain.FlightHorizon()
        self.addCleanup(horizon.close)
        def settle(x,setting='Auto'):
            removed=[]
            for i in range(100):
                drops,_=horizon.update(x,0,None,setting)
                removed.extend(drops)
                if not horizon.job:return removed
                horizon.job.result()
            self.fail('Horizon did not settle')
        with patch('pnw.terrain.flight_patch',return_value=(b'image',None)), patch(
                'pnw.terrain.available_memory',return_value=4*1024**3) as memory:
            settle(0)
            self.assertEqual(len(horizon.resident),52)
            pins={i:horizon.resident[i] for i in (25,26,27)}
            settle(3*pnw_terrain.HORIZON_WIDTH)
            self.assertEqual({i:horizon.resident[i] for i in pins},pins)
            memory.return_value=None
            horizon.next_sample=0
            settle(0)
            self.assertEqual(len(horizon.resident),52)
            settle(0,'120 km')
            self.assertEqual(len(horizon.resident),84)
            memory.return_value=800*1024**2
            horizon.next_sample=0
            self.assertEqual(len(settle(0)),72)
            self.assertEqual(len(horizon.resident),12)
            memory.return_value=128*1024**2
            horizon.next_sample=0
            self.assertEqual(len(settle(0)),12)
            self.assertFalse(horizon.resident)
        args=lambda w:parse_qs(urlparse(pnw_terrain.aerial_url((8,-8),width=w)).query)
        def extent(w):
            a,b,c,d=map(float,args(w)['bbox'][0].split(','))
            return (a+c)/2,(b+d)/2,c-a
        near=extent(pnw_terrain.PATCH_WIDTH)
        far=extent(pnw_terrain.HORIZON_WIDTH)
        for i in (0,1):self.assertAlmostEqual(near[i],far[i])
        self.assertAlmostEqual(far[2],4*near[2])

    def test_exterior_tile_renders_real_lowland_elevation(self):
        from geometry import HeightField,Vec
        field=HeightField(2,2,Vec(-4096,0,-4096),8192,8192,(200,)*4,'meters')
        dem=[65]*(129*129)
        patch,mesh=pnw_terrain.relief_mesh((4,0),field,dem)
        self.assertEqual(set(patch.values),{65.})
        self.assertEqual(set(mesh[1::7]),{65.})
        with self.assertRaises(ValueError):pnw_terrain.relief_mesh((4,0),field)

    def test_drawn_surface_uses_map_vectors_and_preserves_islands_offline(self):
        from unittest.mock import patch
        from geometry import HeightField,Vec
        from struct import Struct
        field=HeightField(2,2,Vec(-8192,0,-8192),16384,16384,(125,)*4,'meters')
        def coords(*points):
            return [pnw_terrain.patch_corner(x,z) for x,z in points]
        water={'rings':[coords((-2500,-2500),(2500,-2500),(2500,2500),(-2500,2500)),
                        coords((-400,-400),(400,-400),(400,400),(-400,400))]}
        road={'kind':'primary','points':coords((-3000,1024),(3000,1024))}
        with patch('pnw.terrain.urlopen',side_effect=AssertionError('downloaded while drawing terrain')), \
                patch('map_hydrography.polygons_in',return_value=(water,)), \
                patch('map_geography.selected_geography',return_value=((),(road,),())):
            rgb,_=pnw_terrain.load_surface((0,0),field,'Drawn terrain')
        def color(x,y):return Struct('3B').unpack_from(rgb,3*(1024*y+x))
        self.assertEqual(color(512,700),(47,92,107))
        self.assertEqual(color(512,512),color(512,1000))
        self.assertEqual(color(512,640),(134,129,113))
        self.assertEqual(color(512,384),(47,92,107))

    def test_aerial_registration(self):
        args=parse_qs(urlparse(pnw_terrain.aerial_url()).query)
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
        from pnw import pike_market
        from pnw.seattle_places import arcade_origin
        center=arcade_origin()
        x,z,yaw,pitch=pike_market.arrival(center)
        self.assertGreater(x,center[0])
        self.assertGreater(z,center[1])
        self.assertAlmostEqual(x+38*math.sin(yaw),center[0])
        self.assertAlmostEqual(z+38*math.cos(yaw),center[1])
        self.assertLess(pitch,0)

    def test_counter_shoppers_can_browse_and_player_orders_queue(self):
        from pnw.market_life import FishCounter,actors
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
        from pnw.market_life import actors
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
        from pnw.market_life import BOUQUET,actors,shopper
        def visitor(age):
            identity=shopper('flower table',0)
            return next(row for row in actors(age,lambda x,z:0,None)
                        if row[0]==0 and row[6]&~BOUQUET==identity)
        self.assertEqual(0,visitor(1)[6]&BOUQUET)
        self.assertEqual(visitor(1)[6]|BOUQUET,visitor(2)[6])
        self.assertEqual(visitor(2)[6],visitor(39)[6])
        self.assertNotEqual(shopper('market',1,'Seattle'),shopper('market',1,'Tacoma'))

    def test_plaza_dog_tracks_walker_on_sloping_ground(self):
        from pnw.market_life import plaza_walkers
        ground=lambda x,z:.1*x-.04*z
        for age in (0,9,70):
            owner,dog,*others=plaza_walkers(age,ground)
            self.assertEqual((owner[0],dog[0]),(0,7))
            self.assertAlmostEqual(dog[2],ground(dog[1],dog[3]))
            self.assertAlmostEqual(owner[2]-dog[2],dog[6])
            self.assertAlmostEqual(math.hypot(owner[1]-dog[1],owner[3]-dog[3]),math.hypot(.76,.30))
            self.assertEqual(len(others),3)

    def test_workers_rest_independently_and_reach_in_sequence(self):
        from pnw.market_life import actors
        def poses(age,since):
            return [a[5] for a in actors(age,lambda x,z:0,since) if a[0]==1]
        idle=poses(5,None)
        self.assertTrue(all(12<=pose<=13 for pose in idle))
        self.assertNotAlmostEqual(idle[0],idle[1])
        self.assertTrue(all(a!=b for a,b in zip(idle,poses(6,None))))
        self.assertAlmostEqual(poses(10,.8)[0],15.)
        self.assertAlmostEqual(poses(11,1.75)[1],17.)

    def test_staff_stand_on_the_rendered_slab_and_street_matches_mesh(self):
        from pnw.market_life import actors
        from pnw.pike_market import build,floor_height,offset
        from pnw.seattle_places import arcade_origin
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
        from pnw import market_visit
        for key in market_visit.FLOORS:
            field,_,mesh,count,*_=pnw.build_world(key)
            x,z,*_=market_visit.arrival(key)
            self.assertEqual((x,z),market_visit.walk_inside(key,x,z))
            self.assertEqual(len(mesh),7*count)
            self.assertEqual(field.height(x,z),0.)
            self.assertNotEqual(market_visit.walk_inside(key,0,8),(0,8))
            self.assertEqual(market_visit.walk_inside(key,2,1),(2,1))

    def test_downunder_landings_connect_adjacent_floors(self):
        from pnw.market_visit import stairs, stair_exit
        for floor,upper,lower in [('down5','market','down4'),('down4','down5','down3'),('down3','down4',None)]:
            self.assertIsNone(stair_exit(floor,-1,-9))
            self.assertEqual(stair_exit(floor,-1,-12.3),upper)
            self.assertEqual(stair_exit(floor,1,-12.3),lower)
            self.assertGreater(stairs(floor,-1,-12.3),stairs(floor,-1,-8))
            if lower:self.assertLess(stairs(floor,1,-12.3),stairs(floor,1,-8))

    def test_overlook_steps_descend_toward_the_waterfront(self):
        from pnw import market_visit
        x,z=market_visit.site('overlook')
        heights=[market_visit.deck_height(lambda *_:18.,x,z+i) for i in range(16,-38,-1)]
        self.assertEqual(sorted(heights,reverse=True),heights)
        self.assertGreater(heights[0]-heights[-1],4.)

    def test_delivery_yields_on_its_mapped_route(self):
        from pnw.market_life import Delivery
        from pnw.seattle_places import delivery_route
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
        from pnw.market_visit import storefront_point
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
        from pnw.market_life import street_walkers
        from pnw.market_visit import site
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
        from pnw.seattle_places import DECK_HEIGHT,TIP_HEIGHT,space_needle
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

    def test_research_jet_cruise_full_power_and_landing(self):
        ground=lambda x,z:0.
        limits=(-1e7,1e7,-1e7,1e7)
        field=SimpleNamespace(height=ground)
        jet=SoundVehicle('jet',field)
        trainer=SoundVehicle('plane',field)
        self.assertGreater(jet.speed,3*trainer.speed)
        jet.toggle_speed()
        trainer.toggle_speed()
        for _ in range(350):
            jet.advance(.1,ground,limits)
            trainer.advance(.1,ground,limits)
        self.assertAlmostEqual(jet.speed,420.,delta=.1)
        self.assertAlmostEqual(trainer.speed,150.,delta=.1)
        jet.x,jet.z,jet.heading,_,_=jet.runways[1]
        jet.altitude=5.
        jet.speed=65.
        jet.descending=True
        for _ in range(140):jet.advance(.1,ground,limits)
        self.assertEqual(jet.roll_state,'parked')

    def test_hangar_jet_gear_and_air_sports(self):
        from pnw.outings import AirSport
        ground=lambda x,z:0.
        field=SimpleNamespace(height=ground)
        limits=(-1e6,1e6,-1e6,1e6)
        plane=SoundVehicle('hangar-jet',field)
        plane.toggle_gear()
        self.assertTrue(plane.gear_down)
        plane.descending=True
        for _ in range(230):plane.advance(.1,ground,limits)
        self.assertIsNone(plane.roll_state)
        plane.toggle_gear()
        self.assertFalse(plane.gear_down)
        plane.descending=True
        plane.advance(.1,ground,limits)
        self.assertTrue(plane.gear_down)
        dive=AirSport('skydive',field)
        for _ in range(60):dive.advance(.1,ground,limits)
        self.assertLess(dive.vertical,-40.)
        dive.action()
        for _ in range(60):dive.advance(.1,ground,limits)
        self.assertGreater(dive.vertical,-5.)
        balloon=AirSport('balloon',field)
        balloon.action()
        for _ in range(60):balloon.advance(.1,ground,limits)
        self.assertGreater(balloon.clearance,120.)

    def test_plane_manual_approach_and_controller_release(self):
        ground=lambda x,z:0.
        plane=SoundVehicle('plane',SimpleNamespace(height=ground))
        plane.throttle_rate=-1.;plane.rudder=.4
        for _ in range(40):plane.advance(.1,ground,(-1e6,1e6,-1e6,1e6))
        self.assertEqual(plane.throttle,0.)
        plane.cancel_input()
        self.assertEqual((plane.throttle_rate,plane.rudder),(0.,0.))
        plane.x,plane.z,plane.heading,_,_=plane.runways[1]
        plane.altitude=3.;plane.speed=33.;plane.pitch_stick=.16
        for _ in range(130):plane.advance(.1,ground,(-1e6,1e6,-1e6,1e6))
        self.assertEqual(plane.roll_state,'parked')

    def test_jet_elevator_follows_the_canopy(self):
        ground=lambda x,z:0.
        limits=(-1e7,1e7,-1e7,1e7)
        for bank in (0,90,-90,180):
            with self.subTest(bank=bank):
                jet=SoundVehicle('jet',SimpleNamespace(height=ground))
                jet.roll_angle=math.radians(bank)
                jet.pitch_stick=-1.
                initial_heading,initial_alt=jet.heading,jet.altitude
                for _ in range(30):pose=jet.advance(1/60,ground,limits)
                self.assertAlmostEqual(pose[3],-jet.elevation)
                if abs(bank)==90:
                    self.assertAlmostEqual(jet.elevation,0.)
                    self.assertGreater((jet.heading-initial_heading)*math.copysign(1,bank),.1)
                else:
                    self.assertGreater((jet.altitude-initial_alt)*(1 if bank==0 else -1),5.)

    def test_airborne_jet_completes_inside_and_outside_loops(self):
        ground=lambda x,z:0.
        limits=(-1e7,1e7,-1e7,1e7)
        for direction in (-1,1):
            for hz in (30,60):
                with self.subTest(direction=direction,hz=hz):
                    jet=SoundVehicle('jet',SimpleNamespace(height=ground))
                    jet.altitude=4000.
                    jet.pitch_stick=direction
                    heading=jet.heading
                    # Project the nose onto the initial vertical flight plane.
                    # Unwrap its angle so crossing either pole counts continuously.
                    previous=angle=0.
                    for _ in range(10*hz):
                        _,_,yaw,pitch=jet.advance(1/hz,ground,limits)
                        current=math.atan2(-math.sin(pitch),math.cos(pitch)*math.cos(yaw-heading))
                        delta=math.remainder(current-previous,math.tau)
                        self.assertLess(abs(delta),.04)
                        previous=current
                        angle+=delta
                        if abs(angle)>=math.tau:break
                    self.assertGreaterEqual(-direction*angle,math.tau)
                    self.assertLess(abs(jet.elevation),.04)
                    self.assertGreater(math.cos(jet.roll_angle),.99)
                    self.assertGreater(math.cos(jet.heading-heading),.99)

    def test_aircraft_glance_roll_stall_and_recovery(self):
        ground=lambda x,z:0.
        limits=(-1e6,1e6,-1e6,1e6)
        plane=SoundVehicle('plane',SimpleNamespace(height=ground))
        plane.look=(1.,0.)
        heading=plane.heading
        for _ in range(20):pose=plane.advance(.05,ground,limits)
        self.assertGreater(pose[2]-heading,1.3)
        self.assertEqual(plane.heading,heading)
        plane.cancel_input()
        plane.stick=1.
        angles=[]
        for _ in range(90):
            plane.advance(.05,ground,limits)
            angles.append(plane.roll_angle)
        self.assertGreater(max(angles),3.)
        self.assertLess(min(angles),-3.)
        self.assertAlmostEqual(plane.look_yaw,0.,places=3)
        plane.stick=plane.roll_rate=plane.roll_angle=0.
        plane.throttle=0.
        plane.pitch_stick=-1.
        for _ in range(100):plane.advance(.05,ground,limits)
        self.assertTrue(plane.stalled)
        altitude=plane.altitude
        plane.advance(.1,ground,limits)
        self.assertLess(plane.altitude,altitude)
        plane.throttle=1.
        plane.pitch_stick=.3
        for _ in range(30):plane.advance(.05,ground,limits)
        self.assertFalse(plane.stalled)

    def test_dpad_distinguishes_pause_wheel_and_live_flight(self):
        from pnw.scene import RainierView
        from unittest.mock import Mock
        view=RainierView(SimpleNamespace())
        view.outing='plane'
        view.world=(object(),)
        plane=view.glider=SoundVehicle('plane',SimpleNamespace(height=lambda x,z:0.))
        view.pause_owner=SimpleNamespace(clock=Mock(side_effect=[10.,13.,13.]),paused_total=0.,cancel_keys=Mock())
        view.controller_button(6)
        view.controller_button(12)
        self.assertEqual(view.notebook.rows()[view.notebook.selected],'Controller')
        self.assertEqual(plane.flaps,0)
        view.controller_button(6)
        self.assertEqual(view.pause_owner.paused_total,3.)
        view.controller_button(4)
        self.assertTrue(plane.menu)
        view.controller_button(12)
        self.assertFalse(plane.menu)
        self.assertEqual(plane.flaps,0)
        view.controller_button(12)
        self.assertEqual(plane.flaps,1)

    def test_controller_selects_explore_destination(self):
        from unittest.mock import Mock
        from pnw.scene import RainierView
        view=RainierView(SimpleNamespace())
        menu=view.notebook=ExploreMenu(view)
        view.start_outing=Mock()
        view.controller_button(12)
        self.assertIn('> Fly',menu.menu_lines(40))
        view.controller_button(0)
        self.assertEqual(menu.group,'Fly')
        view.controller_button(12)
        self.assertIn('> Thun Field hangar',menu.menu_lines(40))
        view.controller_button(14)
        view.start_outing.assert_called_once_with('hangar')

    def test_boat_stops_at_land(self):
        boat=SoundVehicle('boat',SimpleNamespace(height=lambda x,z:0))
        start=boat.x,boat.z
        boat.advance(.1,lambda x,z:4,(-1e6,1e6,-1e6,1e6))
        self.assertEqual((boat.x,boat.z),start)
        self.assertEqual(boat.speed,0)

    def test_destinations_reachable(self):
        choices={item for group in ExploreMenu.groups.values() for item in group}
        self.assertTrue(set(pnw.OUTINGS)<=choices)
