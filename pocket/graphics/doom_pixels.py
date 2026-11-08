# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""A graphical view of the existing Doom owner and latest-frame protocol."""
from pathlib import Path
import ctypes as C,importlib.util,time
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('pixel_doom_engine',HERE.parent/'shell/apps/doom-app/doom_app.py')
engine_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine_module)
class Engine(engine_module.DoomApp):
 def __init__(self,*args,**kwargs):
  self.serial=0;super().__init__(*args,**kwargs)
 def configure_bridge(self):
  try:convert=self.lib.convert_pixels
  except AttributeError:raise ValueError('Doom pixel adapter is outdated; run make doom from pocket/') from None
  convert.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t]+[C.c_uint]*6
  convert.restype=C.c_int
 def update(self):
  start=time.perf_counter();ok=self.lib.snapshot(C.byref(self.shared),C.byref(self.frame));self.stats['snapshot_seconds']+=time.perf_counter()-start
  if not ok or not self.frame.number or self.frame.number==self.serial:return None
  self.stats['skipped']+=max(0,self.frame.number-self.serial-1) if self.serial else 0
  self.serial=self.frame.number;self.stats['sampled']+=1
  return self.frame.number,self.frame.ns,self.frame.input
class View:
 input_role='game'
 def __init__(self,host,owner):
  self.host=host;self.owner=owner;self.name=owner.name;self.size=None;self.image=None;self.last_serial=0
  self.pixel_frames=0;self.pixel_jobs=0
  owner.engine_factory=lambda h,state:Engine(h,state,name=owner.name,resource_root=owner.root)
 def _active(self):return self.owner._active()
 @property
 def pixel_dirty(self):
  engine=self.owner.engine
  return bool(engine and engine.serial and (engine.serial!=self.last_serial or self.dimensions()!=self.size))
 @pixel_dirty.setter
 def pixel_dirty(self,value):
  if value:self.last_serial=0
 def dimensions(self):
  _,_,width,height=self.host.bounds(self.host.window(self.name));return (max(1,(width-2)*8),max(1,(height-2)*16))
 def render_image(self):
  engine=self.owner.engine
  if not engine or not engine.serial or self.owner.error:return None
  width,height=self.dimensions()
  if self.size!=(width,height):self.image=(C.c_uint16*(width*height))();self.size=(width,height);self.last_serial=0
  if engine.serial!=self.last_serial:
   x0,y0,w,h=engine_module.fitted_viewport(width,height,1)
   if engine.lib.convert_pixels(C.byref(engine.frame),self.image,len(self.image),width,height,x0,y0,w,h):raise ValueError('Doom native viewport rejected')
   self.last_serial=engine.serial;self.pixel_frames+=1
  x,y,_,_=self.host.bounds(self.host.window(self.name));ox,oy=self.host.origin
  return self.image,(x+ox+1)*8,(y+oy+1)*16,width,height
