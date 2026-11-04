"""Wake an independent collector from the existing receive stream."""
import re
import selectors
import socket
import time

PACKET = re.compile(rb'^\d\d:\d\d:\d\d \S+>\S+ ctl=[0-9a-f]+(?: pid=[0-9a-f]+)? ')


class PacketEvents:
    def __init__(self, path, capture, report=print):
        self.path = path
        self.capture = capture
        self.report = report
        self.selector = selectors.DefaultSelector()
        self.stream = None
        self.pending = bytearray()
        self.retry_at = 0

    def disconnected(self):
        if self.stream is not None:
            self.selector.unregister(self.stream)
            self.stream.close()
            self.stream = None
        self.pending.clear()
        self.retry_at = time.monotonic() + 10

    def connect(self):
        stream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stream.settimeout(2)
        try:
            stream.connect(self.path)
        except OSError as error:
            stream.close()
            self.report('Feed unavailable: '+str(error))
            self.retry_at = time.monotonic()+10
            return
        stream.setblocking(False)
        self.stream = stream
        self.selector.register(stream, selectors.EVENT_READ)
        self.capture()

    def ready(self):
        try:
            block = self.stream.recv(65536)
        except BlockingIOError:
            return
        except OSError:
            self.disconnected()
            return
        if not block:
            self.disconnected()
            return
        self.pending.extend(block)
        if len(self.pending) > 131072:
            self.report('Receive stream line exceeds limit; reconnecting')
            self.disconnected()
            return
        changed = False
        while b'\n' in self.pending:
            line, _, rest = self.pending.partition(b'\n')
            self.pending[:] = rest
            changed = changed or bool(PACKET.match(line))
        if changed:
            self.capture()

    def run(self):
        while True:
            if self.stream is None and time.monotonic() >= self.retry_at:
                self.connect()
            timeout = max(0, self.retry_at-time.monotonic()) if self.stream is None else None
            for _key, _mask in self.selector.select(timeout):
                self.ready()

    def close(self):
        self.disconnected()
        self.selector.close()
