"""Wake the existing desktop inbox on child exit; child owners still reap."""
import signal


class ChildExitWake:
    def __init__(self, inbox):
        self.inbox = inbox
        self.closed = False
        self.previous = signal.getsignal(signal.SIGCHLD)
        self.handler = self._ready
        signal.signal(signal.SIGCHLD, self.handler)

    def _ready(self, signum, frame):
        if not self.closed:
            try:
                self.inbox.writable.send(b'c')
            except OSError:
                pass
        if callable(self.previous):
            self.previous(signum, frame)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if signal.getsignal(signal.SIGCHLD) == self.handler:
            signal.signal(signal.SIGCHLD, self.previous)
