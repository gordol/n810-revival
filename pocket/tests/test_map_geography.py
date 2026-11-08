import sys,unittest,gzip,json,time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from map_geography import maidenhead,grid,load,signature
from map_fixtures import install, regional_data_available
class GeographyTests(unittest.TestCase):
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
