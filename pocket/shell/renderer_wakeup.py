"""Reuse the desktop inbox for renderer completion; no new worker or transport."""


def bind_completion_wakeup(renderer,inbox):
    if 'completion_wakeup' not in getattr(renderer,'__dict__',{}):return False
    def completed():
        if callable(getattr(inbox,'notify',None)):
            inbox.notify('all');return
        try:inbox.writable.send(b'm')
        except OSError:pass  # Full inbox already wakes selector; closed inbox is shutdown.
    renderer.completion_wakeup=completed
    return True


def needs_completion_poll(renderers):
    return any(renderer.pending and not callable(getattr(renderer,'completion_wakeup',None))
               for renderer in renderers)


class FutureWakeups:
    """Watch existing owned Futures once; completion only signals the Inbox.

    watch() runs on the desktop thread before it sleeps. Future callbacks keep
    neither the owner, Future, nor Inbox alive. Replaced generations and closed
    owners cannot post new readiness; result/error handling stays with the owner.
    """
    def __init__(self, inbox):
        import weakref
        self._inbox = weakref.ref(inbox)
        self._watched = weakref.WeakKeyDictionary()

    def watch(self, owner, key, attribute='_future'):
        import weakref
        future = getattr(owner, attribute, None)
        if future is None or not callable(getattr(future, 'add_done_callback', None)):
            return False
        try:
            owner_ref = weakref.ref(owner)
            future_ref = weakref.ref(future)
            watched = self._watched.setdefault(owner, {})
        except TypeError:
            return False
        if attribute in watched and watched[attribute]() is future:
            return True
        watched[attribute] = future_ref
        inbox_ref = self._inbox
        def completed(done):
            current = owner_ref()
            inbox = inbox_ref()
            if (current is not None and inbox is not None
                    and not getattr(current, '_closed', False)
                    and getattr(current, attribute, None) is done):
                inbox.notify(key)
        future.add_done_callback(completed)
        return True
