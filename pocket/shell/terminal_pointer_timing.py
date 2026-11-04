"""Label terminal byte-ingress time; never claim it is physical mouse event time."""
import time
from pointer_events import PointerEvent, SourceStamp


class IngressDecoder:
    def __init__(self, decoder, *, clock=time.monotonic_ns, stream=None):
        self.decoder, self.clock = decoder, clock
        self.stream = stream or f'terminal-ingress-{id(self)}'
        self.batch = 0

    @property
    def pending(self):
        return self.decoder.pending

    def feed(self, data, expire=False):
        fragmented = bool(self.pending)
        stamp = None
        if data:
            self.batch += 1
            stamp = SourceStamp(self.clock(), self.stream, 'ingress', self.batch)
        events = self.decoder.feed(data, expire=expire)
        return [PointerEvent(event, stamp=None if fragmented else stamp)
                if event[0] == 'mouse' else event for event in events]
