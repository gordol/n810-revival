from reference_fixtures import activate
activate()
import sys,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from terrain_elevation import sample_elevation,calculate
class SharedElevationTests(unittest.TestCase):
 def test_map_and_profile_sample_same_best_local_height(self):
  import desktop_elevation
  for pos in ((47.252900,-122.444300),(47.02,-122.9),(46.973167,-123.138167)):
   height,m=sample_elevation(*pos)
   self.assertIn('fictional-fine',m['source']);self.assertLess(abs(m['latitude_step'])*111320,15)
   values,_=desktop_elevation.sample(SimpleNamespace(center=pos,span=0,width=1,height=1,cell_aspect=2))
   self.assertAlmostEqual(height,float(values[0,0]),places=7)
 def test_profile_reports_fine_source_and_actual_grid_spacing(self):
  result=calculate('47.252900,-122.444300','46.973167,-123.138167',count=4097,frequency_mhz=915,tx_height_m=15,rx_height_m=24)
  self.assertIn('fictional-fine',result['source']);self.assertLess(result['finest_grid_spacing_north_m'],15)
  fine=sum(row['samples'] for row in result['elevation_sources'] if 'fictional-fine' in row['source'])
  self.assertGreater(fine/len(result['samples']),.95)
 def test_path_cache_includes_elevation_revision(self):
  import terrain_sites
  terrain_sites.cached_path.cache_clear()
  with patch('local_elevation.revision',return_value=('first',)) as revision,patch('terrain_sites.classify_path',return_value={'los':'clear'}) as classify:
   args=('47,-123','47.01,-123',915,15,24)
   terrain_sites.cached_path(*args);terrain_sites.cached_path(*args);self.assertEqual(classify.call_count,1)
   revision.return_value=('updated',);terrain_sites.cached_path(*args);self.assertEqual(classify.call_count,2)
 def test_preview_apply_accepts_cropped_projection(self):
  from station_workspace import StationMap,Context
  form=StationMap(Context(),Path(__file__).resolve().parents[1]/'shell/vendor/packet-console',lambda:None)
  form.width=120;form.height=42;form.center=(5.4655,5.3055);form.span=35
  try:
   form.target_box.choose((5.4455,5.2855),30);form.apply_target()
   until=time.monotonic()+10
   while form._detail_request is not None and time.monotonic()<until:form.lines();time.sleep(.01)
   self.assertIsNone(form._detail_request,form.renderer.error)
   self.assertEqual(form.center,(5.4455,5.2855));self.assertEqual(form.span,30)
   self.assertEqual(tuple(form._image.projection.center),(5.4455,5.2855))
  finally:form.close();form.renderer.close()
 def test_both_zoom_directions_keep_visible_preview_box_while_rendering(self):
  from station_workspace import StationMap,Context
  from unittest.mock import patch
  form=StationMap(Context(),Path(__file__).resolve().parents[1]/'shell/vendor/packet-console',lambda:None)
  form.width=120;form.height=42;form.center=(5.4655,5.3055);form.span=35
  try:
   until=time.monotonic()+10
   while time.monotonic()<until:
    form.lines()
    if form._shown_image:break
    time.sleep(.01)
   self.assertIsNotNone(form._shown_image)
   for key in ('+','-','-'):
    with patch.object(form.renderer,'frame',return_value=None):
     form.key(key);lines=form.lines()
     self.assertIsNotNone(form._zoom_context_image)
     layer=form.layer();self.assertTrue(any(layer[4][i][0] in '─│┌┐└┘' for i in range(len(layer[4]))))
     self.assertNotIn('Apply',lines[0]);self.assertNotIn('Cancel',lines[0])
    self.assertIsNone(form._detail_request);self.assertIsNone(form.poll_interval())
  finally:form.close();form.renderer.close()
 def test_zoom_gesture_cannot_also_select_terrain_endpoint(self):
  from native_terrain_profile import TerrainProfile
  app=TerrainProfile();self.addCleanup(app.close)
  app.width=120;app.height=42
  until=time.monotonic()+10
  while time.monotonic()<until:
   app.lines()
   if app.map.image:break
   time.sleep(.01)
  # A zoom occurs between press and release, but the displayed span is unchanged.
  app.map.pointer(35,14,120)
  app.map.base.zoom_at_pointer(35,14,120)
  app.map.pointer(35,14,120,released=True)
  self.assertEqual(app.map.points,[None,None])
 def test_preview_never_applies_until_enter_and_escape_cancels(self):
  from native_terrain_profile import TerrainProfile
  app=TerrainProfile();self.addCleanup(app.close)
  app.result={'bottleneck':dict(distance_m=165,coordinate=(5.5555,5.5555),fresnel_clearance_m=-1)}
  for overview in (False,True):
   for after_x in (False,True):
    app.map.base.cancel_pointer();app.map.base.full_overview=overview
    camera=app.map.center,app.map.span
    if after_x:app.key('x')
    for key in ('+','-','+'):app.map.base.key(key)
    for _ in range(10):app.map.base.poll()
    self.assertEqual((app.map.center,app.map.span),camera)
    self.assertIsNone(app.map.base._detail_request);self.assertIsNone(app.map.base.poll_interval())
    app.map.base.key('\x1b');self.assertIsNone(app.map.base.target_box.view)
    self.assertEqual((app.map.center,app.map.span),camera)
    app.map.base.key('+');app.map.base.key('\r');self.assertIsNotNone(app.map.base._detail_request)
 def test_preview_refines_without_applying_selected_camera(self):
  from station_workspace import StationMap,Context
  form=StationMap(Context(),Path(__file__).resolve().parents[1]/'shell/vendor/packet-console',lambda:None)
  form.width=240;form.height=90;form.center=(5.5555,5.54555);form.span=8.8
  try:
   until=time.monotonic()+10
   while time.monotonic()<until:
    form.lines()
    if form._shown_image:break
    time.sleep(.01)
   camera=form.center,form.span;form.key('-');target=form.target_box.view
   until=time.monotonic()+10
   while time.monotonic()<until:
    lines=form.lines()
    if form._local_overview.refined is not None:break
    time.sleep(.01)
   self.assertIsNotNone(form._local_overview.coarse,form.renderer.error)
   self.assertIsNotNone(form._local_overview.refined,form.renderer.error)
   self.assertEqual(form._local_overview.refined.width,240)
   self.assertEqual((form.center,form.span),camera);self.assertEqual(form.target_box.view,target)
   self.assertIn('Enter confirm','\n'.join(lines));self.assertIsNone(form._detail_request)
  finally:form.close();form.renderer.close()
 def test_context_scaling_does_not_repeat_half_blocks_or_road_glyphs(self):
  from paint import ink
  from offline_map import ContextPlane
  color=ink(200,30,20,background=(20,30,200))
  plane=ContextPlane([('▀',color)],1,1,4,8)
  # A single red/blue cell becomes contiguous red then blue, not eight stripes.
  self.assertEqual(plane[0][0],' ');self.assertEqual(plane[7*4][0],' ')
  self.assertEqual(plane[0][1]&0xffffff,(color>>24)&0xffffff)
  self.assertEqual(plane[7*4][1]&0xffffff,color&0xffffff)
  road=ContextPlane([('┼',color)],1,1,4,8)
  self.assertTrue(all(road[i][0]==' ' for i in range(len(road))))
 def test_shoreline_uses_local_vector_geometry_at_display_resolution(self):
  from desktop_shoreline import mask
  for pos,expected in (((47.252900,-122.444300),1),((47.203,-122.61),0),
                       ((47.30,-122.45),1),((47.25,-122.56),0)):
   view=SimpleNamespace(center=pos,span=.01,width=3,height=2,cell_aspect=2)
   result=mask(view);self.assertIsNotNone(result);self.assertEqual(int(result[1,1]),expected)
