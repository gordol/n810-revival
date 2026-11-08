# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native map presentation using the shared camera, worker and semantic overlays.

The terminal model retains geographic selection and input. This adapter strips
road glyphs from its terrain sample plane and draws the source vectors directly.
One outstanding presentation job shares the map's existing bounded executor.
"""
from array import array
import ctypes as C

class Sample(C.Structure):
 _fields_=[('ch',C.c_uint32),('pad',C.c_uint32),('ink',C.c_uint64)]
class Mark(C.Structure):
 _fields_=[('index',C.c_uint32),('ch',C.c_uint32),('ink',C.c_uint64)]

def rgb565(color):
 r,g,b=color;return ((r>>3)<<11)|((g>>2)<<5)|(b>>3)

def segments(engine,view):
 """Yield source geographic segments, preserving the terminal detail policy."""
 from map_geography import covers,data_for_view
 if covers(view):
  data=data_for_view(view)
  for kind,color in (('streams',(55,177,196)),('roads',(219,205,155))):
   points=array('d')
   for item in data.get(kind,()):
    role=item.get('kind');limit={'residential':20,'unclassified':20,'living_street':12,'service':8}.get(role)
    if role=='forest' and not getattr(engine,'forest_roads',False):continue
    if kind=='streams' and view.ground_m_per_halfcell>250 and role!='river':continue
    if limit is not None and view.ground_m_per_halfcell>limit:continue
    if limit is None and view.span>item.get('max_span',100) and kind=='roads':continue
    west,south,east,north=view.bbox;a,b,c,d=item.get('bbox',(-180,-90,180,90))
    if c<west or a>east or d<south or b>north:continue
    for first,last in zip(item['points'],item['points'][1:]):points.extend((*first,*last))
   yield color,points
  return
 if view.ground_m_per_halfcell>6000:return
 atlas=engine.atlas
 west,south,east,north=(round(v*100000) for v in view.bbox)
 for role,layer in [*enumerate(atlas.roads),*(([(2,atlas.streams)]) if atlas.streams else [])]:
  if role==0 and view.ground_m_per_halfcell>=150 or role==2 and view.ground_m_per_halfcell>=250:continue
  extent=engine.layer_bounds.get(id(layer))
  if not extent:continue
  a,b,c,d=max(west,extent[0]),max(south,extent[1]),min(east,extent[2]),min(north,extent[3])
  if a>c or b>d:continue
  ids=set();tile=layer['tile']
  for y in range(b//tile,d//tile+1):
   for x in range(a//tile,c//tile+1):ids.update(layer['index'].get((x,y),()))
  points=array('d');coords=layer['coords']
  for i in sorted(ids):points.extend(value/100000 for value in coords[i*4:i*4+4])
  yield ((55,177,196) if role==2 else (219,205,155)),points

class View:
 input_role='map'
 def __init__(self,host,owner,library,font):
  self.host=host;self.owner=owner;self.base=owner.base;self.name='Station Map';self.font=font;self.lib=C.CDLL(str(library))
  self.lib.pocket_map_base.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p,C.c_uint,C.c_uint]
  self.lib.pocket_map_lines.argtypes=[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_uint]
  self.lib.pocket_map_marks.argtypes=[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_void_p]
  self.pending=None;self.ready=None;self.ready_layer=None;self.key=None;self.failed=None;self.pixel_frames=0;self.pixel_jobs=0;self.error=''
 def plan(self):
  if self.owner.dialog or self.owner.terrain_active or self.base.filter_open:return None
  layer=self.owner.layer();image=getattr(self.base,'_shown_image',None) or getattr(self.base,'_display_image',None)
  if layer is None or image is None or image.projection is None or self.base.renderer.engine is None:return None
  if getattr(self.base.renderer,'provider_selection',None) is not None:return None
  x,y,w,h,plane=layer;projection=image.projection
  key=(id(plane),x,y,w,h,tuple(projection.center),projection.span,getattr(self.base.renderer,'forest_roads',False))
  return key,layer,projection
 @property
 def pixel_dirty(self):
  plan=self.plan()
  return bool(plan and ((self.pending and self.pending[1].done()) or (self.pending is None and plan[0]!=self.key and plan[0]!=self.failed)))
 @pixel_dirty.setter
 def pixel_dirty(self,value):
  if value:self.key=None
 def build(self,layer,projection):
  x,y,w,h,plane=layer;overlay={}
  # Outermost annotations win, including the sidebar and target rectangle.
  while hasattr(plane,'overlay') and hasattr(plane,'base'):
   for i,cell in plane.overlay.items():overlay.setdefault(i,cell)
   plane=plane.base
  samples=(Sample*(w*h))(*(Sample(ord(plane[i][0]),0,plane[i][1]) for i in range(w*h)))
  pixels=(C.c_uint16*(w*8*h*16))();capacity=len(pixels)
  if self.lib.pocket_map_base(pixels,capacity,samples,w,h):raise ValueError('Map terrain dimensions rejected')
  view=self.base.renderer.module.Viewport(projection.center,projection.span,w,h)
  for color,points in segments(self.base.renderer.engine,view):
   projected=array('d')
   for i in range(0,len(points),2):
    px,py=view.project(points[i],points[i+1]);projected.extend(((px+.5)*8,(py+.5)*16))
   if len(projected)//4>250000:raise ValueError('Map vector budget exceeded')
   data=(C.c_double*len(projected)).from_buffer(projected)
   if self.lib.pocket_map_lines(pixels,capacity,w*8,h*16,data,len(projected)//4,rgb565(color)):raise ValueError('Map vectors rejected')
  marks=(Mark*len(overlay))();bits=bytearray()
  for n,(index,(ch,ink)) in enumerate(sorted(overlay.items())):
   marks[n]=Mark(index,ord(ch),ink);bits.extend(self.font.glyph(ch))
  glyphs=(C.c_ubyte*len(bits)).from_buffer(bits)
  if self.lib.pocket_map_marks(pixels,capacity,w,h,marks,len(marks),glyphs):raise ValueError('Map annotations rejected')
  return pixels
 def wake(self,future):
  callback=self.base.renderer.completion_wakeup
  if callback:
   try:callback()
   except (OSError,RuntimeError):pass
 def render_image(self):
  plan=self.plan()
  if plan is None:return None
  key,layer,projection=plan
  if self.pending and self.pending[1].done():
   finished,future,retained_layer=self.pending;self.pending=None
   try:self.ready=future.result();self.key=finished;self.ready_layer=retained_layer;self.pixel_frames+=1;self.error=''
   except Exception as error:self.failed=finished;self.error=str(error)
  if self.pending is None and key!=self.key and key!=self.failed:
   pool=self.base.renderer.pool
   if pool is not None:
    future=pool.submit(self.build,layer,projection);self.pending=key,future,layer;future.add_done_callback(self.wake)
  if self.key!=key:return None
  x,y,w,h=layer[:4];wx,wy,_,_=self.host.bounds(self.host.window(self.name));ox,oy=self.host.origin
  return self.ready,(wx+ox+1+x)*8,(wy+oy+1+y)*16,w*8,h*16
