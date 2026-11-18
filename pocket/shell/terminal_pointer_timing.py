"""Label terminal byte-ingress time; never claim it is physical mouse event time."""
import time
from pointer_events import PointerEvent, SourceStamp


class IngressDecoder:
    def __init__(self, decoder, *, clock=time.monotonic_ns, stream=None):
        self.decoder, self.clock = decoder, clock
        self.stream = stream or f'terminal-ingress-{id(self)}'
        self.batch = 0
        self.last_byte_ns = None

    @property
    def pending(self):
        return self.decoder.pending

    def events(self, platform=None, *, expire=False):
        events = platform.events() if platform is not None else []
        if platform is None or getattr(platform, 'terminal_input', False):
            aged = self.pending and self.last_byte_ns is not None and self.clock() - self.last_byte_ns >= 40_000_000
            events.extend(self.feed(b'', expire=expire or bool(aged)))
        return events

    def feed(self, data, expire=False):
        fragmented = bool(self.pending)
        stamp = None
        if data:
            self.last_byte_ns = self.clock()
            self.batch += 1
            stamp = SourceStamp(self.last_byte_ns, self.stream, 'ingress', self.batch)
        events = self.decoder.feed(data, expire=expire)
        return [PointerEvent(event, stamp=None if fragmented else stamp)
                if event[0] == 'mouse' else event for event in events]
