"""Opt-in native cell worker; the desktop owns GPU/device lifetime separately.

No module loading, display takeover, or implicit renderer selection happens here.
Unsupported requests retain the existing renderer before any worker submission.
"""
import os
import select
import struct
import subprocess
import threading
import time
from core import Cell
from frame_job import resize_cells


class NativeRoomBackend:
    def __init__(self, command, *, env=None, log=None, timeout=90):
        self.command=tuple(map(str,command));self.env=env;self.log=log
        self.timeout=timeout;self.process=None;self.lock=threading.Lock();self.closed=False

    def supports(self, request, implementation, materials):
        from profiles import ROOM
        from surface_renderer import GlyphRenderer
        return (not (request.outdoors or request.portal or request.rift) and
                1<=request.width<=100 and 1<=request.height<=30 and
                type(implementation) is GlyphRenderer and
                (implementation.max_cells,implementation.max_glyphs)==(6000,1600) and materials==ROOM)

    def _read(self, size, deadline):
        result=bytearray()
        while len(result)<size:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not select.select([self.process.stdout],[],[],remaining)[0]:
                raise TimeoutError('Native room completion timed out; worker retained for owner recovery')
            part=os.read(self.process.stdout.fileno(),size-len(result))
            if not part:raise RuntimeError('Native room worker exited before frame completion')
            result.extend(part)
        return result

    def prepare(self, request, implementation, materials):
        if not self.supports(request,implementation,materials):raise ValueError('Unsupported native room request')
        with self.lock:
            if self.closed:raise RuntimeError('Native room backend is closed')
            if self.process is None:
                self.process=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                    stderr=self.log,env=self.env,bufsize=0)
            r=request;started=time.monotonic();deadline=started+self.timeout
            wire=struct.pack('<III5f',0x31575250,r.width,r.height,r.age,r.x,r.z,r.yaw,r.pitch)
            if self.process.stdin.write(wire)!=len(wire):raise RuntimeError('Incomplete native room request')
            magic,width,height,count,repairs=struct.unpack('<5I',self._read(20,deadline))
            if (magic,width,height,count)!=(0x31435250,r.width,r.height,r.width*r.height) or repairs>32:
                raise RuntimeError('Invalid native room completion')
            geometry,materials_ns,cpu,total=struct.unpack('<4Q',self._read(32,deadline))
            values=tuple(struct.iter_unpack('<3I',self._read(count*12,deadline)))
            if any(char>0x10ffff or 0xd800<=char<=0xdfff or fg>0xffffff or bg>0xffffff for char,fg,bg in values):
                raise RuntimeError('Invalid native cell payload')
            cells=tuple(Cell(chr(char),(1<<48)|(fg<<24)|bg) for char,fg,bg in values)
            cells=resize_cells(cells,width,height,r.body_width,r.body_height)
            return r,cells,dict(geometry_seconds=geometry/1e9,surface_seconds=materials_ns/1e9,
                preparation_seconds=time.monotonic()-started,last_scene_backend='mbx-native',
                last_native_cpu_ms=cpu/1e6,last_native_wall_ms=total/1e6,last_edge_repairs=repairs)

    def close(self):
        with self.lock:
            self.closed=True
            if self.process:
                self.process.stdin.close()
                # EOF only: never kill a process that may own active GPU buffers.
                self.process.wait(timeout=self.timeout)
                self.process.stdout.close();self.process=None
