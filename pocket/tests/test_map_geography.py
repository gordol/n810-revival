import sys,unittest,gzip,json,time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from map_geography import maidenhead,grid,grid_features,grid_enabled,load,signature,decorate,label_annotations,vector_segments,selected_geography
from map_fixtures import install, regional_data_available
class GeographyTests(unittest.TestCase):
 def test_one_detail_policy_selects_terminal_and_pixel_roads(self):
  data=dict(streams=[dict(kind='river',bbox=(-1,-1,1,1),points=((0,0),(.1,0)))],
            roads=[dict(kind='residential',bbox=(-1,-1,1,1),points=((0,0),(.1,0))),
                   dict(kind='highway',bbox=(-1,-1,1,1),points=((0,0),(.1,0)))],labels=[])
  view=SimpleNamespace(span=50.,bbox=(-1,-1,1,1),ground_m_per_halfcell=100)
  with patch('map_geography.data_for_view',return_value=data):
   streams,roads,_=selected_geography(SimpleNamespace(forest_roads=False),view)
  self.assertEqual(len(streams),1)
  self.assertEqual([r['kind'] for r in roads],['highway'])

 def test_native_pixel_detail_keeps_local_streets_and_forest_toggle_is_live(self):
  data=dict(streams=[],labels=[],roads=[
      dict(kind='residential',bbox=(-1,-1,1,1),points=((0,0),(.1,0))),
      dict(kind='forest',bbox=(-1,-1,1,1),points=((0,.1),(.1,.1)))])
  view=SimpleNamespace(span=5.,bbox=(-1,-1,1,1),ground_m_per_halfcell=100)
  with patch('map_geography.data_for_view',return_value=data),patch('map_geography.covers',return_value=True):
   self.assertEqual(selected_geography(SimpleNamespace(forest_roads=False),view)[1],())
   roads=selected_geography(SimpleNamespace(forest_roads=False),view,detail_pixels=8)[1]
   self.assertEqual([item['kind'] for item in roads],['residential'])
   roads=selected_geography(SimpleNamespace(forest_roads=True),view,detail_pixels=8)[1]
  self.assertEqual([item['kind'] for item in roads],['residential','forest'])

 def test_pixel_grid_uses_same_auto_policy_and_geographic_lines(self):
  self.assertTrue(grid_enabled('auto',4))
  self.assertFalse(grid_enabled('auto',52))
  self.assertTrue(grid_enabled('on',52))
  view=SimpleNamespace(bbox=(-122.6,47.1,-122.4,47.3),span=4,width=40,height=20,
                       project=lambda lon,lat:((lon+122.6)*200,(47.3-lat)*100))
  (color,points),labels=grid_features(view)
  self.assertEqual(color,(117,143,153))
  self.assertEqual(len(points)%4,0)
  self.assertTrue(points)
  self.assertTrue(labels)

 def test_semantic_vectors_use_source_geometry(self):
  layer=dict(tile=100000,index={(0,0):(0,)},coords=(0,0,10000,0))
  engine=SimpleNamespace(atlas=SimpleNamespace(roads=[layer],streams=None),layer_bounds={id(layer):(-100000,-100000,100000,100000)})
  view=SimpleNamespace(bbox=(-1,-1,1,1),ground_m_per_halfcell=100,span=20)
  self.assertEqual([(color,list(points)) for color,points in vector_segments(engine,view)],
                   [((219,205,155),[0.,0.,.1,0.])])

 def test_label_annotations_share_semantic_selection_with_cell_frame(self):
  view=SimpleNamespace(span=20.,width=8,height=2,bbox=(-1,-1,1,1),project=lambda lon,lat:(4,1))
  engine=SimpleNamespace(labels=[dict(name='City',lon=0,lat=0,kind='city')])
  frame=[('┼',(220,205,155),(10,20,30))]*16
  data=dict(roads=[],streams=[],labels=[])
  with patch('map_geography.data_for_view',return_value=data),patch('map_hydrography.labels',return_value=()):
   painted=decorate(engine,view,frame)
   marks=label_annotations(engine,view)
  self.assertEqual(painted[0],frame[0])
  self.assertNotIn(0,marks)
  self.assertEqual(''.join(marks[i][0] for i in range(2,6)),'City')
  self.assertEqual(''.join(painted[i][0] for i in range(2,6)),'City')

 @unittest.skipUnless(regional_data_available(), "Regional integration test: run make maps-download maps first")
 def test_public_arterial_is_rendered_and_named_at_close_zoom(self):
  from offline_map import Renderer
  r=Renderer();key=('map',(5.5388,5.5355),.756,240,87,True,True);r._wanted=key
  try:
   frame=r._render(key)
   text='\n'.join(''.join(c for c,s in frame.cells[i:i+frame.width]) for i in range(0,len(frame.cells),frame.width))
   self.assertIn('South Way SW',text)
  finally:r.close()
 def test_tacoma_locator(self):self.assertEqual(maidenhead(47.252900,-122.444300),'CN87sg')
 def test_grid_uses_real_locator_boundaries(self):
  from offline_map import Renderer
  r=Renderer();install(self,r);key=('map',(5.5555,5.5555),35.,120,42,True,True);r._wanted=key
  try:
   r._render(key);marks=grid(r.module.Viewport((5.5555,5.5555),35,120,42))
   self.assertTrue(marks);self.assertIn('JJ25',''.join(v[0] for v in marks.values()))
  finally:r.close()
 @unittest.skipUnless(regional_data_available(), "Regional integration test: run make maps-download maps first")
 def test_real_arterial_and_named_lakes_retained(self):
  from map_geography import data_for_view
  from map_hydrography import labels
  data=data_for_view(SimpleNamespace(bbox=(-122.65,47.1,-122.4,47.3),span=15))
  self.assertTrue(any('Steilacoom Boulevard' in r['name'] for r in data['roads']))
  self.assertIn('Lake Steilacoom',{r['name'] for r in labels()})
  forest=data_for_view(SimpleNamespace(bbox=(-122,46.7,-121.7,47),span=30))
  self.assertTrue(any(r['kind']=='forest' for r in forest['roads']))
  south=data_for_view(SimpleNamespace(bbox=(-123.1,46.3,-122.6,46.8),span=70))
  interstate=[p for r in south['roads'] if 'I 5' in r['name'] for p in r['points']]
  self.assertLess(min(p[1] for p in interstate),46.8)
 @unittest.skipUnless(regional_data_available(), "Regional integration test: run make maps-download maps first")
 def test_chambers_reservoir_is_water_at_close_and_wide_scales(self):
  from desktop_shoreline import mask
  for span in (.1,4,10,35):
   view=SimpleNamespace(center=(47.1928746,-122.5734199),span=span,width=241,height=89,cell_aspect=2)
   result=mask(view)
   # At wide scales this narrow impoundment can be smaller than one cell.
   self.assertTrue((result[87:91,119:122]==0).any(),span)
 def test_grid_auto_and_manual_controls_do_not_apply_camera(self):
  from station_workspace import StationMap,Context
  f=StationMap(Context(),Path(__file__).resolve().parents[1]/'shell/vendor/packet-console',lambda:None)
  try:
   self.assertEqual(f.maidenhead_grid,'auto');camera=f.center,f.span
   for value in ('on','off','auto'):f.key('u');self.assertEqual(f.maidenhead_grid,value)
   self.assertEqual((f.center,f.span),camera)
  finally:f.close();f.renderer.close()
