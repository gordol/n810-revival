"""A child can complete the offline trail using one tap per stop."""
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'graphics'),str(root/'shell'),str(root/'shell/apps/landscape-lab')]
from pnw.river_walk import BUSHES, FOX, BerryTrail, nearby_calls, river_gain, site, wet


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

    def test_calls_follow_animals_in_three_dimensions(self):
        subjects=[('barred_owl',0.,10.,0.,.5),('trout',1.,0.,0.,1.),('chipmunk',0.,0.,18.,.3)]
        near=nearby_calls(subjects,0.,0.,0.)
        self.assertEqual([key for key,_,_ in near],['barred_owl'])
        self.assertAlmostEqual(near[0][2],1-10/65)
        self.assertFalse(nearby_calls(subjects,200.,0.,0.))

    def test_river_sound_fades_from_nearest_bank(self):
        segments=[(0,0,1,0,50),(100,0,0,1,50)]
        self.assertEqual(river_gain(40,8,segments),1.)
        self.assertAlmostEqual(river_gain(40,-168,segments),.5)
        self.assertEqual(river_gain(108,40,segments),1.)
        self.assertAlmostEqual(river_gain(100,378,segments),1/3)
        self.assertEqual(river_gain(0,0,[]),0.)

    def test_water_surface_falls_downstream_and_clears_terrain(self):
        from pnw.river_walk import channel
        from pnw.scene import surface
        field,_=site()
        river=channel()
        bed=river.bed_field(field)
        vertices=[]
        river.mesh(bed.height,lambda *args:None,lambda *vertex:vertices.append(vertex))
        self.assertGreater(river.rows[0].stage,river.rows[-1].stage)
        for a,b in zip(river.rows,river.rows[1:]):
            self.assertGreater(b.station,a.station)
            self.assertLessEqual(b.stage,a.stage)
        for (a,_,sa),(b,_,sb),(c,_,sc) in zip(vertices[::3],vertices[1::3],vertices[2::3]):
            self.assertLess((b.x-a.x)*(c.z-a.z)-(b.z-a.z)*(c.x-a.x),0)
            edge=(a,b) if sa==sb else (a,c) if sa==sc else (b,c)
            self.assertAlmostEqual(edge[0].y,edge[1].y)
            for p in (a,b,c):
                self.assertGreater(p.y,surface(bed,p.x,p.z))
            x,z=(a.x+b.x+c.x)/3,(a.z+b.z+c.z)/3
            self.assertAlmostEqual(river.water_height(x,z),(a.y+b.y+c.y)/3)
        self.assertIsNotNone(river.water_height(15,8))
        self.assertIsNone(river.water_height(-1000,900))

    def test_camera_clears_rendered_bank_and_water_triangles(self):
        from geometry import Vec
        from pnw.scene import RainierView,surface,valley_floor
        from pnw.river_walk import channel
        bed,_=valley_floor()
        origin=Vec(0,surface(bed,0,0),0)
        view=RainierView.__new__(RainierView)
        view.regional=False
        view.world=(bed,origin)
        max_gap=0.
        def check(a,b,c):
            nonlocal max_gap
            for u,v in ((.3,.4),(.5,.5),(0.,0.)):
                w=1.-u-v
                x,y,z=(u*i+v*j+w*k for i,j,k in zip((a.x,a.y,a.z),(b.x,b.y,b.z),(c.x,c.y,c.z)))
                max_gap=max(max_gap,y-surface(bed,x,z))
                eye=view.eye_position(x,z)[1]+origin.y
                self.assertGreaterEqual(eye+1e-7,y+1.25)
        water=[]
        def water_vertex(p,*_):
            water.append(p)
            if len(water)==3:
                check(*water)
                water.clear()
        channel().mesh(lambda x,z:surface(bed,x,z),lambda a,b,c,*_:check(a,b,c),water_vertex)
        self.assertGreater(max_gap,5.)
        self.assertEqual(view.walk_height(-900,900),surface(bed,-900,900))

    def test_mapped_site_and_dry_game_route(self):
        field,segments=site()
        self.assertEqual(field.nx,257)
        self.assertTrue(550<field.height(0,0)<570)
        self.assertTrue(wet(15,8,segments))
        stops=((0,0),*BUSHES,FOX)
        self.assertGreater(math.dist(BUSHES[-1],FOX),35.)
        for i,(start,end) in enumerate(zip(stops,stops[1:])):
            distance=math.dist(start,end)
            self.assertGreater(distance,30. if i else 10.)
            for j in range(math.ceil(distance)+1):
                t=j/math.ceil(distance)
                self.assertFalse(wet(start[0]+(end[0]-start[0])*t,start[1]+(end[1]-start[1])*t,segments,1.))


    def test_guided_walk_can_look_sideways(self):
        trail=BerryTrail()
        owner=SimpleNamespace(x=0.,z=0.,yaw=1.5)
        trail.guiding=trail.free_look=True
        for _ in range(80):trail.advance(owner,.05)
        self.assertEqual(owner.yaw,1.5)
        self.assertEqual(len(trail.picked),1)

    def test_trout_holds_above_pool_bed_and_rises_during_hatch(self):
        from unittest.mock import patch
        from geometry import Vec
        from pnw.river_channel import TROUT_POOL
        from pnw.scene import encounters,surface,valley_floor
        from pnw.river_walk import channel
        bed,_=valley_floor()
        with patch('pnw.scene.ENCOUNTERS',(('trout',*TROUT_POOL,.65),)):
            for age,hatch,above in ((5,True,False),(.8,True,True),(.8,False,False),(2,True,False)):
                fish=encounters(bed,Vec(0,0,0),[(0,1,3,0,3)],age,hatch=hatch)[0]
                stage=channel().water_height(fish.x,fish.z)
                self.assertGreater(fish.y,surface(bed,fish.x,fish.z))
                if above:self.assertGreater(fish.y,stage)
                else:self.assertLess(fish.y+.39*.65,stage)

    def test_pool_cast_bite_release_and_retry_with_touch_buttons(self):
        from pnw.scene import RainierView
        view=RainierView(None)
        view.camera=(9.,7.,0.,0.)
        def tap(label):
            _,_,(x,y,w,h)=next(tool for tool in view.walk_tools(42,32) if tool[1]==label)
            self.assertTrue(view.scene_tap(x+w/2,y+h/2,42,32))
        from unittest.mock import Mock,patch
        view.fishing.rng=Mock()
        view.fishing.rng.uniform.return_value=0.
        view.fishing.rng.random.side_effect=(.99,.8,.1,.8)
        tap('Cast fly')
        self.assertIsNotNone(view.fishing.position(0))
        self.assertEqual(view.fishing.update(10),0)
        view.age=10
        tap('Cast again')
        for j in range(90):
            view.age+=.1
            if view.fishing.update(view.age):break
        from tempfile import TemporaryDirectory
        from pnw.river_notebook import DiscoveryBook
        with TemporaryDirectory() as data,patch.dict('os.environ',XDG_DATA_HOME=data),patch('pnw.scene.vibration') as pulse:
            tap('Lift rod!')
            pulse.assert_called_with(130)
            # One tap starts continuous winding, another eases off for a run.
            for j in range(300):
                view.age+=.1
                view.update_fishing(view.age)
                if view.fishing.state=='landed':break
                if view.fishing.reeling==view.fishing.pulling(view.age):tap(view.fishing.label(view.age))
            self.assertEqual(view.fishing.state,'landed')
            self.assertNotIn('keep',[a for a,_,_ in view.walk_tools(42,32)])
            self.assertGreater(sum(call.args==(240,) for call in pulse.call_args_list),1)
            tap('Release trout')
            self.assertEqual([entry[1] for entry in DiscoveryBook(view).entries],['trout'])
            self.assertIsNone(view.fishing.position(view.age))

    def test_motion_rod_needs_a_sustained_tilt(self):
        from pnw.river_fishing import rod_tilted
        import json
        def readings(*values):
            return '\n'.join(json.dumps({'phone accelerometer':{'values':v}},indent=2) for v in values)
        flat=(0,0,9.8)
        up=(0,6.9,6.9)
        self.assertFalse(rod_tilted(readings(flat,up,flat,(0,0,19))))
        self.assertTrue(rod_tilted(readings(flat,up,up)))

    def test_brook_catch_and_photo_share_a_page_after_keep(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from data_paths import rainier_cache
        from pnw.scene import RainierView
        from pnw.river_notebook import DiscoveryBook
        with TemporaryDirectory() as data,patch.dict('os.environ',XDG_DATA_HOME=data):
            view=RainierView(None)
            fish=view.fishing
            fish.state='fight'
            fish.target='brook_trout#1'
            fish.reeling=True
            fish.remaining=.001
            fish.hook=fish.turn=fish.last_pulse=0.
            fish.last=2.
            view.update_fishing(2.1)
            self.assertEqual(fish.state,'landed')
            self.assertEqual(DiscoveryBook(view).entries,[('Brook trout','brook_trout','Landed at the trout pool.')])
            fish.keep()
            photos=rainier_cache()/'photos'
            photos.mkdir()
            photo=photos/'brook_trout-123.png'
            photo.touch()
            book=DiscoveryBook(view)
            self.assertEqual(len(book.entries),1)
            self.assertEqual(book.preview,photo)

    def test_line_break_slack_missed_bite_and_species_retention(self):
        from pnw.river_fishing import Fishing
        from unittest.mock import Mock
        def strike():
            rng=Mock()
            rng.uniform.return_value=0.
            rng.random.return_value=.05
            game=Fishing(rng)
            game.tap(0,(9,7))
            for j in range(90):
                t=j/10
                if game.update(t):return game,t
            self.fail('expected brook trout to take the fly')
        game,t=strike()
        game.update(t+4)
        self.assertEqual(game.state,'over')
        game,t=strike()
        game.tap(t,(9,7))
        game.tap(t+.01,(9,7))
        for j in range(1,16):game.update(t+j*.1)
        self.assertEqual(game.note,'Line broke - trout away')
        game,t=strike()
        game.tap(t,(9,7))
        game.update(t+9)
        self.assertEqual(game.note,'Slack line - trout away')
        game,t=strike()
        game.state='landed'
        game.keep()
        self.assertTrue(game.kept_brook)
        game.tap(t+1,(9,7))
        self.assertEqual(game.target,'trout')
        game.state='landed'
        game.keep()
        self.assertEqual(game.state,'landed')

    def test_gather_supplies_once_and_build_at_camp(self):
        from pnw.scene import RainierView
        from pnw.river_camp import CAMP,SUPPLIES
        view=RainierView(None)
        def actions():return {key:box for key,_,box in view.walk_tools(42,32)}
        for i,(_,x,z) in enumerate(SUPPLIES):
            view.camera=(x,z,0.,0.)
            self.assertNotIn('build',actions())
            key='gather'+str(i)
            bx,by,_,_=actions()[key]
            view.scene_tap(bx+1,by+1,42,32)
            self.assertNotIn(key,actions())
        view.camera=(*CAMP,0.,0.)
        bx,by,_,_=actions()['build']
        view.scene_tap(bx+1,by+1,42,32)
        self.assertTrue(view.tent and view.camp_built)
        self.assertNotIn('build',actions())

    def test_population_and_trail_geometry(self):
        from pnw.scene import ENCOUNTERS
        from pnw.river_walk import hiking_paths
        self.assertEqual(len({key for key,*_ in ENCOUNTERS}),len(ENCOUNTERS))
        self.assertGreater(sum(key.partition('#')[0]=='trout' for key,*_ in ENCOUNTERS),2)
        paths=hiking_paths()
        self.assertEqual({p['name'] for p in paths},{'Silver Falls Loop Trail','Hot Springs Trail'})
        self.assertTrue(all(abs(c)<=1024 for p in paths for pt in p['xz'] for c in pt))

    def test_river_stones_round(self):
        from pnw.river_notebook import CARDS,RiverNotebook
        book=RiverNotebook()
        for index,(_,_,correct,_) in enumerate(CARDS):
            lines=book.lines(34)
            self.assertTrue(all(len(line)<=34 for line in lines))
            answer=next(row for row,action in book.actions.items() if action==correct)
            self.assertTrue(book.tap(answer))
            book.lines(34)
            self.assertEqual(book.score,index+1)
            advance=next(row for row,action in book.actions.items() if action==2)
            self.assertEqual(book.tap(advance),index+1<len(CARDS))
