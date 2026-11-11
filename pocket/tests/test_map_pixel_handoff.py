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
  with patch('map_geography.vector_segments',return_value=()),patch('map_geography.label_annotations',return_value={}):
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

 def test_pan_composite_moves_sharp_scene_over_surrounding_map(self):
  from array import array
  from scenes import MapScene,MapComposite
  host=NS(origin=(0,0),window=lambda name:name,bounds=lambda window:(1,2,12,6))
  app=View(host,None);app._surround_scene=MapScene(15,12,array('I',[0]*(15*12*2)),15,24,(),())
  sharp=MapScene(5,4,array('I',[0]*40),5,8,(),())
  composite,x,y,width,height=app.positioned(sharp,(0,0,5,4,()),NS(content_width=5,inset=None),(8,-16))
  self.assertIsInstance(composite,MapComposite)
  self.assertEqual((x,y,width,height),(16,48,40,64))
  self.assertEqual(composite.layers[0][1:3],(-40,-64))
  self.assertEqual(composite.layers[1][1:3],(8,-16))

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
  app.build=lambda *args:first
  self.assertIs(app.render_image()[0],first)
  plan[0]=('zoomed',(0,2,20,10,object()),surface)
  self.assertIs(app.render_image()[0],first)
  self.assertIs(app.presentation_marks()[0],first.marks)
  pool.future.set_result(second)
  self.assertIs(app.render_image()[0],second)
  self.assertIs(app.presentation_marks()[0],second.marks)
  self.assertEqual(app.key,'zoomed')
  pool.future=Future();plan[0]=('another-zoom',(0,2,20,10,object()),surface)
  self.assertIs(app.render_image()[0],second)
  plan[0]=('resized',(0,2,25,10,object()),surface)
  self.assertIs(app.render_image()[0],first)
  self.assertEqual(app.key,'resized')

if __name__=='__main__':unittest.main()
