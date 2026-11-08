"""Doom lifecycle adapter. Shared runtime owns menus, scheduling, focus and Help."""
from pathlib import Path
import importlib.util
import os
import signal
import tempfile
import time

NAME='Doom / Freedoom'

class DesktopDoom:
    """Lazy owner; close() is final shutdown, on_close() pauses the window.

    open/key/poll/poll_interval/close match the existing lifetime-owner pattern.
    on_close/on_focus/on_visibility are cheap optional lifecycle notifications.
    poll_interval also reconciles Host lifecycle so an existing generic scheduler
    can adopt this owner without Doom-specific notifications or draw callbacks.
    """
    def __init__(self,host,*,root=None,engine_factory=None,clock=time.monotonic):
        self.host=host;self.name=NAME;self.root=Path(root) if root else Path(__file__).parent
        self.engine_factory=engine_factory;self.clock=clock
        self.engine=None;self.temporary=None;self.closed=False;self.paused=False;self.active=False
        self.layer_only=True
        self.error='';self.next_poll=0;self.last_frame=None;self.width=80;self.height=25
        self.view=self
    def _dependencies(self):
        if self.engine_factory:return
        required=('build/doom-engine','build/bridge.so','vendor/freedoom-0.13.0/freedoom1.wad')
        missing=[item for item in required if not (self.root/item).is_file()]
        if missing:raise OSError('Missing Doom components: '+', '.join(missing))
        if not os.access(self.root/'build/doom-engine',os.X_OK):raise OSError('Doom engine is not executable')
    def _factory(self):
        if self.engine_factory:return self.engine_factory
        path=Path(__file__).with_name('doom_app.py');spec=importlib.util.spec_from_file_location('_current_world_doom_engine',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return lambda host,state:module.DoomApp(host,state,name=self.name,resource_root=self.root)
    def _error(self,error):
        self.error=str(error)[:1000];self._dispose();self.last_frame=None
        self.host.content(self.name,('doom-error',self.error),self.lines(),layer=None)
    def open(self):
        if self.closed:return False
        self.active=True;self.host.activate(self.name)
        if self.engine is None:
            try:
                self._dependencies();factory=self._factory()
                self.temporary=tempfile.TemporaryDirectory(prefix='cw-doom-desktop-')
                self.engine=factory(self.host,Path(self.temporary.name));self.error=''
                self.host.content(self.name,'doom-starting',('Starting Freedoom…',),layer=None)
            except (OSError,ImportError,RuntimeError,ValueError,AttributeError) as error:
                self._error(error);return False
        self.next_poll=0;self._sync();return True
    def _active(self):
        w=self.host.window(self.name)
        return self.active and self.host.shown(w) and not w.rolled and self.host.focus==self.name
    def _sync(self):
        if not self.engine:return False
        active=self._active()
        if active and self.paused:
            try:self.engine.child.send_signal(signal.SIGCONT)
            except ProcessLookupError:pass
            self.paused=False;self.next_poll=0
        elif not active and not self.paused:
            if self.engine.child.poll() is None:self.cancel_keys()
            try:self.engine.child.send_signal(signal.SIGSTOP)
            except ProcessLookupError:pass
            self.paused=True
        return active
    def on_close(self):
        """Host already changed opened/visible state; keep the game for reopen."""
        self.set_active(False)
    def on_focus(self,*_):self._sync()
    def on_visibility(self,*_):self._sync()
    def cancel_keys(self,now=None):
        if self.engine:self.engine.release(self.clock() if now is None else now,True)
    def key_event(self,key,kind,now):
        if self.closed or not self._sync() or self.engine.child.poll() is not None:return False
        return self.engine.key_event(key,kind,now)
    def key(self,key,now=None):
        if self.closed or not self._active():return False
        if key in ('?','help'):return False # Shared contextual Help handles this.
        if self.engine is None:
            if key.lower()=='r':self.open();return True
            return False
        if self.engine.child.poll() is not None:return False
        self._sync();self.engine.key(key,self.clock() if now is None else now);return True
    def poll_interval(self):
        return 1/35 if not self.closed and self._sync() else None
    def poll(self,*,force=False):
        if self.closed or not self._sync():return
        now=self.clock()
        if not force and now<self.next_poll:return
        self.next_poll=now+1/35
        if self.engine.child.poll() is not None:
            try:detail=(Path(self.temporary.name)/'engine.log').read_text(errors='replace')[-700:]
            except OSError:detail=''
            self._error('Doom engine stopped. '+detail);return
        self.engine.release(now)
        if not self.host.damage:self.last_frame=self.engine.update()
    def presented(self,now=None):
        if self.engine and self.last_frame and not self.host.damage:
            self.engine.presented(self.last_frame,self.clock() if now is None else now);self.last_frame=None
    @property
    def layer(self):return self.host.window(self.name).layer
    def lines(self):
        if not self.error:return ()
        return ('Doom could not start.',*tuple(self.error[i:i+max(20,self.width)] for i in range(0,len(self.error),max(20,self.width))),
                '', 'Prepare: make doom (from pocket/)','R: retry   ?: game and window help')
    def spans(self):return ()
    def _dispose(self):
        if self.engine:
            if self.paused:
                try:self.engine.child.send_signal(signal.SIGCONT)
                except ProcessLookupError:pass
            self.engine.close();self.engine=None;self.paused=False
        if self.temporary:self.temporary.cleanup();self.temporary=None
    def set_active(self,opened):
        self.active=bool(opened) and not self.closed
        self._sync()
    def close(self):
        """Final desktop-lifetime teardown, exactly once."""
        if self.closed:return
        self.closed=True;self.active=False;self._dispose()

    shutdown=close # Optional spelling; existing desktop calls close() once at exit.
