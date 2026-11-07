# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Panning retains overlap and prepares only newly exposed edge strips."""
import sys,unittest,importlib.util
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from map_regions import Regions
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('incremental_engine',root/'shell/vendor/packet-console/n810-map-next.py')
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)

class IncrementalRegionTests(unittest.TestCase):
 def test_scroll_reuses_overlap_in_all_directions(self):
  for dx,dy in ((8,0),(-8,0),(0,5),(0,-5),(8,5),(-8,-5)):
   with self.subTest(delta=(dx,dy)):
    regions=Regions();view=engine.Viewport((47.,-122.),100.,101,41)
    calls=[];serial=[0]
    def prepare(v):
     calls.append(v);serial[0]+=1
     return tuple((serial[0],i) for i in range(v.width*v.height)),'fixture'
    first=regions.frame(view,prepare,padding=False)
    center=first.unproject(50+dx,20+dy)
    moved=engine.Viewport(center,100.,101,41)
    before=regions.prepared_cells
    result=regions.frame(moved,prepare,padding=False)
    self.assertGreater(regions.reused_cells,101*41*.7)
    self.assertLess(regions.prepared_cells-before,101*41*.4)
    self.assertTrue(all(v.width<101 or v.height<41 for v in calls[1:]))
    self.assertNotIn(None,result.cells)
    for y in range(max(0,-dy),min(41,41-dy)):
     for x in range(max(0,-dx),min(101,101-dx)):
      self.assertEqual(result.cells[y*101+x],first.cells[(y+dy)*101+x+dx])
 def test_changed_scale_or_layer_does_not_reuse_old_pixels(self):
  regions=Regions();calls=[]
  def prepare(v):calls.append(v);return tuple(range(v.width*v.height)),'fixture'
  regions.frame(engine.Viewport((47.,-122.),100.,101,41),prepare,'terrain',padding=False)
  regions.frame(engine.Viewport((47.,-122.),50.,101,41),prepare,'terrain',padding=False)
  regions.frame(engine.Viewport((47.,-122.),50.,101,41),prepare,'roads',padding=False)
  self.assertEqual(len(calls),3);self.assertEqual(regions.reused_cells,0)
 def test_wide_north_south_pan_reprojects_overlap_instead_of_rebuilding(self):
  regions=Regions();calls=[]
  def prepare(v):calls.append(v);return tuple(range(v.width*v.height)),'fixture'
  first=regions.frame(engine.Viewport((47.,-122.),953.,243,61),prepare,padding=False)
  moved=engine.Viewport(first.unproject(121,35),953.,243,61)
  regions.frame(moved,prepare,padding=False)
  self.assertGreater(regions.reused_cells,243*61*.85)
  self.assertTrue(all(v.width<243 or v.height<61 for v in calls[1:]))
 def test_narrow_patch_keeps_parent_road_detail_level(self):
  import map_geography
  overview=[{'name':'main road'}]
  data=dict(tiles={},overview_roads=overview,labels=[],coverage=[-124.,46.,-120.,49.],step=.25)
  view=engine.Viewport((47.,-122.),5.,20,40)
  with patch.object(map_geography,'load',return_value=data):
   self.assertEqual(map_geography.data_for_view(view,display_span=100.)['roads'],overview)
   self.assertEqual(map_geography.data_for_view(view)['roads'],())

if __name__=='__main__':unittest.main()
