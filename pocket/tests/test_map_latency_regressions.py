# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Detail loading does no work for covered DEM pixels; previews preserve half cells."""
from array import array
import importlib.util
from pathlib import Path
import sys,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'shell'))
import desktop_elevation as dem
from offline_map import Image,ReprojectedPlane,map_rgb
from paint import rgb,ink
spec=importlib.util.spec_from_file_location('latency_viewport',ROOT/'shell/vendor/packet-console/n810-map-next.py')
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)

class LatencyTests(unittest.TestCase):
 def sample(self,water=False):
  import numpy as np
  with tempfile.TemporaryDirectory() as folder:
   coarse=Path(folder)/'coarse';fine=Path(folder)/'fine'
   for p in (coarse,fine):p.write_text('{}')
   def metadata(path,*args):
    return dict(nx=512,nz=512,longitude_first=0.,latitude_first=0.,longitude_step=.01 if path==coarse else .001,latitude_step=.01 if path==coarse else .001,nodata=-32768,_index_stamp=0,tiles={f'{x},{y}':dict(width=256,height=256) for y in range(2) for x in range(2)})
   calls=[]
   def tile(path,stamp,x,y):
    calls.append((path.name,x,y));values=array('h',[100 if path==coarse else 900])*65536
    if path==coarse:
     for row in range(256):values[row*256+11]=values[row*256+12]=-32768
    return values,256
   view=SimpleNamespace(width=3,height=1,span=20.,center=(.2,.2),cell_aspect=2)
   with patch.object(dem,'sources',return_value=[coarse,fine]),patch.object(dem,'metadata',side_effect=metadata),patch('local_elevation.tile',side_effect=tile):
    result,_=dem.sample(view,land_mask=np.zeros((2,3),dtype=bool) if water else None)
   return result,calls
 def test_fine_gather_reads_only_pixels_missing_from_overview(self):
  result,calls=self.sample()
  self.assertEqual(result[0].tolist(),[900,100,100])
  self.assertEqual({x for name,x,y in calls if name=='fine'},{0})
 def test_known_water_does_not_read_any_dem_tile(self):
  result,calls=self.sample(water=True)
  self.assertEqual(calls,[])
 def test_map_color_lookup_is_exactly_the_existing_rgb565_quantization(self):
  for value in range(256):self.assertEqual(map_rgb((value,255-value,value//2)),rgb(value,255-value,value//2))
  self.assertEqual(map_rgb((-1,300,3.5)),rgb(-1,300,3.5))
 def test_zoom_reprojection_keeps_contiguous_halves_and_does_not_repeat_roads(self):
  style=ink(200,30,20,background=(20,30,200))
  source=engine.Viewport((47.,-122.),2.,2,1)
  destination=engine.Viewport((47.,-122.),2.,8,4)
  image=Image(2,1,(('▀',style),('▀',style)),'',(),0.,source)
  plane=ReprojectedPlane(image,destination)
  self.assertTrue(plane.resampled)
  self.assertEqual(plane[0][1]&0xffffff,(style>>24)&0xffffff)
  self.assertEqual(plane[24][1]&0xffffff,style&0xffffff)
  self.assertTrue(all(plane[i][0]==' ' for i in range(len(plane))))
  roads=ReprojectedPlane(Image(2,1,(('\\',style),('\\',style)),'',(),0.,source),destination)
  self.assertTrue(all(roads[i][0]==' ' for i in range(len(roads))))
 def test_pan_retains_glyphs_and_repeated_pans_keep_one_source(self):
  source=engine.Viewport((47.,-122.),20.,20,10)
  cells=tuple(('R',1) for _ in range(200));image=Image(20,10,cells,'',(),0.,source)
  first=ReprojectedPlane(image,source)
  second=ReprojectedPlane(Image(20,10,first,'',(),0.,source),source)
  self.assertFalse(second.resampled);self.assertIs(second.base,cells)
  self.assertEqual(second[0],('R',1))
 def test_resized_station_map_projects_labels_once_at_display_size(self):
  from station_workspace import StationMap,Context
  context=Context();context.catalog(dict(revision=1,has_more=False,rows=[dict(call='NEAR',position=dict(lat=47.,lon=-122.),categories=[],symbol=None)]))
  context.select(None,dict(call='NEAR',position=(47.,-122.)))
  app=StationMap(context,ROOT/'shell/vendor/packet-console',lambda:None)
  app.renderer.module=engine
  app.width=80;app.height=27;app.center=(47.,-122.);app.span=20.
  view=engine.Viewport(app.center,app.span,40,12)
  image=Image(40,12,tuple(('▀',ink(200,30,20,background=(20,30,200))) for _ in range(480)),'',(),0.,view)
  try:
   with patch.object(app.renderer,'frame',return_value=image),patch('repeater_catalog.load',return_value=()):
    app.lines()
    self.assertEqual(app._hit_size,(80,24))
    self.assertEqual(app._display_layer[2:4],(80,24))
    hits=[hit for hit in app._station_hits if hit[3]=='NEAR']
    self.assertEqual(len(hits),1)
    x,y,width,call=hits[0]
    self.assertTrue(any(entity.key=='NEAR' for entity in app.entities_at(x,y+2)))
    self.assertEqual(sum(cell[0]=='N' for cell in app._display_layer[4]),1)
  finally:app.close();app.renderer.close()
 def test_locator_uses_retained_terrain_when_legacy_preview_is_not_installed(self):
  from station_workspace import StationMap,Context
  app=StationMap(Context(),ROOT/'shell/vendor/packet-console',lambda:None)
  app.width=96;app.height=27;app.center=(47.,-122.);app.span=20.
  app.renderer.module=engine;app.side_overview=True;app._locator_overview.data=None
  view=engine.Viewport(app.center,app.span,96,24)
  image=Image(96,24,tuple(('▀',ink(i%255,80,40,background=(40,i%255,80))) for i in range(96*24)),'',(),0.,view)
  try:
   with patch.object(app.renderer,'frame',return_value=image),patch.object(app.renderer,'context_frame',return_value=None),patch('repeater_catalog.load',return_value=()):
    app.lines()
    x,y,w,h,locator=app._locator_rect
    self.assertEqual((w,h),(30,15))
    self.assertEqual(locator.source,'locator')
    self.assertEqual(locator.projection.center,app.center)
    self.assertGreater(locator.projection.span,app.span)
    self.assertGreater(len({cell[1] for cell in locator.cells}),2)
  finally:app.close();app.renderer.close()
 def test_region_prefetch_is_bounded_near_visible_area(self):
  from map_regions import Regions
  view=engine.Viewport((47.,-122.),40.,240,90);prepared=[]
  def prepare(v):prepared.append(v.width*v.height);return [(' ',0)]*(v.width*v.height),''
  Regions().frame(view,prepare)
  self.assertLessEqual(sum(prepared),view.width*view.height*1.6)

if __name__=='__main__':unittest.main()
