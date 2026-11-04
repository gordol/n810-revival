"""Attach optional app-owned readiness to the desktop's existing selector."""
from collections import namedtuple
import selectors
import weakref


class AppReady(namedtuple('AppReady','reference error_reference listeners',defaults=(None,(),))):
    __slots__=()
    reference:object
    error_reference:object
    listeners:tuple
    @classmethod
    def bind(cls,callback,on_error=None):
        reference=weakref.WeakMethod(callback) if getattr(callback,'__self__',None) is not None else weakref.ref(callback)
        return cls(reference,weakref.WeakMethod(on_error) if on_error is not None else None)
    def callback(self):
        if self.listeners:
            for listener in self.listeners: listener.callback()
            return
        method=self.reference()
        if method is not None:
            try:method()
            except Exception as error:
                handler=self.error_reference() if self.error_reference is not None else None
                if handler is None:raise
                handler(error)


class AppReadiness:
    def __init__(self, selector):
        self.selector = selector
        self.sources = {}

    def sync(self, forms):
        wanted = {}
        for form in forms:
            method = getattr(form, 'readiness_sources', None)
            if method is None:
                continue
            sources = tuple(method())
            if len(sources) > 8:
                raise ValueError('Too many application readiness sources')
            for source, callback in sources:
                fd = source if isinstance(source, int) else source.fileno()
                if type(fd) is not int or fd < 0 or not callable(callback):
                    raise ValueError('Invalid application readiness source')
                listener = (callback,getattr(form,'readiness_error',None))
                if fd in wanted:
                    previous_source, listeners = wanted[fd]
                    if previous_source is not source:
                        raise ValueError('Different application sources share a descriptor')
                    listeners.append(listener)
                else:
                    wanted[fd] = (source, [listener])
        for fd,(source,listeners) in wanted.items():
            old=self.sources.get(fd)
            previous=(old[1].listeners or (old[1],)) if old is not None and old[0] is source else ()
            # Resolve existing weak references for comparison. Rebuilding them
            # every drawing pass is costly on the N810 and changes no ownership.
            if len(previous)==len(listeners) and all(
                ready.reference()==callback and
                (ready.error_reference() if ready.error_reference is not None else None)==on_error
                for ready,(callback,on_error) in zip(previous,listeners)):
                ready=old[1]
            else:
                bound=tuple(AppReady.bind(callback,on_error) for callback,on_error in listeners)
                ready=bound[0] if len(bound)==1 else AppReady(None,listeners=bound)
            wanted[fd]=(source,ready)
        for fd, old in tuple(self.sources.items()):
            # A bare integer cannot identify a kernel-handle lifetime. Re-arm
            # it conservatively; stable file objects retain their registration.
            if fd not in wanted or wanted[fd] != old or isinstance(wanted[fd][0],int):
                try:
                    self.selector.unregister(fd)
                except (KeyError, OSError):
                    pass
                del self.sources[fd]
        for fd, (source, ready) in wanted.items():
            if fd not in self.sources:
                self.selector.register(source, selectors.EVENT_READ, ready)
                self.sources[fd] = (source, ready)

    def rearm_integers(self):
        # A cached lifecycle pass still cannot establish an integer descriptor's
        # kernel identity. Preserve conservative rearming without rescanning apps.
        for source,ready in self.sources.values():
            if isinstance(source,int):
                try:self.selector.unregister(source)
                except (KeyError,OSError):pass
                self.selector.register(source,selectors.EVENT_READ,ready)

    def close(self):
        self.sync(())
