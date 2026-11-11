# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Publish engine-owned map scenes to the active native render context.

Input, source selection, and annotation meaning belong to the shared model.
"""
from array import array
import ctypes as C
import math

class Mark(C.Structure):
 _fields_=[('index',C.c_uint32),('ch',C.c_uint32),('ink',C.c_uint64)]

def rgb565(color):
 r,g,b=color;return ((r>>3)<<11)|((g>>2)<<5)|(b>>3)

def place_labels(labels,overlay,width,height):
 """Move a complete place-name run clear of station and path marks."""
 runs=[];previous=-2;style=None
 for index,cell in sorted(labels.items()):
  if runs and index==previous+1 and index//width==previous//width and cell[1]==style:runs[-1].append((index,cell))
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
   placed.update((index,cell) for index,(_,cell) in zip(indices,run));occupied.update(indices);break
 return placed

def terrain_detail(surface,view,features):
 """Sample terrain at semantic pixel density, within a fixed work budget."""
 if not getattr(surface,'terrain',False) or getattr(surface.image,'source',None) not in ('semantic','pan-preview'):
  return features.terrain,features.sample_width,features.sample_height
 from desktop_elevation import enabled
 if not enabled():
  return features.terrain,features.sample_width,features.sample_height
 factor=min(8,math.isqrt(262144//max(1,view.width*view.height)))
 if factor<2:return features.terrain,features.sample_width,features.sample_height
 dense=surface.renderer.module.Viewport(view.center,view.span,view.width*factor,view.height*factor,view.cell_aspect)
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

def surround_camera(projection,content_width,height):
 """Extend the current pane around its visible center at matching scale."""
 x,y=(content_width-1)/2,(height-1)/2
 lat,lon=projection.center
 step=projection.span/max(1,projection.width-1)/111.32
 center=(lat-(y-(projection.height-1)/2)*step*projection.cell_aspect,
         lon+(x-(projection.width-1)/2)*step/max(.000001,math.cos(math.radians(lat))))
 span=projection.span*(3*content_width-1)/max(1,projection.width-1)
 return tuple(center),span

class View:
 input_role='map'
 def __init__(self,host,owner,*,name='Station Map'):
  self.host=host;self.owner=owner;self.name=name
  self.pending=None;self.ready=None;self.ready_layer=None;self.key=None;self.failed=None;self.pixel_frames=0;self.pixel_jobs=0;self.error=''
  self.ready_surface=None;self._presented_pan=None
  self._surround_key=None;self._surround_future=None;self._surround_scene=None;self.surround_error=''
  self._inset_key=None;self._inset_scene=None
  self._terrain_key=None;self._terrain_samples=None
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
  features=surface.features(view,plane)
  projected=[]
  for color,points in (*features.vectors,*surface.overlay_vectors):
   pixels=array('d')
   for i in range(0,len(points),2):
    px,py=view.project(points[i],points[i+1]);pixels.extend(((px+.5)*8,(py+.5)*16))
   if len(pixels)//4>250000:raise ValueError('Map vector budget exceeded')
   projected.append((color,pixels))
  if content_width<w:
   overlay={i:cell for i,cell in overlay.items() if i%w<content_width}
  labels={i:cell for i,cell in features.labels.items() if i%w<content_width}
  labels=place_labels(labels,overlay,w,h)
  combined=dict(labels);combined.update(overlay)
  marks=(Mark*len(combined))(*(Mark(i,ord(ch),style) for i,(ch,style) in sorted(combined.items())))
  terrain_key=(id(getattr(surface,'image',surface)),getattr(view,'center',None),
               getattr(view,'span',None),w,h,bool(getattr(surface,'terrain',True)))
  if terrain_key!=self._terrain_key:
   self._terrain_samples=terrain_detail(surface,view,features);self._terrain_key=terrain_key
  terrain,sample_width,sample_height=self._terrain_samples
  scene=MapScene(w,h,terrain,sample_width,sample_height,tuple(projected),marks)
  prepare=getattr(getattr(self.host,'render_context',None),'prepare_scene',None)
  return prepare(scene) if prepare is not None else scene

 def pan_offset(self):
  base=getattr(self.owner,'base',None)
  if base is None or getattr(self.owner,'terrain_active',False):return None
  return getattr(base,'_gpu_pan_offset',None)

 def prepare_surround(self,renderer,center,span,width,height,roads):
  from scenes import MapScene
  from map_geography import vector_segments
  from offline_map import map_rgb
  view=renderer.module.Viewport(center,span,width,height)
  frame,_=renderer.engine._rgb_terrain(view,True)
  terrain=array('I')
  for row in range(height):
   cells=frame[row*width:(row+1)*width]
   terrain.extend(map_rgb(upper) for _,upper,_ in cells)
   terrain.extend(map_rgb(lower) for _,_,lower in cells)
  lines=[]
  for color,points in vector_segments(renderer.engine,view,roads=roads,detail_pixels=8,forest_roads=False):
   pixels=array('d')
   for i in range(0,len(points),2):
    px,py=view.project(points[i],points[i+1]);pixels.extend(((px+.5)*8,(py+.5)*16))
   if len(pixels)//4>250000:raise ValueError('Map surround vector budget exceeded')
   lines.append((color,pixels))
  scene=MapScene(width,height,terrain,width,height*2,tuple(lines),(Mark*0)())
  prepare=getattr(getattr(self.host,'render_context',None),'prepare_scene',None)
  return prepare(scene) if prepare is not None else scene

 def schedule_surround(self,surface):
  image=getattr(surface,'image',None);projection=getattr(image,'projection',None)
  if getattr(getattr(self.host,'render_context',None),'backend',None)=='framebuffer':return
  if (image is None or getattr(surface,'unavailable_reason','') or getattr(image,'source',None)!='semantic' or projection is None or
      not callable(getattr(getattr(getattr(surface,'renderer',None),'engine',None),'_rgb_terrain',None))):return
  if self.ready is None or self.ready_surface is not None and self.ready_surface.image is not image:return
  pool=getattr(surface.renderer,'pool',None)
  if pool is None or getattr(surface.renderer,'pending',None):return
  layer=surface.layer;content_width=min(layer[2],getattr(surface,'content_width',0) or layer[2])
  key=(id(image),content_width,layer[3],surface.roads)
  if key==self._surround_key:return
  if self._surround_future is not None:self._surround_future.cancel()
  center,span=surround_camera(projection,content_width,layer[3])
  self._surround_key=key;self._surround_scene=None
  self._surround_future=pool.submit(self.prepare_surround,surface.renderer,center,span,
      max(2,content_width*3),max(2,layer[3]*3),surface.roads)
  callback=surface.renderer.completion_wakeup
  self._surround_future.add_done_callback(lambda f,callback=callback:self.wake(f,callback))

 def adopt_surround(self):
  future=self._surround_future
  if future is None or not future.done():return
  self._surround_future=None
  try:self._surround_scene=future.result();self.surround_error=''
  except Exception as error:self.surround_error=str(error)

 def positioned(self,source,layer,surface,pan=None):
  x,y,w,h=layer[:4];wx,wy,_,_=self.host.bounds(self.host.window(self.name));ox,oy=self.host.origin
  content_width=min(w,max(1,getattr(surface,'content_width',0) or w))
  from scenes import MapScene
  if not isinstance(source,MapScene):pan=None;content_width=w
  inset=self.inset_scene(surface)
  if pan is not None and self._surround_scene is None:pan=None
  if pan is not None or content_width<w or inset is not None:
   from scenes import MapComposite
   layers=[]
   clip=(0,0,content_width*8,h*16)
   if pan is not None:layers.append((self._surround_scene,-content_width*8,-h*16,*clip))
   layers.append((source,*(pan or (0,0)),*clip))
   if inset is not None:
    scene,ix,iy,iw,ih=inset
    layers.append((scene,ix*8,iy*16,ix*8,iy*16,iw*8,ih*16))
   self._presented_pan=pan
   return MapComposite(tuple(layers),w*8,h*16),(wx+ox+1+x)*8,(wy+oy+1+y)*16,w*8,h*16
  self._presented_pan=pan
  return source,(wx+ox+1+x)*8,(wy+oy+1+y)*16,w*8,h*16

 def inset_scene(self,surface):
  inset=getattr(surface,'inset',None)
  if inset is None:return None
  locator,ix,iy=inset;key=locator.key
  if key!=self._inset_key:
   try:self._inset_scene=self.build(locator.layer,locator);self._inset_key=key
   except Exception as error:self.error=str(error);self._inset_scene=None;self._inset_key=key
  if self._inset_scene is None:return None
  return self._inset_scene,ix,iy,locator.layer[2],locator.layer[3]
 def wake(self,future,callback):
  if callback:
   try:callback()
   except (OSError,RuntimeError):pass
 def render_image(self):
  self.adopt_surround()
  pan=self.pan_offset();base=getattr(self.owner,'base',None)
  dragging=bool(base is not None and (getattr(base,'_target_drag',None) is not None or
                                      getattr(base,'_pan_drag',None) is not None))
  plan=self.plan()
  if plan is None:return None
  key,layer,surface=plan
  self.schedule_surround(surface)
  if self.pending and self.pending[1].done():
   finished,future,retained_layer,retained_surface=self.pending;self.pending=None
   try:self.ready=future.result();self.key=finished;self.ready_layer=retained_layer;self.ready_surface=retained_surface;self.pixel_frames+=1;self.error=''
   except Exception as error:self.failed=finished;self.error=str(error)
  if self.pending and self.pending[2][:4]!=layer[:4]:
   self.pending[1].cancel();self.pending=None
  if not dragging and self.pending is None and key!=self.key and key!=self.failed:
   pool=surface.renderer.pool
   if self.ready is None or self.ready_layer[:4]!=layer[:4] or pool is None:
    try:
     self.ready=self.build(layer,surface);self.key=key;self.ready_layer=layer;self.ready_surface=surface;self.pixel_frames+=1;self.error=''
    except Exception as error:self.failed=key;self.error=str(error)
   else:
    future=pool.submit(self.build,layer,surface);self.pending=key,future,layer,surface;future.add_done_callback(lambda f,callback=surface.renderer.completion_wakeup:self.wake(f,callback))
  if self.ready is None or self.ready_layer[:4]!=layer[:4]:return None
  projection=getattr(getattr(surface,'image',None),'projection',None)
  view_matches=(base is None or projection is not None and
                tuple(projection.center)==tuple(base.center) and abs(projection.span-base.span)<1e-9)
  if not dragging and pan is not None and self.ready_surface is not None and self.ready_surface.image is surface.image and view_matches:
   base._gpu_pan_offset=None;pan=None
  return self.positioned(self.ready,layer,surface,pan)

 def presentation_marks(self):
  if self.pan_offset() is not None:return None
  plan=self.plan()
  if self.ready is None or plan is None or not hasattr(self.ready,'marks') or self.ready_layer[:4]!=plan[1][:4]:return None
  x,y,w,h=self.ready_layer[:4];wx,wy,_,_=self.host.bounds(self.host.window(self.name));ox,oy=self.host.origin
  return self.ready.marks,wx+ox+1+x,wy+oy+1+y,w,h
