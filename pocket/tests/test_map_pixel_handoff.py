# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Pixel maps retain a complete viewport while replacement work is pending."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from concurrent.futures import Future
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'graphics'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from map_pixels import View,place_labels,terrain_detail

class Pool:
 def __init__(self):self.future=Future()
 def submit(self,*args):return self.future

class MapPixelHandoff(unittest.TestCase):
 def test_overview_preparation_does_not_block_dispatch_and_wakes_when_ready(self):
  pool=Pool();wake=[]
  locator=NS(key=('first',),layer=(0,0,24,12,()),renderer=NS(pool=pool,completion_wakeup=lambda:wake.append(True)))
  app=View(NS(),None);surface=NS(inset=(locator,2,3))
  with patch.object(app,'build',side_effect=AssertionError('GUI thread performed terrain work')):
   self.assertIsNone(app.inset_scene(surface))
   pool.future.set_result('scene')
   self.assertTrue(app.pixel_dirty)
   self.assertEqual(app.inset_scene(surface),('scene',2,3,24,12))
  self.assertEqual(wake,[True])
  self.assertIsNone(app.inset_scene(NS(inset=None)))
  self.assertIsNone(app._inset_scene)
 def test_closed_overview_discards_work_that_already_started(self):
  pool=Pool();pool.future.set_running_or_notify_cancel()
  locator=NS(key=('first',),layer=(0,0,24,12,()),renderer=NS(pool=pool,completion_wakeup=None))
  app=View(NS(),None)
  self.assertIsNone(app.inset_scene(NS(inset=(locator,0,0))))
  self.assertIsNone(app.inset_scene(NS(inset=None)))
  pool.future.set_result('obsolete')
  self.assertIsNone(app._inset_pending)
  self.assertIsNone(app._inset_scene)

 def test_overview_refines_on_arm_without_desktop_dem(self):
  from array import array
  from offline_map import MapFeatures
  view=NS(width=24,height=12,center=(0.,0.),span=10.,cell_aspect=2.)
  module=NS(Viewport=lambda c,s,w,h,a:NS(width=w,height=h))
  engine=NS(_rgb_terrain=lambda v,t:([(' ',(1,2,3),(4,5,6))]*(v.width*v.height),''))
  surface=NS(terrain=True,pixel_overview=True,image=NS(source='cached-overview'),renderer=NS(module=module,engine=engine))
  features=MapFeatures(array('I',[0]*576),(),{},24,24)
  with patch('desktop_elevation.enabled',return_value=False):
   samples,w,h=terrain_detail(surface,view,features)
  self.assertGreater(w,24);self.assertGreater(h,24)
  self.assertLessEqual(w*h,32768);self.assertEqual(len(samples),w*h)
 def test_prepared_overview_keeps_pixel_samples_without_resampling(self):
  from array import array
  from offline_map import Image,MapSurface,MapFeatures
  projection=NS(center=(0.,0.),span=160.,cell_aspect=2.)
  samples=array('I',[123]*(160*160))
  prepared=MapFeatures(samples,(),{},160,160,pixel_detail=True)
  image=Image(160,80,(),'overview',(),0.,projection,'locator',prepared)
  renderer=NS(semantic_features=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Repeated terrain sampling')))
  surface=MapSurface(image,(0,0,30,15,()),renderer,('overview',),pixel_overview=True)
  view=NS(center=(0.,0.),span=160.,cell_aspect=2.,width=30,height=15)
  features=surface.features(view,())
  result,w,h=terrain_detail(surface,view,features)
  self.assertIs(result,samples);self.assertEqual((w,h),(160,160))

 def test_arm_gui_uses_pixel_density_and_prepared_display_terrain(self):
  from array import array
  from offline_map import MapFeatures
  calls=[]
  def sample(v,t):calls.append((v.width,v.height));return [(' ',(1,2,3),(4,5,6))]*(v.width*v.height),''
  engine=NS(terrain=object(),_catalogue_original_rgb=sample,
            _rgb_terrain=lambda *a:(_ for _ in ()).throw(AssertionError('Fine DEM queried for display')))
  module=NS(Viewport=lambda c,s,w,h,a:NS(width=w,height=h))
  surface=NS(terrain=True,image=NS(source='semantic'),renderer=NS(module=module,engine=engine))
  view=NS(width=98,height=24,center=(0.,0.),span=160.,cell_aspect=2.)
  features=MapFeatures(array('I',[0]*(98*48)),(),{},98,48)
  with patch('desktop_elevation.enabled',return_value=False):samples,w,h=terrain_detail(surface,view,features)
  self.assertGreater(w,98*4);self.assertGreater(h,48*4)
  self.assertLessEqual(w*h,262144);self.assertEqual(calls,[(w,h//2)])

 def test_precomputed_overview_never_samples_live_terrain(self):
  from map_overview import Overview
  from offline_map import MapSurface
  from paint import ink
  overview=Overview();overview.data=dict(width=192,height=96,center=(0.,0.),span=400.,cells=(('▀',ink(40,80,20,background=(20,60,120))),)*(192*96))
  import importlib.util
  spec=importlib.util.spec_from_file_location('overview_viewport',Path(__file__).resolve().parents[1]/'shell/vendor/packet-console/n810-map-next.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  image=overview.image(module,192,96)
  renderer=NS(module=module,semantic_features=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Live terrain sampled')))
  surface=MapSurface(image,(0,0,30,15,()),renderer,('cached',),pixel_overview=True)
  view=surface.viewport();features=surface.features(view,())
  samples,w,h=terrain_detail(surface,view,features)
  self.assertIs(samples,image.features.terrain);self.assertEqual((w,h),(192,192))

 def test_pixel_map_excludes_terminal_terrain_but_keeps_sidebar_controls(self):
  import struct
  from pixel_scene import uncovered_records
  raw=b''.join(struct.pack('=IIQ',i,65+i,0) for i in range(24))
  pieces=list(uncovered_records(raw,6,4,[(0,0,4,4),(4,0,2,2)]))
  self.assertEqual(len(pieces),1)
  data,x,y,w,h=pieces[0];self.assertEqual((x,y,w,h),(4,2,2,2))
  cells=list(struct.iter_unpack('=IIQ',data))
  self.assertEqual([row[0] for row in cells],list(range(4)))
  self.assertEqual([row[1] for row in cells],[81,82,87,88])

 def test_water_and_lowland_have_distinct_luminance_and_hue(self):
  from elevation_display import WATER_COLOR,display_color
  land=display_color(0,0,1000)
  self.assertGreater(WATER_COLOR[2],WATER_COLOR[1])
  self.assertGreater(land[1],land[2])
  luminance=lambda c:sum(a*b for a,b in zip(c,(.2126,.7152,.0722)))
  self.assertGreater(luminance(land)-luminance(WATER_COLOR),20)

 def test_semantic_loading_reports_actual_work(self):
  from offline_map import Renderer
  renderer=Renderer();renderer.engine=object()
  for phase,text in [('terrain','Loading terrain…'),('features','Preparing map features…'),('places','Loading place labels…')]:
   renderer.loading_phase=phase
   self.assertEqual(renderer.loading_message(),text)
  renderer.close()
 def test_semantic_presentation_reuses_one_clean_engine_frame(self):
  from offline_map import Renderer,MapSurface
  from map_fixtures import install
  renderer=Renderer();install(self,renderer);renderer.set_presentation('semantic')
  key=('map',(45.0,-120.0),5.,40,16,True,True);renderer._wanted=key
  try:
   image=renderer._render(key)
   self.assertEqual(image.source,'semantic')
   self.assertIsNotNone(image.features)
   self.assertFalse(any(char in '┼─│/\\' for char,_ in image.cells))
   from offline_map import map_rgb
   tui,_=renderer.engine.prepare(image.projection,True,True)
   for row in range(image.height):
    for column in range(image.width):
     index=row*image.width+column
     self.assertEqual(image.features.terrain[(row*2+1)*image.width+column],map_rgb(tui[index][2]))
   surface=MapSurface(image,(0,2,image.width,image.height,image.cells),renderer,('test',))
   self.assertEqual(surface.viewport().key,image.projection.key)
   with patch.object(renderer.engine,'_rgb_terrain',side_effect=AssertionError('terrain resampled')):
    self.assertIs(surface.features(image.projection,image.cells),image.features)
    gridded=MapSurface(image,(0,2,image.width,image.height,image.cells),renderer,('grid',),'on')
    with patch.object(renderer.engine,'_rgb_terrain',side_effect=AssertionError('terrain resampled')):
     features=gridded.features(image.projection,image.cells)
    self.assertEqual(len(features.vectors),len(image.features.vectors)+1)
    self.assertIs(features.terrain,image.features.terrain)
  finally:renderer.close()

 def test_prepared_semantic_view_reopens_without_feature_generation(self):
  from offline_map import Renderer
  from map_fixtures import install
  import tempfile
  from pathlib import Path
  import os
  key=('map',(45.0,-120.0),5.,40,16,True,True)
  with tempfile.TemporaryDirectory() as cache,patch.dict(os.environ,{'N810_MAP_BASES':cache}):
   first=Renderer();install(self,first);first.set_presentation('semantic');first._wanted=key
   image=first._render(key);first.close()
   second=Renderer(maps=first.maps);second.set_presentation('semantic');second._wanted=key
   with patch.object(second,'_features_from_terrain',side_effect=AssertionError('features rebuilt')):
    reopened=second._render(key)
   self.assertEqual(reopened.source,'semantic-prepared')
   self.assertEqual(reopened.features,image.features)
   path=Path(second.prepared_path('geography',image.projection,(True,True,False)))
   path.write_bytes(b'incomplete')
   self.assertEqual(second._render(key).source,'semantic')
   second.close()

 def test_real_engine_terrain_is_independent_of_painted_cells(self):
  from offline_map import Renderer
  from paint import ink
  from map_fixtures import install
  renderer=Renderer();install(self,renderer)
  key=('map',(45.0,-120.0),35.,24,10,True,True);renderer._wanted=key
  try:
   image=renderer._render(key)
   view=renderer.module.Viewport(image.projection.center,image.projection.span,image.width,image.height)
   actual=renderer.semantic_features(view,image.cells)
   painted=(('┼',ink(255,0,0,background=(0,0,255))),)*len(image.cells)
   changed=renderer.semantic_features(view,painted)
   self.assertEqual(actual.terrain,changed.terrain)
   self.assertEqual(len(actual.terrain),2*image.width*image.height)
  finally:renderer.close()

 def test_engine_gives_pixel_backend_typed_terrain_halves(self):
  from offline_map import Renderer
  from paint import ink,rgb
  renderer=Renderer()
  # Glyphs and their inks are TUI presentation, unrelated to pixel terrain.
  style=ink(1,2,3,background=(4,5,6))
  cells=(('┼',style),('H',style),('─',style),('▀',style))
  renderer.engine=NS(_rgb_terrain=lambda view,terrain:([
   ('▀',(200,30,20),(20,30,200)),
   ('▀',(20,30,200),(200,30,20)),
   (' ',(200,30,20),(200,30,20)),
   (' ',(20,30,200),(20,30,200))],''))
  with patch('map_geography.selected_geography',return_value=((),(),())),patch('map_geography.vector_segments',return_value=()),patch('map_geography.label_annotations',return_value={}):
   features=renderer.semantic_features(NS(width=4,height=1,span=1),cells)
  fore=rgb(200,30,20);back=rgb(20,30,200)
  self.assertEqual(list(features.terrain),[fore,back,fore,back,back,fore,fore,back])

 def test_surface_capability_controls_native_view(self):
  surface=NS(layer=(0,2,3,1,object()),image=NS(projection=object()),key=('source',))
  owner=NS(map_surface=lambda:surface)
  app=View(None,owner)
  self.assertIs(app.plan()[2],surface)
  owner.map_surface=lambda:None
  self.assertIsNone(app.plan())

 def test_explicit_labels_and_geometry_ignore_cell_glyphs(self):
  from array import array
  features=NS(terrain=array('I',[0]*8),sample_width=4,sample_height=2,vectors=(),labels={0:('B',0),1:(' ',0)})
  surface=NS(unavailable_reason='',viewport=lambda:object(),features=lambda *args:features,overlay_vectors=())
  layer=(0,2,4,1,(('B',0),(' ',0),('┼',0),('▀',0)))
  scene=View(None,None).build(layer,surface)
  self.assertEqual([(mark.index,mark.ch) for mark in scene.marks],[(0,ord('B')),(1,ord(' '))])
  self.assertEqual(scene.lines,())

 def test_place_names_move_as_complete_runs_around_station_marks(self):
  labels={4:('A',1),5:('B',1),6:('C',1)}
  overlay={5:('X',2)}
  placed=place_labels(labels,overlay,8,4)
  indexes=sorted(placed)
  self.assertEqual(indexes,[12,13,14])
  self.assertEqual(''.join(placed[i][0] for i in indexes),'ABC')
  self.assertNotIn(5,placed)

 def test_desktop_semantic_terrain_samples_more_than_one_pair_per_cell(self):
  from array import array
  from offline_map import MapFeatures
  view=NS(width=8,height=4,center=(0.,0.),span=1.,cell_aspect=2.,ground_m_per_halfcell=1.)
  module=NS(Viewport=lambda center,span,w,h,aspect:NS(center=center,span=span,width=w,height=h,cell_aspect=aspect))
  engine=NS(_rgb_terrain=lambda dense,terrain:([(' ',(1,2,3),(4,5,6))]*(dense.width*dense.height),''))
  renderer=NS(module=module,engine=engine)
  surface=NS(terrain=True,image=NS(source='semantic'),renderer=renderer)
  features=MapFeatures(array('I',[0]*(8*4*2)),(),{},8,8)
  with patch('desktop_elevation.enabled',return_value=True),patch('desktop_elevation.pixel_samples',return_value=None):
   samples,width,height=terrain_detail(surface,view,features)
  self.assertGreater(width,view.width)
  self.assertGreater(height,view.height*2)
  self.assertEqual(len(samples),width*height)

 def test_pan_composite_reuses_only_the_visible_map(self):
  from array import array
  from scenes import MapScene,MapComposite
  host=NS(origin=(0,0),window=lambda name:name,bounds=lambda window:(1,2,12,6))
  app=View(host,None)
  sharp=MapScene(5,4,array('I',[0]*40),5,8,(),())
  composite,x,y,width,height=app.positioned(sharp,(0,0,5,4,()),NS(content_width=5,inset=None),(8,-16))
  self.assertIsInstance(composite,MapComposite)
  self.assertEqual((x,y,width,height),(16,48,40,64))
  self.assertEqual(len(composite.layers),1)
  self.assertIs(composite.layers[0][0],sharp)
  self.assertEqual(composite.layers[0][1:3],(8,-16))

 def test_unavailable_source_is_opaque_notice_without_fallback(self):
  surface=NS(unavailable_reason='No semantic layers',viewport=lambda:object(),features=lambda *args:self.fail('Fallback sampled'))
  scene=View(None,None).build((0,0,24,2,object()),surface)
  self.assertEqual(set(scene.terrain),{0})
  self.assertEqual(scene.lines,())
  self.assertEqual(''.join(chr(m.ch) for m in scene.marks),'No semantic layers')

 def test_zoom_keeps_scene_and_annotations_until_replacement(self):
  app=View(NS(origin=(0,0),window=lambda name:None,bounds=lambda w:(2,3,30,20)),None)
  pool=Pool();surface=NS(renderer=NS(pool=pool,completion_wakeup=None))
  layer=(0,2,20,10,object());plan=[('first',layer,surface)]
  app.plan=lambda:plan[0];first=NS(marks=object());second=NS(marks=object())
  app.build=lambda *args:self.fail('UI performed a synchronous map build')
  self.assertIsNot(app.render_image()[0],first)
  self.assertIsNone(app.ready)
  pool.future.set_result(first)
  self.assertIs(app.render_image()[0],first)
  pool.future=Future()
  plan[0]=('zoomed',(0,2,20,10,object()),surface)
  self.assertIs(app.render_image()[0],first)
  self.assertIs(app.presentation_marks()[0],first.marks)
  pool.future.set_result(second)
  self.assertIs(app.render_image()[0],second)
  self.assertIs(app.presentation_marks()[0],second.marks)
  self.assertEqual(app.key,'zoomed')
  pool.future=Future();plan[0]=('another-zoom',(0,2,20,10,object()),surface)
  self.assertIs(app.render_image()[0],second)
  previous=pool.future;pool.future=Future();plan[0]=('resized',(0,2,25,10,object()),surface)
  self.assertEqual(app.render_image()[0].width,25)
  self.assertTrue(previous.cancelled())
  pool.future.set_result(first)
  self.assertIs(app.render_image()[0],first)
  self.assertEqual(app.key,'resized')

if __name__=='__main__':unittest.main()
