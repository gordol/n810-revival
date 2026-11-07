# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Mac key and relative-pointer adapter for the shared exploration actions."""
import ctypes as C
from window import Window as BaseWindow
KEYS={1073741904:'left',1073741903:'right',1073741906:'up',1073741905:'down',
      1073742049:'shift-left',1073742053:'shift-right',32:'space'}
class Window(BaseWindow):
    captured=False
    canvas_size=(800,480)
    def set_canvas(self,width,height):
        self.lib.pocket_window_canvas.argtypes=[C.c_void_p,C.c_uint,C.c_uint]
        if self.lib.pocket_window_canvas(self.handle,width,height):raise RuntimeError(self.lib.pocket_window_error().decode())
        self.canvas_size=(width,height)
    def dynamic(self,enabled=True):
        self.lib.pocket_window_dynamic.argtypes=[C.c_void_p,C.c_int]
        self.lib.pocket_window_dynamic(self.handle,int(enabled))
    def size(self):
        out=(C.c_int*2)();self.lib.pocket_window_size.argtypes=[C.c_void_p,C.c_void_p]
        if self.lib.pocket_window_size(self.handle,out):raise RuntimeError('Mac window size unavailable')
        return tuple(out)
    def present(self,frame):
        if len(frame)!=self.canvas_size[0]*self.canvas_size[1]*2:raise ValueError('Frame does not match current desktop canvas')
        buf=(C.c_ubyte*len(frame)).from_buffer(frame) if isinstance(frame,bytearray) else C.c_char_p(frame)
        if self.lib.pocket_window_present(self.handle,buf):raise RuntimeError(self.lib.pocket_window_error().decode())
    def capture(self,enabled):
        self.lib.pocket_window_capture.argtypes=[C.c_void_p,C.c_int]
        if self.lib.pocket_window_capture(self.handle,int(enabled)):
            raise RuntimeError(self.lib.pocket_window_error().decode())
        self.captured=enabled
    def events(self):
        raw=(C.c_int*6)()
        while self.lib.pocket_window_event(raw):
            kind,x,y,button,up,repeat=raw
            if kind==1:yield {'action':'quit'}
            elif kind==6:
                self.captured=False;yield {'action':'cancel-input'}
            elif kind==5:yield dict(action='look',dx=x,dy=y)
            elif kind==2:yield dict(action='pointer',x=max(0,min(self.canvas_size[0]-1,x)),y=max(0,min(self.canvas_size[1]-1,y)),button=button,released=bool(up))
            elif kind==3 and not repeat:
                if x==27 and not up:
                    if self.captured:self.capture(False);yield {'action':'cancel-input'}
                    else:yield {'action':'quit'}
                elif x==1073741883 and not up:yield dict(action='open',app='surface-room')
                elif x in KEYS or 33<=x<127:yield dict(action='key',key=KEYS.get(x,chr(x) if x<127 else ''),released=bool(up))
            elif kind==8:yield dict(action='resize',width=x,height=y)
            elif kind==4:yield {'action':'redraw'}
    def close(self):
        if self.handle and self.captured:self.capture(False)
        super().close()
