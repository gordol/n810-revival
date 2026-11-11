"""A transient Pocket window consuming retained Symbian GPU images."""
from dataclasses import dataclass
import os,socket,struct
from symbian_window_wire import BEGIN,READY,FRAME,ACK,CLOSE,PAUSE,RESUME,ERROR,MAX_PACKET,packet,decode

@dataclass(frozen=True)
class Frame:
    serial:int
    width:int
    height:int
    images:tuple

class View:
    input_role='game'
    symbian_window=True
    key_event_supported=True
    def __init__(self,host,name,frames,keyboard,control):
        self.host=host;self.name=name;self.frames=frames;self.keyboard=keyboard;self.control=control
        self.frames.setblocking(False);os.set_blocking(keyboard,False)
        self.phase='idle';self.serial=0;self.frame=None;self.error='';self.context=None
        self.pixel_frames=0;self.pixel_jobs=0;self._dirty=True;self.held=set();self.closed=False;self.paused=False;self.pause_requested=False;self.wanted_paused=False
        self.width=30;self.height=20;self.transition_had_image=False
    def readiness_sources(self):return () if self.closed else ((self.frames,self.receive),(self.control,self.receive_control))
    def receive_control(self):
        message=self.control.recv(16)
        if message.startswith(b'E') and len(message)==5:
            result=struct.unpack('<i',message[1:])[0]
            self.readiness_error(RuntimeError('Symbian application exited (status '+str(result)+')'))
        elif not message:self.readiness_error(RuntimeError('Symbian window broker stopped'))
        else:raise ValueError('Invalid window broker status')
    def readiness_error(self,error):
        self.error=str(error);self.close();self.host.invalidate(self.host.bounds(self.host.window(self.name)))
    def _send(self,kind,serial=None):
        self.frames.sendall(packet(kind,self.serial if serial is None else serial))
    def receive(self):
        for _ in range(8):
            try:data,_,flags,_=self.frames.recvmsg(MAX_PACKET)
            except BlockingIOError:return
            if not data:self.readiness_error(RuntimeError('Symbian application stopped'));return
            if flags&socket.MSG_TRUNC:raise ValueError('Oversized GPU window message')
            kind,serial,width,height,images=decode(data)
            if kind==BEGIN:
                if self.phase not in ('idle','displayed') or serial<=self.serial:raise ValueError('Out-of-order GPU window begin')
                self.serial=serial;self.phase='begin';self.transition_had_image=self.frame is not None
            elif kind==FRAME:
                if self.phase!='receiving' or serial!=self.serial:raise ValueError('Unrequested GPU window frame')
                self.frame=Frame(serial,width,height,images);self.phase='ready'
            elif kind==PAUSE:
                if serial!=self.serial:raise ValueError('Stale GPU window pause')
                if self.wanted_paused:
                    self.control.sendall(b'S');self.paused=True
                else:self._send(RESUME,0);self.pause_requested=False
            elif kind==CLOSE:
                if self.context:self.context.retire_retained(self.name)
                self.control.sendall(b'F')
                self._send(READY);self.close(notify=False)
                self.host.close(self.name);return
            elif kind==ERROR:
                self.readiness_error(RuntimeError('Symbian renderer stopped'));return
            else:raise ValueError('Unexpected producer message')
            self._dirty=True;self.host.invalidate(self.host.bounds(self.host.window(self.name)))
    def prepare_gpu(self,context):
        self.context=context
        if self.phase=='begin':
            context.retire_retained(self.name,keep=True);self.frame=None
            self._send(READY);self.phase='receiving'
        if self.phase=='ready' and self.wanted_paused:
            self._send(ACK);self.phase='displayed';self._dirty=False
        return self.phase!='receiving' or self.paused or not self.transition_had_image
    @property
    def pixel_dirty(self):return self._dirty
    @pixel_dirty.setter
    def pixel_dirty(self,value):self._dirty=bool(value)
    def render_retained(self):
        if self.frame is None:return None
        x,y,w,h=self.host.bounds(self.host.window(self.name));ox,oy=self.host.origin
        return self.frame,(x+ox+1)*8,(y+oy+1)*16,max(1,(w-2)*8),max(1,(h-2)*16)
    def frame_presented(self):
        if self.phase=='ready':
            self._send(ACK);self.phase='displayed';self.pixel_frames+=1;self.pixel_jobs+=len(self.frame.images)
        self._dirty=False
    def poll(self):
        if self.closed:return
        window=self.host.window(self.name)
        self.wanted_paused=not self.host.shown(window) or window.rolled
        if self.wanted_paused and not self.pause_requested:
            self.cancel_keys();self._send(PAUSE,0);self.pause_requested=True
        elif not self.wanted_paused and self.paused:
            self.control.sendall(b'R');self._send(RESUME,0);self.paused=False;self.pause_requested=False
    def poll_interval(self):return None
    def lines(self):return (self.error,) if self.error else (() if self.frame else ('Starting Symbian…',))
    def _key(self,key,value):
        codes={'up':103,'down':108,'left':105,'right':106,'enter':28,'\r':28,'\n':28,'esc':1,'\x1b':1,'f1':59,'f2':60,'menu':139,' ':57,'\x7f':14}
        code=codes.get(key)
        if code is None and key in '1234567890' and len(key)==1:code=11 if key=='0' else int(key)+1
        if code is None or self.closed:return False
        # ARM input_event has two 32-bit timeval fields, independent of host ABI.
        try:
            if os.write(self.keyboard,struct.pack('<iiHHi',0,0,1,code,value))!=16:raise OSError('Short keyboard write')
        except OSError as error:
            self.held.clear();self.readiness_error(RuntimeError('Symbian input connection failed: '+str(error)));return False
        return True
    def key_event(self,key,phase,now=None):
        if phase not in ('press','repeat','release'):return False
        # WSERV owns key repetition. Host repeats would become new key-downs
        # and arm duplicate guest timers that a single release cannot cancel.
        if phase=='repeat':return True
        if self._key(key,{'press':1,'repeat':2,'release':0}[phase]):
            if phase=='release':self.held.discard(key)
            else:self.held.add(key)
            return True
        return False
    def key(self,key):
        if self._key(key,1):self._key(key,0);return True
        return False
    def cancel_keys(self,now=None):
        for key in tuple(self.held):self._key(key,0)
        self.held.clear()
    def close(self,notify=True):
        if self.closed:return
        self.cancel_keys()
        # Forget imports before allowing the producer to retire its publications.
        if self.context:self.context.retire_retained(self.name)
        try:self.control.sendall(b'C' if notify else b'F')
        except OSError:pass
        self.closed=True;self.frame=None;self.phase='closed';self._dirty=True
        self.frames.close();self.control.close();os.close(self.keyboard)
