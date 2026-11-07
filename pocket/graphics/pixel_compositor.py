"""Native source-over pixel composition. Python handles window plans, not pixels."""
import ctypes as C
from array import array
import time,os
class Compositor:
 def __init__(self,host,renderer,library):
  self.host=host;self.renderer=renderer;self.lib=C.CDLL(str(library));self.cache={};self.coverage=(C.c_ubyte*384000)();self.builds=0;self.frames=0;self.metrics={};self.outline=None;self.gpu_cache={};self.gpu_key=None
  self.lib.pocket_room_gpu_layers.argtypes=[C.c_void_p,C.c_void_p,C.c_uint]
  self.lib.pocket_pixel_layer_with_shadow.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_uint];self.lib.pocket_pixel_layer_with_shadow.restype=C.c_void_p
  self.lib.pocket_pixel_canvas_size.argtypes=[C.c_uint,C.c_uint]
  self.lib.pocket_pixel_layer_new.argtypes=[C.c_uint,C.c_uint];self.lib.pocket_pixel_layer_new.restype=C.c_void_p
  self.lib.pocket_pixel_layer_free.argtypes=[C.c_void_p]
  self.lib.pocket_pixel_layer_build.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p,C.c_uint,C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_uint]
  self.lib.pocket_pixel_layer_over.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint]
  self.lib.pocket_pixel_image.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_uint,C.c_uint]
  self.lib.pocket_pixel_layer_outline.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint,C.c_uint]
 def layer(self,w):
  h=self.host;r=self.renderer;native=h._native
  if native is None:raise RuntimeError('Native window planes required')
  prior=native.planes.get(w.name)
  if prior is None:raise RuntimeError('Native window plane was not prepared')
  signature,plane=prior[:2];cols,rows=signature[:2]
  return self.cached_plane(w.name,signature,plane,cols,rows,int(h.window_fill),round(h.window_opacity*255))
 def cached_plane(self,name,signature,plane,cols,rows,fill,opacity):
  h=self.host;r=self.renderer;native=h._native
  key=(signature,r.layer_key,r.layer_fallback,fill,opacity)
  cached=self.cache.get(name)
  if cached and cached[0]==key:return cached[1]
  handle=self.lib.pocket_pixel_layer_new(cols,rows)
  if not handle:raise MemoryError('Native pixel layer allocation failed')
  try:
   records=native.lib.export_cells(plane.pointer,array('I',range(cols*rows)))
   if self.lib.pocket_pixel_layer_build(handle,C.c_char_p(records),len(records),r.font_codes,r.font_bits,len(r.font_codes),r.layer_palette,len(r.layer_palette),r.layer_fallback,fill,opacity):
    raise ValueError('Native text pixel layer rejected')
  except Exception:
   self.lib.pocket_pixel_layer_free(handle);raise
  if cached:self.lib.pocket_pixel_layer_free(cached[1])
  self.cache[name]=(key,handle);self.builds+=1
  return handle
 def gpu_compose(self,canvas,apps):
  # Explicit local candidate. MBX admission remains guarded in native code.
  h=self.host
  if os.environ.get('POCKET_GPU_COMPOSE')!='1' or len(apps)!=1 or h.launcher_lines or h.drag:return False
  app=apps[0];seen=False;handles=[];positions=[];keys=[];active=set()
  rx,ry,_,_=h.bounds(h.window(app.name));ox,oy=getattr(h,'origin',(0,0));rx=(rx+ox+1)*8;ry=(ry+oy+1)*16
  dx,dy={'SE':(1,1),'S':(0,1),'SW':(-1,1),'W':(-1,0),'NW':(-1,-1),'N':(0,-1),'NE':(1,-1),'E':(1,0)}[h.shadow_direction]
  dx=round(dx*h.shadow_size*8) if h.shadow_enabled else 0;dy=round(dy*h.shadow_size*16) if h.shadow_enabled else 0;alpha=round(h.shadow_opacity*255) if h.shadow_enabled else 0
  for w in h.windows:
   if w.name==app.name:seen=True;continue
   if not seen or not h.shown(w):continue
   layer=self.layer(w);key=(self.cache[w.name][0],dx,dy,alpha);cached=self.gpu_cache.get(w.name)
   if cached is None or cached[0]!=key:
    merged=self.lib.pocket_pixel_layer_with_shadow(layer,dx,dy,alpha)
    if not merged:return False
    if cached:self.lib.pocket_pixel_layer_free(cached[1])
    self.gpu_cache[w.name]=(key,merged);cached=self.gpu_cache[w.name]
   active.add(w.name);handles.append(cached[1]);x,y,_,_=h.bounds(w);positions.extend(((x+ox)*8+min(0,dx)-rx,(y+oy)*16+min(0,dy)-ry));keys.append((w.name,key,x,y))
  for name in set(self.gpu_cache)-active:self.lib.pocket_pixel_layer_free(self.gpu_cache.pop(name)[1])
  if not handles or len(handles)>32:return False
  key=(app.name,tuple(keys),rx,ry)
  if self.lib.pocket_room_gpu_layers((C.c_void_p*len(handles))(*handles),(C.c_int*len(positions))(*positions),len(handles)):return False
  try:
   if self.gpu_key!=key:app.pixel_dirty=True
   result=app.render_image()
  finally:self.lib.pocket_room_gpu_layers(None,None,0)
  self.gpu_key=key
  if result:
   image,x,y,w,height=result;dst=(C.c_ubyte*len(canvas)).from_buffer(canvas)
   if self.lib.pocket_pixel_image(dst,self.coverage,image,x,y,w,height):raise ValueError('GPU composite image insertion rejected')
  for name in set(self.gpu_cache)-active:self.lib.pocket_pixel_layer_free(self.gpu_cache.pop(name)[1])
  self.metrics={'gpu_composed_layers':len(handles),'layer_cpu_ns':0,'image_cpu_ns':0};self.frames+=1
  return True
 def compose(self,canvas,apps):
  cols,rows=self.renderer.size;count=cols*8*rows*16
  if len(canvas)!=count*2:raise ValueError('Canvas dimensions mismatch')
  if self.lib.pocket_pixel_canvas_size(cols*8,rows*16):raise ValueError('Native canvas size rejected')
  if len(self.coverage)!=count:self.coverage=(C.c_ubyte*count)()
  h=self.host;dst=(C.c_ubyte*len(canvas)).from_buffer(canvas);C.memset(self.coverage,0,count)
  if self.gpu_compose(canvas,apps):return
  if self.gpu_key:
   for app in apps:app.pixel_dirty=True
   self.gpu_key=None
  by_name={app.name:app for app in apps};covered=False;active=set();self.metrics={'layer_cpu_ns':0,'image_cpu_ns':0}
  dx,dy={'SE':(1,1),'S':(0,1),'SW':(-1,1),'W':(-1,0),'NW':(-1,-1),'N':(0,-1),'NE':(1,-1),'E':(1,0)}[h.shadow_direction]
  for w in h.windows:
   if not h.shown(w):continue
   x,y,width,height=h.bounds(w);ox,oy=getattr(h,"origin",(0,0));x+=ox;y+=oy
   if covered:
    active.add(w.name)
    start=time.process_time_ns();layer=self.layer(w)
    if self.lib.pocket_pixel_layer_over(dst,self.coverage,layer,x*8,y*16,round(dx*h.shadow_size*8),round(dy*h.shadow_size*16),round(h.shadow_opacity*255) if h.shadow_enabled else 0):raise ValueError('Native window composition rejected')
    self.metrics['layer_cpu_ns']+=time.process_time_ns()-start
   app=by_name.get(w.name)
   if app is not None:
    result=app.render_image()
    if result:
     image,px,py,pw,ph=result;start=time.process_time_ns()
     if self.lib.pocket_pixel_image(dst,self.coverage,image,px,py,pw,ph):raise ValueError('Native image composition rejected')
     self.metrics['image_cpu_ns']+=time.process_time_ns()-start;covered=True
  if covered and h.launcher_lines:
   overlay=h._native.overlays.get('launcher')
   if overlay is None:raise RuntimeError('Native launcher plane was not prepared')
   cols,rows,plane,signature=overlay;name=('overlay','launcher');active.add(name)
   handle=self.cached_plane(name,signature,plane,cols,rows,1,255);x,y,_,_=h.launcher_bounds();ox,oy=getattr(h,'origin',(0,0));x+=ox;y+=oy
   if self.lib.pocket_pixel_layer_over(dst,self.coverage,handle,x*8,y*16,0,0,0):raise ValueError('Native launcher composition rejected')
  outline=h._native.outline_layer if covered else None
  if outline is not None:
   geometry=h._native.outline_plane[0];cols,rows,glyphs=geometry;color=int(self.renderer.layer_palette[3])&65535
   key=(geometry,color)
   if self.outline is None or self.outline[0]!=key:
    handle=self.lib.pocket_pixel_layer_new(cols,rows)
    if not handle:raise MemoryError('Native outline allocation failed')
    codes=(C.c_uint32*6)(*glyphs)
    if self.lib.pocket_pixel_layer_outline(handle,codes,self.renderer.font_codes,self.renderer.font_bits,len(self.renderer.font_codes),color):
     self.lib.pocket_pixel_layer_free(handle);raise ValueError('Native outline rejected')
    if self.outline:self.lib.pocket_pixel_layer_free(self.outline[1])
    self.outline=(key,handle)
   _,x,y=outline;ox,oy=getattr(h,"origin",(0,0));x+=ox;y+=oy
   if self.lib.pocket_pixel_layer_over(dst,self.coverage,self.outline[1],x*8,y*16,0,0,0):raise ValueError('Native outline composition rejected')
  elif self.outline:self.lib.pocket_pixel_layer_free(self.outline[1]);self.outline=None
  for name in set(self.cache)-active:self.lib.pocket_pixel_layer_free(self.cache.pop(name)[1])
  self.frames+=1
 def close(self):
  for _,handle in self.gpu_cache.values():self.lib.pocket_pixel_layer_free(handle)
  self.gpu_cache.clear()
  for _,handle in self.cache.values():self.lib.pocket_pixel_layer_free(handle)
  self.cache.clear()
  if self.outline:self.lib.pocket_pixel_layer_free(self.outline[1]);self.outline=None
