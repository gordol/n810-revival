"""Focus ownership for an optional explicit hardware motion-key source."""
import time


def take_keyboard(path=None,fd=None):
    """Consume a CLI-owned inherited fd; source owns only its private duplicate."""
    import os
    from evdev_keys import KeyboardSource
    if fd is not None and (type(fd) is not int or not 3<=fd<=65535):
        raise ValueError('inherited keyboard descriptor must be in 3..65535')
    try:return KeyboardSource(path,fd=fd)
    finally:
        if fd is not None:
            try:os.close(fd)
            except OSError:pass


def console_foreground(fd):
    """Read-only Linux VT check; fail closed for SSH/PTYS and unknown owners."""
    import os,sys,fcntl
    from array import array
    if not sys.platform.startswith('linux'):return False
    try:
        device=os.fstat(fd).st_rdev
        if os.major(device)!=4 or not 1<=os.minor(device)<=63:return False
        state=array('H',[0,0,0]);fcntl.ioctl(fd,0x5603,state,True) # VT_GETSTATE
        return state[0]==os.minor(device)
    except (OSError,ValueError):return False


class KeyboardRouter:
    def __init__(self,source,clock=time.monotonic,foreground=lambda:True):
        from evdev_keys import MOTION_KEYS
        self.source=source;self.clock=clock;self.target=None;self.foreground=foreground
        from collections import deque
        self.history=deque(maxlen=128);self.last_foreground=False;self.held=set()
        self.keys={MOTION_KEYS[code] for code in source.device['motion_codes'] if code in MOTION_KEYS}

    def select(self,form):
        capable=(form is not None and getattr(form,'key_event_supported',True)
                 and callable(getattr(form,'key_event',None)) and callable(getattr(form,'cancel_keys',None)))
        self._check_foreground()
        target=form if self.source is not None and capable and self.last_foreground else None
        if target is not self.target:
            self.cancel();self.target=target

    def _check_foreground(self):
        try:self.last_foreground=bool(self.foreground())
        except Exception:self.last_foreground=False
        if not self.last_foreground:self.cancel()
        return self.last_foreground

    def safety_interval(self):
        """No idle VT polling. Recheck only while routed motion can continue.

        This fallback requires no VT_PROCESS change or blocking ioctl thread.
        select() revalidates ownership on every real input/main-loop turn.
        """
        return .1 if self.source is not None and self.target is not None and self.held else None

    def cancel(self):
        target,self.target=self.target,None
        self.held.clear()
        decoder=getattr(self.source,'decoder',None)
        if target is not None and callable(getattr(decoder,'cancel_motion',None)):
            decoder.cancel_motion()
        if target is not None:
            target.cancel_keys(self.clock());self.history.append(dict(time=self.clock(),kind='cancel'))

    def event(self,event):
        if event[0]=='key_cancel':self.cancel();return True
        if event[0]!='key_event':return False
        self._check_foreground()
        routed=False
        if self.target is not None:
            key,phase=event[1:3]
            if phase=='press':self.held.add(key)
            elif phase=='release':self.held.discard(key)
            if phase!='repeat' or key in self.held:
                self.target.key_event(key,phase,self.clock());routed=True
        self.history.append(dict(time=self.clock(),key=event[1],kind=event[2],routed=routed))
        return True

    def suppress_tty(self,key):
        self._check_foreground()
        modified=bool(getattr(getattr(self.source,'decoder',None),'modifiers',()))
        return self.source is not None and self.target is not None and not modified and key in self.keys

    def status(self):
        decoder=getattr(self.source,'decoder',None)
        def keys(name):
            values=getattr(decoder,name,())
            if not isinstance(values,(set,list,tuple)):return []
            return sorted(str(v) for v in values)
        return dict(foreground=self.last_foreground,target=type(self.target).__name__ if self.target is not None else None,
                    device=getattr(self.source,'device',None),down=keys('down'),suppressed=keys('suppressed'),
                    modifiers=keys('modifiers'),events=list(self.history))

    def close(self):
        self.cancel()
        if self.source is not None:self.source.close();self.source=None
