"""Regional hiking uses every elevation sample and metre-based map bounds."""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

pocket=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(pocket/'graphics'),str(pocket/'shell'),str(pocket/'shell/apps/surface-renderer')]
from rainier_hike import HikeMenu,ReliefMap,bounds,region_field,summit_start
from river_explore import ground_target,walk_to


class HikeTests(TestCase):
    def field(self):
        meta=dict(nx=6,nz=5,latitude_first=46.,latitude_step=.06,longitude_step=.08)
        values=list(range(30))
        with patch('rainier_data.download'),patch('terrain_elevation.grid',return_value=(meta,values)):
            return region_field()

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

    def test_whole_field_and_summit_approach(self):
        field=self.field()
        west,east,south,north=bounds(field)
        self.assertEqual(field.height(west,south),0)
        self.assertAlmostEqual(field.height(east,north),29)
        x,z=summit_start(field)
        self.assertEqual(x,east)
        self.assertAlmostEqual(north-z,2200)
        # A shallow tap can reach a distant hillside beyond the valley extent.
        target=ground_target((0,100,0,0,0),.5,.55,1,lambda x,z:0,lambda x,z:False,
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
