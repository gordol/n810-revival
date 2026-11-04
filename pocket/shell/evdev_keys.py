"""Bounded Linux EV_KEY source for one explicitly selected hardware keyboard.

Importing opens nothing.  Runtime selects/enables the source and owns selector
registration, focus routing, cancellation and TTY deduplication.  The pure byte
decoder is separately testable.  No discovery, grabbing or keyboard-mode changes.
"""
import fcntl
import os
import struct
import sys

EV_SYN,EV_KEY=0,1
SYN_REPORT,SYN_DROPPED=0,3
MOTION_KEYS={17:'w',30:'a',31:'s',32:'d',23:'i',37:'k',
             103:'up',108:'down',105:'left',106:'right'}
MODIFIER_KEYS={29,97,56,100,125,126,42,54} # Ctrl, Alt, Meta, Shift


class KeyDecoder:
    def __init__(self,word_bytes=4,*,initial_down=()):
        if type(word_bytes) is not int or word_bytes not in (4,8):
            raise ValueError('Linux input_event word size must be 4 or 8')
        self.codec=struct.Struct('=iiHHi' if word_bytes==4 else '=qqHHi')
        self.pending=b'';self.down=set();self.suppressed=set();self.dropping=False
        self.resync(initial_down)

    def resync(self,currently_down):
        """Use the owner's EVIOCGKEY snapshot; held keys await release/repress."""
        keys=set(currently_down)
        if any(type(k) is not int or not 0<=k<=767 for k in keys):
            raise ValueError('invalid kernel key snapshot')
        self.pending=b''
        self.suppressed=keys&MOTION_KEYS.keys();self.modifiers=keys&MODIFIER_KEYS;self.down.clear();self.dropping=False

    def cancel_motion(self):
        """Ownership was lost: held motion must release before it can restart."""
        self.suppressed.update(self.down)
        self.down.clear()

    def feed(self,data):
        if type(data) is not bytes or len(data)>self.codec.size*256:
            raise ValueError('hardware input chunk must be at most 256 records')
        self.pending+=data;events=[];position=0
        while len(self.pending)-position>=self.codec.size:
            _,_,kind,code,value=self.codec.unpack_from(self.pending,position)
            position+=self.codec.size
            if kind==EV_SYN and code==SYN_DROPPED:
                self.down.clear();self.suppressed.clear();self.modifiers.clear();self.dropping=True
                events.append(('key_cancel',));continue
            if self.dropping:
                if kind==EV_SYN and code==SYN_REPORT:
                    # The snapshot must describe current state, rather than
                    # replaying records that may predate the owner's ioctl.
                    self.pending=b'';events.append(('key_resync',));return events
                continue
            if kind!=EV_KEY or value not in (0,1,2):continue
            if code in MODIFIER_KEYS:
                if value==0:self.modifiers.discard(code)
                elif code not in self.modifiers:
                    self.modifiers.add(code);self.suppressed.update(self.down);self.down.clear()
                    events.append(('key_cancel',))
                continue
            if code not in MOTION_KEYS:continue
            if self.modifiers:
                if value:self.suppressed.add(code)
                else:self.suppressed.discard(code)
                continue
            if code in self.suppressed:
                if value==0:self.suppressed.remove(code)
                continue
            if value==0:
                if code in self.down:
                    self.down.remove(code);events.append(('key_event',MOTION_KEYS[code],'release'))
            elif value==1:
                phase='repeat' if code in self.down else 'press'
                self.down.add(code);events.append(('key_event',MOTION_KEYS[code],phase))
            elif code in self.down:events.append(('key_event',MOTION_KEYS[code],'repeat'))
        self.pending=self.pending[position:];return events


def _read_ioctl(fd,number,size):
    data=bytearray(size)
    fcntl.ioctl(fd,(2<<30)|(size<<16)|(ord('E')<<8)|number,data,True)
    return data


def inspect_keyboard(fd):
    """Selected identity, key capabilities/state ioctls; no sysfs traversal."""
    if not sys.platform.startswith('linux'):raise OSError('hardware keyboard ioctls require Linux')
    name=bytes(_read_ioctl(fd,0x06,256)).split(b'\0',1)[0].decode('utf-8','replace')
    identity=list(struct.unpack('=4H',_read_ioctl(fd,0x02,8)))
    capabilities=_read_ioctl(fd,0x21,96) # EVIOCGBIT(EV_KEY)
    supported={k for k in MOTION_KEYS if capabilities[k//8]&(1<<(k%8))}
    if not {17,30,31,32}<=supported:raise ValueError('keyboard lacks WASD motion keys')
    pressed=_read_ioctl(fd,0x18,96) # EVIOCGKEY
    down={k for k in supported|MODIFIER_KEYS if pressed[k//8]&(1<<(k%8))}
    return dict(name=name,id=identity,motion_codes=sorted(supported)),down


class KeyboardSource:
    """One explicit nonblocking fd. Runtime retains all focus/TTY ownership.

    fd/query/word_bytes allow local pipe fixtures without opening a keyboard.
    Production opens only the caller-provided device path and validates it.
    """
    def __init__(self,path=None,*,fd=None,query=inspect_keyboard,word_bytes=None):
        self.fd=None;self.query=query
        try:
            self.fd=os.open(os.fspath(path),os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC) if fd is None else os.dup(fd)
            os.set_blocking(self.fd,False)
            self.device,down=query(self.fd)
            self.decoder=KeyDecoder(struct.calcsize('l') if word_bytes is None else word_bytes,initial_down=down)
        except BaseException:self.close();raise

    def fileno(self):
        if self.fd is None:raise ValueError('keyboard fd is closed')
        return self.fd

    def close(self):
        if self.fd is not None:
            fd,self.fd=self.fd,None
            try:os.close(fd)
            except OSError:pass

    def drain(self):
        if self.fd is None:raise OSError('keyboard fd is closed')
        try:raw=os.read(self.fd,self.decoder.codec.size*256)
        except BlockingIOError:return []
        if not raw:raise OSError('keyboard disconnected')
        events=self.decoder.feed(raw);result=[]
        for event in events:
            if event==('key_resync',):
                device,down=self.query(self.fd)
                if device!=self.device:raise OSError('keyboard identity changed during resync')
                self.decoder.resync(down)
            else:result.append(event)
        return result
