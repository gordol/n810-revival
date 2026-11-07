"""Surface Room uses the graphical frontend's one current MBX context."""
import ctypes as C
import struct,time
from core import Cell
class Backend:
 def __init__(self,library):
  self.lib=C.CDLL(str(library));self.lib.pocket_room_render.argtypes=[C.c_void_p,C.c_void_p]
 def supports(self,request,implementation,materials):
  from native_backend import NativeRoomBackend
  return NativeRoomBackend.supports(self,request,implementation,materials)
 def prepare(self,r,implementation,materials):
  from frame_job import resize_cells
  if not self.supports(r,implementation,materials):raise ValueError('Unsupported shared GPU room request')
  started=time.monotonic();request=struct.pack('<III5f',0x31575250,r.width,r.height,r.age,r.x,r.z,r.yaw,r.pitch)
  output=C.create_string_buffer(52+r.width*r.height*12)
  result=self.lib.pocket_room_render(C.c_char_p(request),output)
  if result:raise RuntimeError(f'Shared MBX room rendering failed ({result}); no CPU fallback')
  magic,width,height,count,repairs=struct.unpack_from('<5I',output.raw)
  if (magic,width,height,count)!=(0x31435250,r.width,r.height,r.width*r.height) or repairs>32:raise RuntimeError('Invalid shared GPU room result')
  geometry,materials_ns,cpu,total=struct.unpack_from('<4Q',output.raw,20)
  values=tuple(struct.iter_unpack('<3I',output.raw[52:]))
  if any(char>0x10ffff or 0xd800<=char<=0xdfff or fg>0xffffff or bg>0xffffff for char,fg,bg in values):raise RuntimeError('Invalid shared GPU cells')
  cells=tuple(Cell(chr(char),(1<<48)|(fg<<24)|bg) for char,fg,bg in values)
  return r,resize_cells(cells,width,height,r.body_width,r.body_height),dict(geometry_seconds=geometry/1e9,surface_seconds=materials_ns/1e9,preparation_seconds=time.monotonic()-started,last_scene_backend='mbx-shared',last_native_cpu_ms=cpu/1e6,last_native_wall_ms=total/1e6,last_edge_repairs=repairs)
 def close(self):pass # The frontend retains ownership of the shared GL context.
