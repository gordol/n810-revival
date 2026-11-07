# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Room camera/input model with direct native GPU pixels, never cell publication."""
import ctypes as C
import time,math
from app import SurfaceRoom
class PixelRoom(SurfaceRoom):
 def __init__(self,host,library):
  super().__init__(host,asynchronous=False)
  self.lib=C.CDLL(str(library));self.lib.pocket_room_pixels.argtypes=[C.c_float]*5+[C.c_uint,C.c_uint,C.c_void_p,C.c_uint]
  self.lib.pocket_pixels_blit.argtypes=[C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_void_p,C.c_uint]
  self.lib.pocket_room_set_eye_height.argtypes=[C.c_float];self.lib.pocket_room_set_eye_height.restype=C.c_int
  self.eye_height=340.
  self.image=None;self.size=None;self.pixel_dirty=True;self.pixel_jobs=0;self.pixel_frames=0
 def set_eye_height(self,height):
  height=float(height)
  if not math.isfinite(height) or not 0<=height<=20000:raise ValueError('Eye height must be finite and between0 and20000 room units')
  if height!=self.eye_height:self.eye_height=height;self.pixel_dirty=True
 def poll(self,force=False):
  now=self.clock()
  if not self._sync():return
  self._apply_motion(self.held_motion.advance(now),now)
  if force or now>=self.next_poll:self.pixel_dirty=True;self.next_poll=now+1/60
 def render_image(self):
  w=self.host.window(self.name)
  if not self.host.shown(w) or w.rolled:return None
  x,y,width,height=self.host.bounds(w);ox,oy=getattr(self.host,"origin",(0,0));x=(x+ox+1)*8;y=(y+oy+1)*16;width=(width-2)*8;height=(height-2)*16
  if width<=0 or height<=0:return None
  if width>4096 or height>4096:raise ValueError('Direct Room dimensions exceed native framebuffer')
  if self.size!=(width,height):self.image=(C.c_uint16*(width*height))();self.size=(width,height);self.pixel_dirty=True
  if self.pixel_dirty:
   started=time.monotonic_ns();cpu=time.process_time_ns()
   if self.lib.pocket_room_set_eye_height(self.eye_height):raise RuntimeError('Native eye height rejected')
   jobs=self.lib.pocket_room_pixels(self.clock()-self.started-self.paused_total,self.x,self.z,self.yaw,self.pitch,width,height,self.image,400)
   if jobs<0:raise RuntimeError(f'Direct GPU Room failed ({jobs}); no cell fallback')
   self.stats.update(last_pixel_wall_ns=time.monotonic_ns()-started,last_pixel_cpu_ns=time.process_time_ns()-cpu)
   self.pixel_jobs+=jobs;self.pixel_frames+=1;self.pixel_dirty=False
  return self.image,x,y,width,height
 def composite(self,canvas):
  # Standalone compatibility; the Desktop compositor owns window stack blending.
  result=self.render_image()
  if not result:return False
  image,x,y,width,height=result;dst=(C.c_ubyte*len(canvas)).from_buffer(canvas)
  if self.lib.pocket_pixels_blit(dst,image,x,y,width,height,None,0):raise RuntimeError('Native image clipping rejected')
  return True
