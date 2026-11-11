# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Publish engine-owned map scenes to the active native render context.

Input, source selection, and annotation meaning belong to the shared model.
"""
from array import array
import ctypes as C

class Mark(C.Structure):
 _fields_=[('index',C.c_uint32),('ch',C.c_uint32),('ink',C.c_uint64)]

def rgb565(color):
 r,g,b=color;return ((r>>3)<<11)|((g>>2)<<5)|(b>>3)

class View:
 input_role='map'
 def __init__(self,host,owner,*,name='Station Map'):
  self.host=host;self.owner=owner;self.name=name
  self.pending=None;self.ready=None;self.ready_layer=None;self.key=None;self.failed=None;self.pixel_frames=0;self.pixel_jobs=0;self.error=''
 def plan(self):
  surface=self.owner.map_surface()
  if surface is None:return None
  layer=surface.layer;x,y,w,h,plane=layer
  projection=surface.image.projection
  key=surface.key
  return key,layer,surface
 @property
 def pixel_dirty(self):
  plan=self.plan()
  return bool(plan and ((self.pending and self.pending[1].done()) or (self.pending is None and plan[0]!=self.key and plan[0]!=self.failed)))
 @pixel_dirty.setter
 def pixel_dirty(self,value):
  if value:self.key=None
 def build(self,layer,surface):
  from scenes import MapScene
  x,y,w,h,plane=layer;overlay={}
  while hasattr(plane,'overlay') and hasattr(plane,'base'):
   for i,cell in plane.overlay.items():overlay.setdefault(i,cell)
   plane=plane.base
  view=surface.viewport()
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
  for i,cell in features.labels.items():overlay.setdefault(i,cell)
  marks=(Mark*len(overlay))(*(Mark(i,ord(ch),ink) for i,(ch,ink) in sorted(overlay.items())))
  scene=MapScene(w,h,features.terrain,features.sample_width,features.sample_height,tuple(projected),marks)
  prepare=getattr(getattr(self.host,'render_context',None),'prepare_scene',None)
  return prepare(scene) if prepare is not None else scene
 def wake(self,future,callback):
  if callback:
   try:callback()
   except (OSError,RuntimeError):pass
 def render_image(self):
  plan=self.plan()
  if plan is None:return None
  key,layer,surface=plan
  if self.pending and self.pending[1].done():
   finished,future,retained_layer=self.pending;self.pending=None
   try:self.ready=future.result();self.key=finished;self.ready_layer=retained_layer;self.pixel_frames+=1;self.error=''
   except Exception as error:self.failed=finished;self.error=str(error)
  if self.pending and self.pending[2][:4]!=layer[:4]:
   self.pending[1].cancel();self.pending=None
  if self.pending is None and key!=self.key and key!=self.failed:
   pool=surface.renderer.pool
   if self.ready is None or self.ready_layer[:4]!=layer[:4] or pool is None:
    try:
     self.ready=self.build(layer,surface);self.key=key;self.ready_layer=layer;self.pixel_frames+=1;self.error=''
    except Exception as error:self.failed=key;self.error=str(error)
   else:
    future=pool.submit(self.build,layer,surface);self.pending=key,future,layer;future.add_done_callback(lambda f,callback=surface.renderer.completion_wakeup:self.wake(f,callback))
  if self.ready is None or self.ready_layer[:4]!=layer[:4]:return None
  x,y,w,h=layer[:4];wx,wy,_,_=self.host.bounds(self.host.window(self.name));ox,oy=self.host.origin
  return self.ready,(wx+ox+1+x)*8,(wy+oy+1+y)*16,w*8,h*16

 def presentation_marks(self):
  plan=self.plan()
  if self.ready is None or plan is None or self.ready_layer[:4]!=plan[1][:4]:return None
  x,y,w,h=self.ready_layer[:4];wx,wy,_,_=self.host.bounds(self.host.window(self.name));ox,oy=self.host.origin
  return self.ready.marks,wx+ox+1+x,wy+oy+1+y,w,h
