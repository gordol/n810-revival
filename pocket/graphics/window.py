"""SDL presentation and input only. No app, terminal, or driver lifecycle."""
import ctypes as C
class Window:
 def __init__(self,path,fd=-1):
  self.width=800;self.height=480
  self.lib=C.CDLL(str(path))
  self.lib.pocket_window_open.argtypes=[C.c_int]
  self.lib.pocket_window_open.restype=C.c_void_p
  self.lib.pocket_window_error.restype=C.c_char_p
  self.lib.pocket_window_present.argtypes=[C.c_void_p,C.c_void_p]
  self.lib.pocket_window_close.argtypes=[C.c_void_p]
  self.lib.pocket_window_event.argtypes=[C.POINTER(C.c_int)]
  self.handle=self.lib.pocket_window_open(fd)
  if not self.handle:raise RuntimeError(self.lib.pocket_window_error().decode())
 def present(self,frame):
  if len(frame)!=getattr(self,'width',800)*getattr(self,'height',480)*2:raise ValueError('Expected800x480RGB565')
  buffer=C.c_char_p(frame) if isinstance(frame,bytes) else (C.c_ubyte*len(frame)).from_buffer(frame)
  if self.lib.pocket_window_present(self.handle,buffer):raise RuntimeError(self.lib.pocket_window_error().decode())
 def events(self):
  event=(C.c_int*6)()
  while self.lib.pocket_window_event(event):
   kind,x,y,button,up,repeat=event
   if kind==1:yield dict(action='quit')
   elif kind==2:yield dict(action='pointer',x=max(0,min(self.width-1,x)),y=max(0,min(self.height-1,y)),button=button,released=bool(up))
   elif kind==3 and not repeat:
    if x in (27,13,9,8):yield dict(action='key',key=chr(127 if x==8 else x),released=bool(up))
    elif x==1073741883 and not up:yield dict(action='open',app='surface-room') # F2
    elif x in (1073741904,1073741903,1073741906,1073741905):yield dict(action='key',key={1073741904:'left',1073741903:'right',1073741906:'up',1073741905:'down'}[x],released=bool(up))
    elif 32<=x<127:yield dict(action='key',key=chr(x),released=bool(up))
   elif kind==4:yield dict(action='redraw')
   elif kind==5:
    self.width=x*8;self.height=y*16
    yield dict(action='resize',columns=x,rows=y)
 def close(self):
  if self.handle:
   if self.lib.pocket_window_close(self.handle):raise RuntimeError(self.lib.pocket_window_error().decode())
   self.handle=None
