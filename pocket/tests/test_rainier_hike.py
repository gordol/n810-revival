"""Regional hiking uses every elevation sample and metre-based map bounds."""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

pocket=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(pocket/'graphics'),str(pocket/'shell'),str(pocket/'shell/apps/surface-renderer')]
from rainier_hike import ReliefMap,bounds,region_field,summit_start
from river_explore import ground_target,walk_to


class HikeTests(TestCase):
    def field(self):
        meta=dict(nx=6,nz=5,latitude_first=46.,latitude_step=.06,longitude_step=.08)
        values=list(range(30))
        with patch('rainier_data.download'),patch('terrain_elevation.grid',return_value=(meta,values)):
            return region_field()

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
