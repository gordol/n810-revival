"""A child can complete the offline trail using one tap per stop."""
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'graphics'),str(root/'shell')]
from river_walk import BUSHES, FOX, BerryTrail, nearby_calls, river_gain, site, wet


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
        from river_walk import channel
        from rainier_pixels import surface
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

    def test_river_stones_round(self):
        from river_notebook import CARDS,RiverNotebook
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
