"""Pixel maps retain a complete viewport while replacement work is pending."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from concurrent.futures import Future
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'graphics'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from map_pixels import View,surround_camera,place_labels

FIXTURE_CENTER=(47.25,-122.44)  # Fictional test grid point.

class Pool:
 def __init__(self):self.future=Future();self.calls=0
 def submit(self,*args):self.calls+=1;return self.future

class MapPixelHandoff(unittest.TestCase):
 def test_place_label_moves_as_one_word_around_station(self):
  labels={2+i:(ch,7) for i,ch in enumerate('Renton')}
  overlay={4:('E',9)}
  moved=place_labels(labels,overlay,12,5)
  self.assertEqual(''.join(cell[0] for _,cell in sorted(moved.items())),'Renton')
  self.assertFalse(set(moved)&set(overlay))
  self.assertEqual({index//12 for index in moved},{1})

 def test_station_collision_keeps_city_name_in_one_overlay(self):
  from array import array
  from offline_map import Plane
  features=NS(terrain=array('I',[0]*72),sample_width=12,sample_height=6,
              vectors=(),labels={2+i:(ch,7) for i,ch in enumerate('Renton')})
  view=NS(width=12,height=3,project=lambda lon,lat:(lon,lat))
  surface=NS(image=NS(source='semantic'),renderer=NS(engine=object()),terrain=True,
             roads=True,grid_mode='off',unavailable_reason='',viewport=lambda:view,
             features=lambda *a:features,overlay_vectors=())
  with patch('map_pixels.terrain_detail',return_value=(features.terrain,12,6)):
   scene=View(None,None).build((0,0,12,3,Plane(object(),{4:('E',9)})),surface)
  self.assertEqual(len(scene.base.marks),0)
  self.assertEqual(''.join(chr(mark.ch) for mark in scene.overlay_marks if mark.index>=12),'Renton')
  self.assertEqual({mark.index for mark in scene.overlay_marks if mark.index>=12},set(range(14,20)))
  self.assertEqual(next(chr(mark.ch) for mark in scene.overlay_marks if mark.index==4),'E')
 def test_desktop_drag_surround_uses_sharp_map_samples(self):
  from offline_map import Renderer
  from map_fixtures import install
  from desktop_elevation import enabled
  if not enabled():self.skipTest('Desktop pixel terrain is unavailable')
  renderer=Renderer();install(self,renderer);renderer.set_presentation('semantic')
  key=('map',(FIXTURE_CENTER),35.,90,38,True,True);renderer._wanted=key
  try:
   renderer._render(key)
   scene=View(None,None).prepare_surround(renderer,(FIXTURE_CENTER),70.,90,38,75.,True,7)
   self.assertEqual((scene.width,scene.height),(180,76))
   self.assertEqual((scene.sample_width,scene.sample_height),(1260,1064))
   self.assertFalse(scene.smooth)
  finally:renderer.close()
 def test_surrounding_terrain_tracks_the_map_pane_projection(self):
  projection=NS(width=100,span=40.,center=(47.,-122.),
                unproject=lambda x,y:(47.,-122.+(x-49.5)*.01),
                project=lambda lon,lat:((lon+122.)/.01+49.5,19.5))
  center,span=surround_camera(projection,68,40)
  self.assertAlmostEqual(span,40*135/99)
  self.assertAlmostEqual(center[0],47.)
  self.assertAlmostEqual(projection.project(center[1],center[0])[0],33.5)

 def test_real_viewport_without_unproject_centers_surround_on_visible_pane(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('map_viewport_test',Path(__file__).resolve().parents[1]/'shell/vendor/packet-console/n810-map-next.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  view=module.Viewport((47.,-122.),160.,125,34)
  center,span=surround_camera(view,93,34)
  x,y=view.project(center[1],center[0])
  self.assertAlmostEqual(x,46.)
  self.assertAlmostEqual(y,16.5)
  self.assertAlmostEqual(span,160.*185/124)

 def test_coarse_backdrop_moves_with_detailed_texture(self):
  from gpu_scene import backdrop_rect
  first=backdrop_rect(8,32,544,480,(0,0))
  moved=backdrop_rect(8,32,544,480,(80,40))
  self.assertEqual((moved[0]-first[0],moved[1]-first[1]),(80,40))
  self.assertEqual(moved[2:],first[2:])
 def test_semantic_presentation_reuses_one_clean_engine_frame(self):
  from offline_map import Renderer,MapSurface
  from map_fixtures import install
  renderer=Renderer();install(self,renderer);renderer.set_presentation('semantic')
  key=('map',(FIXTURE_CENTER),5.,40,16,True,True);renderer._wanted=key
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
  key=('map',(FIXTURE_CENTER),35.,24,10,True,True);renderer._wanted=key
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

 def test_box_only_redraw_reuses_terrain_and_geographic_lines(self):
  from array import array
  from unittest.mock import Mock
  view=NS(width=4,height=1,project=lambda lon,lat:(lon,lat))
  features=NS(terrain=array('I',[0]*8),sample_width=4,sample_height=2,
              vectors=(((220,200,150),array('d',[0.,0.,1.,0.])),),labels={})
  image=NS(source='semantic')
  sample=Mock(return_value=features)
  surface=NS(image=image,renderer=NS(engine=object()),terrain=True,roads=True,
             grid_mode='off',unavailable_reason='',viewport=lambda:view,
             features=sample,overlay_vectors=())
  builder=View(None,None)
  plain=(0,0,4,1,object())
  from offline_map import Plane
  marked=(0,0,4,1,Plane(plain[4],{0:('X',0)}))
  with patch('map_pixels.terrain_detail',return_value=(features.terrain,4,2)) as dense:
   first=builder.build(plain,surface)
   second=builder.build(marked,surface)
  self.assertEqual(sample.call_count,1)
  self.assertEqual(dense.call_count,1)
  self.assertIs(first.terrain,second.terrain)
  self.assertIs(first.base,second.base)
  self.assertEqual(len(first.overlay_marks),0)
  self.assertEqual(len(second.overlay_marks),1)
  self.assertIs(first.lines[0][1],second.lines[0][1])
  self.assertEqual([(m.index,m.ch) for m in second.marks],[(0,ord('X'))])

 def test_gui_target_box_uses_vector_without_cell_border(self):
  from array import array
  from offline_map import Plane
  view=NS(width=4,height=1,project=lambda lon,lat:(lon,lat))
  features=NS(terrain=array('I',[0]*8),sample_width=4,sample_height=2,vectors=(),labels={})
  box=Plane(object(),{0:('┌',0),1:('─',0)})
  surface=NS(image=NS(source='semantic'),renderer=NS(engine=object()),terrain=True,
             roads=True,grid_mode='off',unavailable_reason='',viewport=lambda:view,
             features=lambda *a:features,overlay_vectors=(((255,210,65),array('d',[0.,0.,1.,0.])),),
             box_plane=box)
  with patch('map_pixels.terrain_detail',return_value=(features.terrain,4,2)):
   scene=View(None,None).build((0,0,4,1,box),surface)
  self.assertEqual(len(scene.marks),0)
  self.assertEqual(len(scene.overlay_lines),1)

 def test_sidebar_cell_marks_are_excluded_from_moving_pixel_scene(self):
  from array import array
  from offline_map import Plane
  view=NS(width=4,height=1,project=lambda lon,lat:(lon,lat))
  features=NS(terrain=array('I',[0]*8),sample_width=4,sample_height=2,
              vectors=(),labels={3:('S',1)})
  surface=NS(image=NS(source='semantic'),renderer=NS(engine=object()),terrain=True,
             roads=True,grid_mode='off',unavailable_reason='',viewport=lambda:view,
             features=lambda *a:features,overlay_vectors=(),content_width=2)
  with patch('map_pixels.terrain_detail',return_value=(features.terrain,4,2)):
   scene=View(None,None).build((0,0,4,1,Plane(object(),{0:('M',1),3:('B',1)})),surface)
  self.assertEqual(scene.content_width,16)
  self.assertEqual([(mark.index,mark.ch) for mark in scene.marks],[(0,ord('M'))])

 def test_loaded_box_redraw_does_not_wait_for_map_worker(self):
  from array import array
  from offline_map import Plane
  pool=Pool();renderer=NS(pool=pool,completion_wakeup=None,engine=object(),forest_roads=False)
  view=NS(width=4,height=1,project=lambda lon,lat:(lon,lat))
  features=NS(terrain=array('I',[0]*8),sample_width=4,sample_height=2,vectors=(),labels={})
  image=NS(source='semantic',projection=object())
  base=object();current=[NS(image=image,renderer=renderer,terrain=True,roads=True,
       grid_mode='off',unavailable_reason='',viewport=lambda:view,features=lambda *a:features,
       overlay_vectors=(),layer=(0,0,4,1,base),key=('first',))]
  owner=NS(map_surface=lambda:current[0]);host=NS(origin=(0,0),window=lambda n:None,bounds=lambda w:(0,0,6,3))
  app=View(host,owner)
  with patch('map_pixels.terrain_detail',return_value=(features.terrain,4,2)):
   first=app.render_image()[0]
   current[0]=NS(**{**vars(current[0]),'layer':(0,0,4,1,Plane(base,{0:('X',0)})),'key':('box',)})
   second=app.render_image()[0]
  self.assertEqual(pool.calls,0)
  self.assertIs(first.base,second.base)
  self.assertEqual([(m.index,m.ch) for m in second.marks],[(0,ord('X'))])

 def test_pixel_drag_repositions_retained_scene_without_rebuilding(self):
  from array import array
  pool=Pool();renderer=NS(pool=pool,completion_wakeup=None,engine=object())
  view=NS(width=4,height=1,project=lambda lon,lat:(lon,lat))
  features=NS(terrain=array('I',[0]*8),sample_width=4,sample_height=2,vectors=(),labels={})
  image=NS(source='semantic',projection=object())
  surface=NS(image=image,renderer=renderer,terrain=True,roads=True,grid_mode='off',
             unavailable_reason='',viewport=lambda:view,features=lambda *a:features,
             overlay_vectors=(),layer=(0,0,4,1,object()),key=('original',))
  base=NS(_gpu_pan_offset=None,_target_drag=None,_pan_drag=None,_image_view=((47.,-122.),2.),
          center=(47.,-122.),span=2.)
  owner=NS(base=base,terrain_active=False,map_surface=lambda:surface)
  host=NS(origin=(0,0),window=lambda n:None,bounds=lambda w:(0,0,6,3))
  app=View(host,owner)
  with patch('map_pixels.terrain_detail',return_value=(features.terrain,4,2)) as dense:
   original=app.render_image()
   base._target_drag=object();base._gpu_pan_offset=(6,4)
   self.assertTrue(app.pixel_dirty)
   shifted=app.render_image()
  self.assertIs(shifted[0],original[0])
  self.assertEqual(shifted[-2:],(6,4))
  self.assertEqual(dense.call_count,1)
  self.assertEqual(pool.calls,0)

 def test_forest_toggle_reuses_terrain_scene_and_road_overlay(self):
  from array import array
  pool=Pool();renderer=NS(pool=pool,completion_wakeup=None,engine=object(),forest_roads=False)
  view=NS(width=4,height=1,project=lambda lon,lat:(lon,lat))
  features=NS(terrain=array('I',[0]*8),sample_width=4,sample_height=2,
              vectors=(),labels={},forest_vectors=(((219,205,155),array('d',[0.,0.,1.,0.])),))
  image=NS(source='semantic',projection=object());base=object()
  surface=NS(image=image,renderer=renderer,terrain=True,roads=True,grid_mode='off',
             unavailable_reason='',viewport=lambda:view,features=lambda *a:features,
             overlay_vectors=(),layer=(0,0,4,1,base),key=('forest-off',))
  current=[surface];owner=NS(map_surface=lambda:current[0])
  host=NS(origin=(0,0),window=lambda n:None,bounds=lambda w:(0,0,6,3))
  app=View(host,owner)
  with patch('map_pixels.terrain_detail',return_value=(features.terrain,4,2)) as dense:
   off=app.render_image()[0]
   renderer.forest_roads=True
   current[0]=NS(**{**vars(surface),'key':('forest-on',)})
   on=app.render_image()[0]
   renderer.forest_roads=False
   current[0]=surface
   hidden=app.render_image()[0]
  self.assertEqual(pool.calls,0)
  self.assertEqual(dense.call_count,1)
  self.assertIs(off.base,on.base)
  self.assertIs(off.base,hidden.base)
  self.assertIs(off.forest_overlay,on.forest_overlay)
  self.assertIs(on.forest_overlay,hidden.forest_overlay)
  self.assertEqual((off.forest_visible,on.forest_visible,hidden.forest_visible),(False,True,False))

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
