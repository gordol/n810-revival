# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Publish engine-owned map scenes to the active native render context.

Input, source selection, and annotation meaning belong to the shared model.
"""
from array import array
from concurrent.futures import ThreadPoolExecutor
import ctypes as C
import math
from dataclasses import replace
from scenes import MapScene

class Mark(C.Structure):
 _fields_=[('index',C.c_uint32),('ch',C.c_uint32),('ink',C.c_uint64)]

_surround_pool=None
def surround_pool():
 global _surround_pool
 if _surround_pool is None:_surround_pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='map-surround')
 return _surround_pool

def rgb565(color):
 r,g,b=color;return ((r>>3)<<11)|((g>>2)<<5)|(b>>3)

def place_labels(labels,overlay,width,height):
 """Keep a place name intact when station marks cover part of its row."""
 runs=[];previous=-2;style=None
 for index,cell in sorted(labels.items()):
  if runs and index==previous+1 and index//width==previous//width and cell[1]==style:
   runs[-1].append((index,cell))
  else:runs.append([(index,cell)])
  previous=index;style=cell[1]
 occupied=set(labels)|set(overlay);placed={}
 for run in runs:
  original={index for index,_ in run};occupied.difference_update(original-set(overlay))
  x=run[0][0]%width;y=run[0][0]//width
  for dx,dy in ((0,0),(0,-1),(0,1),(-1,0),(1,0),(0,-2),(0,2)):
   nx,ny=x+dx,y+dy
   if nx<0 or ny<0 or ny>=height or nx+len(run)>width:continue
   indices=[ny*width+nx+n for n in range(len(run))]
   if any(index in occupied for index in indices):continue
   placed.update((index,cell) for index,(_,cell) in zip(indices,run))
   occupied.update(indices)
   break
 return placed

def surround_camera(projection,content_width,height):
 """Match the map pane's scale and center before extending its coverage."""
 x,y=(content_width-1)/2,(height-1)/2
 if callable(getattr(projection,'unproject',None)):
  center=projection.unproject(x,y)
 else:
  lat,lon=projection.center
  step=projection.span/max(1,projection.width-1)/111.32
  center=(lat-(y-(projection.height-1)/2)*step*projection.cell_aspect,
          lon+(x-(projection.width-1)/2)*step/max(.000001,math.cos(math.radians(lat))))
 span=projection.span*(2*content_width-1)/max(1,projection.width-1)
 return tuple(center),span

def terrain_detail(surface,view,features):
 """Sample the desktop DEM beyond character-cell resolution for native maps."""
 from desktop_elevation import enabled
 if (not enabled() or not getattr(surface,'terrain',False) or
     getattr(surface.image,'source',None)!='semantic'):
  return features.terrain,features.sample_width,features.sample_height
 # Limit one render to 262,144 terrain cells (524,288 half-cell samples).
 factor=min(8,math.isqrt(262144//max(1,view.width*view.height)))
 if factor<2:return features.terrain,features.sample_width,features.sample_height
 dense=surface.renderer.module.Viewport(view.center,view.span,view.width*factor,
                                       view.height*factor,view.cell_aspect)
 from desktop_elevation import pixel_samples
 fast=pixel_samples(surface.renderer.engine,dense)
 if fast is not None:return fast
 frame,_=surface.renderer.engine._rgb_terrain(dense,True)
 from offline_map import map_rgb
 samples=array('I')
 for row in range(dense.height):
  cells=frame[row*dense.width:(row+1)*dense.width]
  samples.extend(map_rgb(upper) for _,upper,_ in cells)
  samples.extend(map_rgb(lower) for _,_,lower in cells)
 return samples,dense.width,dense.height*2

class View:
 input_role='map'
 def __init__(self,host,owner,*,name='Station Map',_builder=False):
  self.host=host;self.owner=owner;self.name=name
  self.pending=None;self.ready=None;self.ready_layer=None;self.ready_surface=None;self.key=None;self.failed=None;self.pixel_frames=0;self.pixel_jobs=0;self.error=''
  self._terrain_key=None;self._terrain_samples=None
  self._features_key=None;self._features=None;self._projected_vectors=()
  self._forest_scene=None
  self._base_key=None;self._base_scene=None
  self._presented_pan=None
  self._surround_key=None;self._surround_future=None;self._surround_image=None;self._surround_scene=None;self.surround_error=''
  self._locator_builder=None if _builder else View(host,owner,name=name,_builder=True)
 def plan(self):
  surface=self.owner.map_surface()
  if surface is None:return None
  layer=surface.layer;x,y,w,h,plane=layer
  projection=surface.image.projection
  key=surface.key
  return key,layer,surface
 @property
 def pixel_dirty(self):
  if self._surround_future is not None and self._surround_future.done():return True
  pan=self.pan_offset()
  if pan is not None and pan!=self._presented_pan:return True
  plan=self.plan()
  return bool(plan and ((self.pending and self.pending[1].done()) or (self.pending is None and plan[0]!=self.key and plan[0]!=self.failed)))
 @pixel_dirty.setter
 def pixel_dirty(self,value):
  if value:self.key=None
 def build(self,layer,surface):
  from scenes import MapScene
  x,y,w,h,plane=layer;overlay={}
  while hasattr(plane,'overlay') and hasattr(plane,'base'):
   if plane is not getattr(surface,'box_plane',None):
    for i,cell in plane.overlay.items():overlay.setdefault(i,cell)
   plane=plane.base
  view=surface.viewport()
  content_width=min(w,max(1,getattr(surface,'content_width',0) or w))
  if surface.unavailable_reason:
   message=surface.unavailable_reason[:w]
   marks=(Mark*len(message))(*(Mark(i,ord(ch),(1<<48)|(0xffffff<<24)) for i,ch in enumerate(message)))
   return MapScene(w,h,array('I',[0]*(w*h*2)),w,h*2,(),marks)
  try:view_key=tuple(view)
  except TypeError:view_key=id(view)
  renderer=getattr(surface,'renderer',None)
  feature_key=(id(getattr(surface,'image',surface)),view_key,id(renderer),
               id(getattr(renderer,'engine',None)),getattr(surface,'terrain',True),
               getattr(surface,'roads',True),getattr(surface,'grid_mode','off'))
  if feature_key!=self._features_key:
   self._features=surface.features(view,plane)
   projected=[]
   for color,points in self._features.vectors:
    pixels=array('d')
    for i in range(0,len(points),2):
     px,py=view.project(points[i],points[i+1]);pixels.extend(((px+.5)*8,(py+.5)*16))
    if len(pixels)//4>250000:raise ValueError('Map vector budget exceeded')
    projected.append((color,pixels))
   self._projected_vectors=tuple(projected)
   forest=[]
   for color,points in getattr(self._features,'forest_vectors',()):
    pixels=array('d')
    for i in range(0,len(points),2):
     px,py=view.project(points[i],points[i+1]);pixels.extend(((px+.5)*8,(py+.5)*16))
    if len(pixels)//4>250000:raise ValueError('Map forest vector budget exceeded')
    if pixels:forest.append((color,pixels))
   empty=(Mark*0)()
   self._forest_scene=(MapScene(w,h,self._features.terrain,self._features.sample_width,
                      self._features.sample_height,(),empty,(),None,empty,tuple(forest))
                       if forest else None)
   self._features_key=feature_key
  features=self._features
  projected=list(self._projected_vectors)
  for color,points in surface.overlay_vectors:
   pixels=array('d')
   for i in range(0,len(points),2):
    px,py=view.project(points[i],points[i+1]);pixels.extend(((px+.5)*8,(py+.5)*16))
   if len(pixels)//4>250000:raise ValueError('Map vector budget exceeded')
   projected.append((color,pixels))
  if content_width<w:overlay={i:cell for i,cell in overlay.items() if i%w<content_width}
  labels=features.labels if getattr(surface,'labels',True) else {}
  if content_width<w:labels={i:cell for i,cell in labels.items() if i%w<content_width}
  labels=place_labels(labels,overlay,w,h)
  combined=dict(labels);combined.update(overlay)
  marks=(Mark*len(combined))(*(Mark(i,ord(ch),ink) for i,(ch,ink) in sorted(combined.items())))
  dynamic_marks=(Mark*len(overlay))(*(Mark(i,ord(ch),ink) for i,(ch,ink) in sorted(overlay.items())))
  terrain_key=(id(getattr(surface,'image',surface)),view_key,getattr(surface,'terrain',True),id(getattr(renderer,'engine',None)))
  if terrain_key!=self._terrain_key:
   self._terrain_samples=terrain_detail(surface,view,features)
   self._terrain_key=terrain_key
  terrain,sample_width,sample_height=self._terrain_samples
  base_key=(feature_key,terrain_key)
  if base_key!=self._base_key:
   self._base_scene=MapScene(w,h,terrain,sample_width,sample_height,self._projected_vectors,(Mark*0)())
   self._base_key=base_key
  insets=()
  inset_plan=getattr(surface,'inset',None)
  if inset_plan is not None and self._locator_builder is not None:
   locator,offset_x,offset_y=inset_plan
   inset=self._locator_builder.build(locator.layer,locator)
   insets=((inset,offset_x*8,offset_y*16),)
  drag_labels=MapScene(w,h,terrain,sample_width,sample_height,(),marks,(),None,marks) if len(marks) else None
  scene=MapScene(w,h,terrain,sample_width,sample_height,tuple(projected),marks,insets,
                 self._base_scene,marks,tuple(projected[len(self._projected_vectors):]),
                 self._forest_scene,bool(getattr(renderer,'forest_roads',False)),drag_labels,
                 content_width*8)
  return scene
 def wake(self,future,callback):
  if callback:
   try:callback()
   except (OSError,RuntimeError):pass
 def static_key(self,surface):
  inset=getattr(surface,'inset',None)
  locator=inset[0] if inset else None
  renderer=getattr(surface,'renderer',None)
  return (id(getattr(surface,'image',None)),id(renderer),getattr(surface,'grid_mode','off'),
          getattr(surface,'terrain',True),getattr(surface,'roads',True),
          id(getattr(locator,'image',None)),getattr(locator,'grid_mode','off'))
 def pan_offset(self):
  base=getattr(self.owner,'base',None)
  if base is None or getattr(self.owner,'terrain_active',False):return None
  return getattr(base,'_gpu_pan_offset',None)
 def positioned(self,scene,layer,pan=None):
  x,y,w,h=layer[:4];wx,wy,_,_=self.host.bounds(self.host.window(self.name));ox,oy=self.host.origin
  self._presented_pan=pan
  result=(scene,(wx+ox+1+x)*8,(wy+oy+1+y)*16,w*8,h*16)
  return (*result,*pan) if pan is not None else result
 def prepare_surround(self,renderer,center,span,width,height,source_pixel_metres,roads,detail_factor):
  from offline_map import map_rgb
  from desktop_elevation import enabled,pixel_samples
  # The backdrop covers twice the visible pane in each direction. Sample at
  # least one column per displayed cell so its coastline stays recognizable.
  coarse_width=(min(512,width*2,1+255*max(1,width-1)//max(1,height-1))
                if enabled() else min(128,max(40,width//2)))
  coarse_width=max(2,coarse_width)
  coarse_height=(min(256,height*2) if enabled() else
                 max(8,round((coarse_width-1)*max(1,height-1)/max(1,width-1))+1))
  view=renderer.module.Viewport(center,span,coarse_width,coarse_height)
  lines=[]
  if enabled():
   from map_geography import vector_segments
   for color,points in vector_segments(renderer.engine,view,roads=roads,detail_pixels=8,
                                       forest_roads=False):
    pixels=array('d')
    for i in range(0,len(points),2):
     px,py=view.project(points[i],points[i+1]);pixels.extend(((px+.5)*8,(py+.5)*16))
    if len(pixels)//4>250000:raise ValueError('Map backdrop vector budget exceeded')
    lines.append((color,pixels))
  detail_view=(renderer.module.Viewport(center,span,coarse_width*detail_factor,
                                       coarse_height*detail_factor)
               if enabled() and detail_factor>=2 else view)
  fast=pixel_samples(renderer.engine,detail_view,source_pixel_metres=source_pixel_metres)
  if fast is not None:
   samples,sample_width,sample_height=fast
   return MapScene(coarse_width,coarse_height,samples,sample_width,sample_height,tuple(lines),(Mark*0)(),smooth=False)
  frame,_=renderer.engine._rgb_terrain(view,True)
  samples=array('I')
  for row in range(coarse_height):
   cells=frame[row*coarse_width:(row+1)*coarse_width]
   samples.extend(map_rgb(upper) for _,upper,_ in cells)
   samples.extend(map_rgb(lower) for _,_,lower in cells)
  return MapScene(coarse_width,coarse_height,samples,coarse_width,coarse_height*2,tuple(lines),(Mark*0)(),smooth=True)
 def schedule_surround(self,surface):
  renderer=surface.renderer;image=getattr(surface,'image',None);projection=getattr(image,'projection',None)
  if (getattr(surface,'unavailable_reason','') or getattr(image,'source',None)!='semantic' or projection is None or
      not callable(getattr(getattr(renderer,'engine',None),'_rgb_terrain',None)) or
      renderer.pool is None):return
  view=surface.viewport()
  content_width=min(surface.layer[2],getattr(surface,'content_width',0) or surface.layer[2])
  key=(id(image),content_width,surface.layer[3])
  if key==self._surround_key:return
  if self._surround_future is not None:self._surround_future.cancel()
  self._surround_key=key;self._surround_image=image
  self._surround_scene=None
  center,span=surround_camera(view,content_width,surface.layer[3])
  factor=min(8,math.isqrt(262144//max(1,view.width*view.height)))
  detail_width=view.width*factor if factor>=2 else view.width
  source_pixel_metres=view.span*1000/max(1,detail_width-1)*min(1,view.cell_aspect/2)
  from desktop_elevation import enabled
  pool=surround_pool() if enabled() else renderer.pool
  self._surround_future=pool.submit(self.prepare_surround,renderer,
      center,span,content_width,surface.layer[3],source_pixel_metres,surface.roads,factor)
  self._surround_future.add_done_callback(lambda f,callback=renderer.completion_wakeup:self.wake(f,callback))
 def adopt_surround(self):
  future=self._surround_future
  if future is None or not future.done():return
  self._surround_future=None
  try:surround=future.result()
  except Exception as error:self.surround_error=str(error);return
  self._surround_scene=surround
  if self.ready is not None and self.ready_surface is not None and self.ready_surface.image is self._surround_image:
   self.ready=replace(self.ready,surround=surround)
 def render_image(self):
  self.adopt_surround()
  pan=self.pan_offset()
  base=getattr(self.owner,'base',None)
  if (pan is not None and self.ready is not None and self.ready_layer is not None and
      (getattr(base,'_target_drag',None) is not None or getattr(base,'_pan_drag',None) is not None or
       getattr(base,'_image_view',None)!=(tuple(base.center),base.span))):
   return self.positioned(self.ready,self.ready_layer,pan)
  plan=self.plan()
  if plan is None:return None
  key,layer,surface=plan
  self.schedule_surround(surface)
  if self.pending and self.pending[1].done():
   finished,future,retained_layer,finished_surface=self.pending;self.pending=None
   try:self.ready=future.result();self.key=finished;self.ready_layer=retained_layer;self.ready_surface=finished_surface;self.pixel_frames+=1;self.error=''
   except Exception as error:self.failed=finished;self.error=str(error)
  if self.pending and self.pending[2][:4]!=layer[:4]:
   self.pending[1].cancel();self.pending=None
  if self.pending is None and key!=self.key and key!=self.failed:
   pool=surface.renderer.pool
   same_static=(self.ready_surface is not None and isinstance(self.ready,MapScene) and self.ready.base is not None
                and self.static_key(self.ready_surface)==self.static_key(surface))
   if self.ready is None or self.ready_layer[:4]!=layer[:4] or pool is None or same_static:
    try:
     self.ready=self.build(layer,surface);self.key=key;self.ready_layer=layer;self.ready_surface=surface;self.pixel_frames+=1;self.error=''
    except Exception as error:self.failed=key;self.error=str(error)
   else:
    future=pool.submit(self.build,layer,surface);self.pending=key,future,layer,surface;future.add_done_callback(lambda f,callback=surface.renderer.completion_wakeup:self.wake(f,callback))
  if self.ready is None or self.ready_layer[:4]!=layer[:4]:return None
  if (self._surround_scene is not None and self.ready_surface is not None and
      self.ready_surface.image is self._surround_image and self.ready.surround is not self._surround_scene):
   self.ready=replace(self.ready,surround=self._surround_scene)
  if pan is not None and self.ready_surface is not None and self.ready_surface.image is not surface.image:
   return self.positioned(self.ready,self.ready_layer,pan)
  if pan is not None:base._gpu_pan_offset=None
  return self.positioned(self.ready,self.ready_layer)

 def presentation_marks(self):
  if self.pan_offset() is not None:return None
  plan=self.plan()
  if self.ready is None or plan is None or self.ready_layer[:4]!=plan[1][:4]:return None
  x,y,w,h=self.ready_layer[:4];wx,wy,_,_=self.host.bounds(self.host.window(self.name));ox,oy=self.host.origin
  return self.ready.marks,wx+ox+1+x,wy+oy+1+y,w,h
