import os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import desktop_elevation as dem
from offline_map import Renderer

from map_fixtures import install, regional_data_available

class DesktopElevationTests(unittest.TestCase):
 @unittest.skipUnless(regional_data_available() and dem.sources(), "Regional elevation integration test: build maps and elevation first")
 def test_normal_map_preserves_bays_with_relief_on_or_off(self):
  r=Renderer();key=('map',(47.25,-122.56),.1,41,15,True,True);r._wanted=key
  try:
   r._render(key)
   for terrain in (False,True):
    for pos,water in (((47.25,-122.56),True),((47.30,-122.65),False)):
     view=r.module.Viewport(pos,.1,41,15)
     cells,_=r.engine._rgb_terrain(view,terrain)
     _,top,bottom=cells[7*41+20]
     self.assertEqual(top==r.engine.palette.WATER,water)
     self.assertEqual(bottom==r.engine.palette.WATER,water)
  finally:r.close()
 def test_nokia_keeps_prepared_renderer(self):
  with patch('platform.machine',return_value='armv7l'):self.assertFalse(dem.enabled())
 @unittest.skipUnless(regional_data_available() and dem.sources(), "Regional elevation integration test: build maps and elevation first")
 def test_regional_heights_are_sampled_outside_lakewood(self):
  r=Renderer()
  try:
   r._wanted=('map',(47.02,-122.9),4.,70,25,True,True)
   r._render(r._wanted)
   import numpy as np
   values,spacing=dem.sample(r.module.Viewport((47.02,-122.9),4,70,25))
   self.assertTrue(np.isfinite(values).any());self.assertLess(float(np.nanmin(spacing)),150)
  finally:r.close()
 def test_second_renderer_reads_disk_cache(self):
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'N810_MAP_BASES':str(Path(folder)/'cache')}):
   key=('map',(47.04,-122.95),5.,65,22,True,True)
   r=Renderer();install(self,r);r._wanted=key
   try:first=r._render(key)
   finally:r.close()
   r=Renderer();install(self,r);r._wanted=key
   try:
    second=r._render(key)
    self.assertEqual(first.cells,second.cells);self.assertEqual(first.legend,second.legend);self.assertEqual(r.engine.stats['cache'],'prepared')
   finally:r.close()
 @unittest.skipUnless(regional_data_available() and dem.sources(), "Regional elevation integration test: build maps and elevation first")
 def test_actual_station_map_uses_desktop_dem_not_prepared_terrain(self):
  from station_workspace import StationMap,Context
  form=StationMap(Context(),Path(__file__).resolve().parents[1]/'shell/vendor/packet-console',lambda:None)
  form.width=120;form.height=42;form.center=(47.1,-122.78);form.span=35
  try:
   until=time.monotonic()+10
   while time.monotonic()<until:
    form.lines();image=form._shown_image or form._image
    if image:break
    time.sleep(.01)
   self.assertIsNotNone(image,form.renderer.error)
   self.assertIn('Local DEM',image.legend)
   self.assertNotEqual(image.source,'regional-pack')
  finally:form.close();form.renderer.close()
