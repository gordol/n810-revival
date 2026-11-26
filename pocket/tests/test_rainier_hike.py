"""Regional hiking uses every elevation sample and metre-based map bounds."""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

pocket=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(pocket/'graphics'),str(pocket/'shell'),str(pocket/'shell/apps/surface-renderer'),str(pocket/'shell/apps/landscape-lab')]
from rainier_hike import HikeMenu,ReliefMap,bounds,region_field,summit_start
from river_explore import ground_target,walk_to


class HikeTests(TestCase):
    def field(self):
        meta=dict(nx=6,nz=5,latitude_first=46.,latitude_step=.06,longitude_step=.08)
        values=list(range(30))
        with patch('rainier_data.download'),patch('terrain_elevation.grid',return_value=(meta,values)):
            return region_field()

    def test_ice_grips_deliver_the_climber_to_the_peak_before_flag_raise(self):
        from geometry import HeightField,Vec
        from rainier_hike import SummitClimb
        heights=tuple(4000-abs(i-10)-abs(j-10) for j in range(21) for i in range(21))
        field=HeightField(21,21,Vec(-100,0,-100),10,10,heights)
        climb=SummitClimb(field)
        x,z,*_=climb.advance(0,field.height)
        self.assertLess(field.height(x,z),4000)
        for grip in range(1,11):
            climb.reach()
            climb.reach()
            self.assertEqual(climb.grips,grip)
            x,z,*_=climb.advance(1,field.height)
        self.assertEqual((x,z),(0,0))
        self.assertTrue(climb.arrived)
        self.assertFalse(climb.raised)
        self.assertEqual(climb.controls(40,30)[-1][1],'Raise flag')
        climb.reach()
        self.assertTrue(climb.raised)
        self.assertIn('launch',[action for action,*_ in climb.controls(40,30)])

    def test_summit_views_follow_geographic_bearings_and_wrap(self):
        from geometry import HeightField,Vec
        from rainier_hike import SummitClimb
        import math
        field=HeightField(3,3,Vec(-100,0,-100),100,100,(0,0,0,0,100,0,0,0,0))
        climb=SummitClimb(field,panorama=True)
        climb.grips=climb.pitches
        climb.advance(20,field.height)
        self.assertNotIn('vista',[a for a,*_ in climb.controls(40,30)])
        climb.reach()
        self.assertTrue(climb.dancing)
        climb.advance(climb.dance_seconds,field.height)
        self.assertFalse(climb.dancing)
        self.assertIn('encore',[a for a,*_ in climb.controls(40,30)])
        headings=[]
        for _ in climb.vistas:
            headings.append(math.degrees(climb.advance(.1,field.height)[2])%360)
            climb.next_vista()
        self.assertEqual(climb.vista,0)
        self.assertTrue(300<headings[0]<330)
        self.assertTrue(150<headings[-1]<180)
        self.assertIn('vista',[a for a,*_ in climb.controls(40,30)])

    def test_summit_dancers_alternate_hops_and_stop_at_the_panorama(self):
        from geometry import HeightField,Vec
        from rainier_hike import SummitClimb
        from rainier_pixels import summit_dancers
        field=HeightField(3,3,Vec(-100,0,-100),100,100,(0,0,0,0,1,0,0,0,0))
        climb=SummitClimb(field)
        spans=((0,10,16,0,12),(160,8,3,12,9))
        climb.wave=.25
        climb.raised=False
        self.assertFalse(summit_dancers(climb,field,field.origin,spans))
        climb.raised=True
        fox,marmot=summit_dancers(climb,field,field.origin,spans)
        self.assertGreater(fox.y,marmot.y)
        climb.wave+=.5/.92
        fox,marmot=summit_dancers(climb,field,field.origin,spans)
        self.assertGreater(marmot.y,fox.y)
        self.assertGreaterEqual(marmot.first,160)
        climb.wave=climb.dance_seconds
        self.assertFalse(summit_dancers(climb,field,field.origin,spans))

    def test_horizon_joins_the_walking_grid_and_curves_below_sea_level(self):
        from array import array
        from geometry import HeightField,Vec
        import summit_horizon as h
        field=HeightField(257,257,Vec(-12800,0,-12800),100,100,(300,)*(257**2))
        vertices=array('f')
        h.append_mesh(vertices,field,100,[-40]*(h.SIZE**2))
        self.assertEqual(len(vertices)%21,0)
        edge=set()
        far_y=[]
        for index in range(0,len(vertices),7):
            x,y,z=vertices[index:index+3]
            self.assertGreaterEqual(max(abs(x),abs(z)),12800)
            if z==-12800 and abs(x)<=12800:edge.add((x,y))
            if x==-102400 and z==0:far_y.append(y)
        self.assertEqual(edge,{(x,200) for x in range(-12800,12801,100)})
        self.assertAlmostEqual(far_y[0],-100-102400**2/(2*6371000),places=3)

    def test_hang_glide_steering_dead_straight_then_landing(self):
        from rainier_hike import HangGlider
        import math
        climb=SimpleNamespace(x=0,z=0,heading=math.pi)
        height=lambda x,z:100-.4*z
        flight=HangGlider(climb,height)
        limits=(-500,500,-500,500)
        for _ in range(20):flight.advance(.1,height,limits)
        self.assertAlmostEqual(flight.x,0)
        self.assertGreater(flight.clearance,10)
        flight.steer(1)
        for _ in range(20):flight.advance(.1,height,limits)
        self.assertGreater(flight.x,5)
        self.assertLessEqual(flight.heading%math.tau,math.radians(18))
        flight.descending=True
        for _ in range(200):
            flight.advance(.1,height,limits)
            if flight.landed:break
        self.assertTrue(flight.landed)
        self.assertEqual(flight.clearance,0)

    def test_paramotor_climbs_coasts_and_lands_in_either_view(self):
        from rainier_hike import HangGlider
        floor=lambda x,z:4200.
        limits=(-1000,1000,-1000,1000)
        flight=HangGlider(SimpleNamespace(x=0,z=0,heading=0),floor,powered=True)
        self.assertTrue(flight.chase)
        flight.advance(1,floor,limits)
        self.assertEqual(flight.clearance,10.)
        flight.toggle_motor()
        flight.chase=False
        flight.advance(1,floor,limits)
        self.assertAlmostEqual(flight.clearance,7.7)
        flight.descending=True
        flight.advance(1,floor,limits)
        self.assertTrue(flight.landed)

    def test_controller_launches_from_flag_and_hike_offers_direct_flight(self):
        from rainier_pixels import RainierView
        view=RainierView(None)
        view.regional=True
        view.world=(SimpleNamespace(inset=True),)
        menu=HikeMenu(view)
        with patch.object(view,'start_glide') as launch:
            self.assertFalse(menu.tap_xy(0,menu.lines(40).index('Hang glide')))
            view.climb=SimpleNamespace(raised=True)
            view.controller_button(0)
            self.assertEqual(launch.call_count,2)

    def test_pad_shutter_and_pool_actions_follow_equipped_tool(self):
        from rainier_pixels import RainierView
        from river_channel import TROUT_POOL
        host=SimpleNamespace(window=lambda name:SimpleNamespace(w=42,h=32))
        view=RainierView(host)
        view.world=(True,)
        view.camera=(*TROUT_POOL,0,0)
        view.frame_camera=(view.camera,1.)
        view.controller_button(3)
        view.controller_button(10)
        self.assertTrue(view.binoculars)
        self.assertEqual(view.zoom,8)
        view.controller_button(2)
        view.focus_key='marmot'
        view.controller_button(0)
        self.assertEqual(view.shutter,'marmot')
        self.assertEqual(view.fishing.state,'idle')
        view.controller_button(1)
        self.assertTrue(view.lens)
        view.notebook.entries=['fox','marmot']
        view.controller_button(14)
        self.assertEqual(view.notebook.page,1)
        view.controller_button(13)
        self.assertEqual(view.notebook.page,0)
        view.controller_button(1)
        self.assertIsNone(view.notebook)
        view.controller_button(2)
        self.assertFalse(view.lens or view.binoculars)
        view.controller_button(0)
        self.assertEqual(view.fishing.state,'drift')
        view.fishing.state='bite'
        with patch('rainier_pixels.vibration'):
            view.controller_button(0)
        self.assertEqual(view.fishing.state,'fight')
        view.controller_button(0)
        self.assertTrue(view.fishing.reeling)
        view.controller_button(0)
        self.assertFalse(view.fishing.reeling)
        view.fishing.state='landed'
        view.fishing.target='trout'
        view.controller_button(1)
        self.assertFalse(view.fishing.kept_brook)
        view.controller_button(1)
        view.controller_button(0)
        self.assertEqual(view.fishing.state,'idle')
        view.fishing.state='landed'
        view.fishing.target='brook_trout#1'
        view.controller_button(1)
        self.assertTrue(view.fishing.kept_brook)
        view.camera=(100,100,0,0)
        view.controller_button(0)
        self.assertEqual(view.fishing.state,'idle')

    def test_camp_menu_controls_match_drawn_rows(self):
        for height in (14,38):
            visits=[]
            view=SimpleNamespace(name='Walk',time_mode=0,party=None,regional=False,travel_job=None,season=0,weather=0,
                tent=False,story=False,host=SimpleNamespace(window=lambda _:SimpleNamespace(h=height)),
                move_to_view=lambda camp=False:visits.append(camp))
            menu=HikeMenu(view)
            menu.tap_xy(0,8)
            def choose(prefix):
                return menu.tap_xy(0,next(i for i,row in enumerate(menu.lines(40)) if row.startswith(prefix)))
            choose('Season');choose('Weather');choose('Light')
            self.assertEqual(view.time_mode,1)
            self.assertEqual((view.season,view.weather),(1,1))
            self.assertFalse(choose('Visit river'));self.assertEqual(visits,[False])
            self.assertFalse(choose('Bigfoot'));self.assertTrue(view.story and view.tent)
            self.assertEqual(visits,[False,True])
            choose('Pack tent');self.assertFalse(view.story or view.tent)

    def test_debug_overlay_toggle_returns_to_walk(self):
        view=SimpleNamespace(regional=True,party=None,travel_job=None,pace_name='Walk',travel_error='',debug_overlay=False)
        menu=HikeMenu(view)
        for expected in (True,False):
            row=next(i for i,line in enumerate(menu.lines(36)) if line.startswith('Debug overlay'))
            self.assertFalse(menu.tap_xy(0,row))
            self.assertEqual(view.debug_overlay,expected)

    def test_lookout_position_and_deck_match_the_mesh(self):
        import fremont_lookout as lookout
        from rainier_pixels import RainierView,surface
        from geometry import Vec
        field=self.field()
        meta=dict(latitude_first=lookout.LATITUDE-.12,longitude_first=lookout.LONGITUDE-.24,
                  latitude_step=.06,longitude_step=.08)
        with patch('terrain_elevation.grid',return_value=(meta,field.values)):
            x,z=lookout.location(field)
        self.assertAlmostEqual(x,field.origin.x+3*field.dx)
        self.assertAlmostEqual(z,field.origin.z+2*field.dz)
        height=lambda i,j:surface(field,i,j)
        level=lookout.base_level(height,x,z)
        faces=[]
        lookout.build(height,lambda a,b,c,color:faces.append((a,b,c)),x,z)
        self.assertTrue(any(all(p.y==level+lookout.DECK for p in triangle) for triangle in faces))
        view=RainierView.__new__(RainierView)
        view.world=(field,Vec(0,0,0))
        view.regional=True
        view.lookout_site=(x,z,level)
        RainierView.visit_lookout(view,deck=True)
        px,pz=view.trip_pose[:2]
        self.assertEqual(RainierView.eye_position(view,px,pz)[1],level+lookout.DECK+1.25)
        RainierView.visit_lookout(view)
        px,pz=view.trip_pose[:2]
        self.assertEqual(RainierView.eye_position(view,px,pz)[1],height(px,pz)+1.25)

    def test_regional_builder_streams_the_same_grid_triangles(self):
        from array import array
        from geometry import HeightField
        from rainier_pixels import build_world
        field=self.field()
        mesh=field.mesh()
        with patch('rainier_pixels.region_field',return_value=field),patch('fremont_lookout.location',return_value=None),patch.object(
                HeightField,'mesh',side_effect=AssertionError('materialized regional mesh')):
            _,origin,vertices,*_=build_world(False,regional=True)
        expected=array('f')
        for triangle in mesh.triangles:
            for i in triangle[:3]:
                p=mesh.vertices[i]
                expected.extend((p.x-origin.x,p.y-origin.y,p.z-origin.z))
        for axis in range(3):
            self.assertEqual(vertices[axis::7],expected[axis::3])

    def test_whole_field_and_summit_approach(self):
        field=self.field()
        west,east,south,north=bounds(field)
        self.assertEqual(field.height(west,south),0)
        self.assertAlmostEqual(field.height(east,north),29)
        x,z=summit_start(field)
        self.assertEqual(x,east)
        self.assertAlmostEqual(north-z,2200)
        # A shallow tap can reach a distant hillside beyond the valley extent.
        target=ground_target((0,100,0,0,0),.5,.55,1,lambda x,z:0,
                             bounds=bounds(field),regional=True)
        self.assertGreater(target[1],1000)
        walker=SimpleNamespace(x=0,z=0,yaw=0)
        walk_to(walker,target,.1,speed=25.6)
        self.assertAlmostEqual(walker.z,2.56)

    def test_overview_selects_northwestern_part_in_portrait_or_landscape(self):
        field=self.field()
        for cols,rows in ((45,40),(92,20)):
            view=SimpleNamespace(world=(field,),name='Rainier walk',map_position=None,
                host=SimpleNamespace(window=lambda _:SimpleNamespace(w=cols,h=rows)))
            overview=ReliefMap(view)
            left,top,w,h=overview.frame((cols-2)*8,(rows-3)*16)
            self.assertFalse(overview.tap_xy((left+w*.25)/8-.5,(top+h*.25)/16-.5))
            west,east,south,north=bounds(field)
            x,z=view.map_position
            self.assertAlmostEqual((x-west)/(east-west),.25)
            self.assertAlmostEqual((z-south)/(north-south),.75)

    def test_valley_map_layers_zoom_and_walking_waypoint(self):
        from valley_map import ValleyMap,RIVER,TRAIL_COLORS,SIZE
        from river_walk import site
        for cols,rows in ((45,40),(92,20)):
            window=SimpleNamespace(w=cols,h=rows)
            view=SimpleNamespace(world=(site()[0],),camera=(0.,0.,0.,0.),name='Walk',destination=None,
                trail=SimpleNamespace(free_look=True),host=SimpleNamespace(window=lambda _:window))
            overview=ValleyMap(view)
            self.assertEqual(overview.normalized(0,0),(.5,.5))
            self.assertTrue(overview.tap_xy(1,rows-4))
            self.assertFalse(overview.local)
            self.assertEqual(len(overview.rgb),SIZE*SIZE*3)
            for color in (RIVER,*TRAIL_COLORS.values()):self.assertIn(bytes(color),overview.rgb)
            left,top,w,h=overview.frame((cols-2)*8,(rows-3)*16)
            overview.tap_xy((left+.67*w)/8-.5,(top+.28*h)/16-.5)
            target=overview.selected
            self.assertGreater(min(target),0)
            self.assertIsNone(view.destination)
            overview.tap_xy(1,rows-4)
            self.assertEqual(overview.normalized(*target),(.5,.5))
            self.assertFalse(overview.tap_xy(cols//2,rows-4))
            self.assertEqual(view.destination,target)
            self.assertFalse(view.trail.free_look)

    def test_paradise_outing_and_seasonal_discoveries(self):
        import paradise_meadow as meadow
        from river_notebook import PLANTS
        from rainier_pixels import RainierView
        view=RainierView(None)
        menu=HikeMenu(view)
        row=menu.lines(40).index('Paradise meadows')
        with patch.object(view,'start_region') as start:
            self.assertTrue(menu.tap_xy(0,row))
            start.assert_called_once_with(meadow_arrival=True)
        view.regional=True
        view.meadow_site=(120.,350.)
        self.assertFalse(menu.tap_xy(0,row))
        self.assertEqual(view.trip_pose[:2],view.meadow_site)
        self.assertEqual(set(k for k,_,_ in meadow.patches()),set(meadow.FLOWERS))
        for k in meadow.FLOWERS:
            self.assertIn(k,PLANTS)
            self.assertEqual([s for s in range(4) if meadow.blooming(k,s)],[0,3] if k=='avalanche_lily' else [0])
        counts={}
        def face(a,b,c,color,material):
            self.assertGreaterEqual(min(a.y,b.y,c.y),9.98)
            counts[material]=counts.get(material,0)+3
        meadow.meadow(lambda x,z:10.,face,*view.meadow_site)
        self.assertEqual(set(counts),{.815,.86,.88})
        self.assertLess(sum(counts.values()),350_000)

    def test_close_approach_uses_parent_edges_and_fine_walking_triangles(self):
        from array import array
        from geometry import HeightField,Vec
        from rainier_pixels import surface
        import summit_approach as p
        from summit_detail import attach_approach
        parent=HeightField(145,104,Vec(-4300,0,1150),34,38,
                           tuple(3000+i*.25+j*.5 for j in range(104) for i in range(145)),'meters')
        field=attach_approach(parent,array('f',[3400.])*(p.WIDTH*p.HEIGHT))
        patch=field.inset
        for i,j in ((0,25),(42,0),(p.WIDTH-1,81),(115,p.HEIGHT-1)):
            x,z=patch.origin.x+i*patch.dx,patch.origin.z+j*patch.dz
            self.assertAlmostEqual(surface(field,x,z),surface(parent,x,z),places=3)
        x,z=patch.origin.x+28.2*patch.dx,patch.origin.z+40.1*patch.dz
        self.assertAlmostEqual(surface(field,x,z),surface(patch,x,z))
        self.assertGreater(surface(field,x,z)-surface(parent,x,z),300.)

    def test_summit_inset_registered_to_terrain_and_walk_height(self):
        import summit_detail
        from rainier_pixels import surface
        from geometry import HeightField,Vec
        field=HeightField(257,257,Vec(-12800,0,-12800),100.,100.,tuple(
            1800+x-z for z in range(257) for x in range(257)),'meters')
        meta=dict(longitude_first=-122.1+.68/514,latitude_first=46.53+.53/514,
                  longitude_step=.68/257,latitude_step=.53/257)
        terrain=summit_detail.attach(field,meta)
        fine=terrain.inset
        self.assertGreater(max(fine.values),4300)
        for i in (0,1,13,97,200,252):
            for col,row in ((0,i),(252,i),(i,0),(i,252)):
                x,z=fine.origin.x+col*fine.dx,fine.origin.z+row*fine.dz
                self.assertAlmostEqual(surface(terrain,x,z),surface(field,x,z))
        x,z=fine.origin.x+118.31*fine.dx,fine.origin.z+139.57*fine.dz
        self.assertAlmostEqual(surface(terrain,x,z),surface(fine,x,z))
        self.assertIs(summit_detail.attach(field,dict(meta,latitude_first=46.2)),field)
