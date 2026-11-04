"""Source-timed empty-map double-tap recognition; no clock, I/O or zoom ownership."""


class DoubleTap:
    def __init__(self, *, slop, radius, max_contact_ns, interval_ns):
        if (len(slop) != 2 or len(radius) != 2 or min(*slop, *radius) < 0
                or max_contact_ns <= 0 or interval_ns <= 0):
            raise ValueError('invalid double-tap bounds')
        self.slop, self.radius = slop, radius
        self.max_contact_ns, self.interval_ns = max_contact_ns, interval_ns
        self.reset()

    def reset(self):
        self.contact = None
        self.pending = None
        self.last = None
        self.context = None
        self.dragged = False

    def feed(self, event, *, empty, context):
        """Return True once on the second eligible release; marker taps return False."""
        stamp = getattr(event, 'stamp', None)
        if (len(event) != 5 or event[0] != 'mouse' or stamp is None
                or event[1] not in (0, 32)):
            self.reset()
            return False
        if (self.context != context or self.last is not None and
                (stamp.stream != self.last.stream or stamp.kind != self.last.kind
                 or stamp.ns < self.last.ns)):
            self.reset()
        self.context, self.last = context, stamp
        _, button, x, y, released = event
        point = x, y
        if button == 0 and not released:
            if self.contact is not None or not empty:
                self.pending = None
            self.contact = (stamp, point, empty, False)
            self.dragged = False
            return False
        if self.contact is None:
            self.pending = None
            return False
        started, origin, eligible, dragged = self.contact
        left, top, right, bottom = getattr(event, 'bounds', (x, y, x, y))
        dragged = dragged or (max(abs(left-origin[0]), abs(right-origin[0])) > self.slop[0]
                              or max(abs(top-origin[1]), abs(bottom-origin[1])) > self.slop[1])
        self.dragged = dragged
        eligible = (eligible and empty and not dragged
                    and stamp.ns-started.ns <= self.max_contact_ns)
        if not eligible:
            self.pending = None
        if not released:
            self.contact = started, origin, eligible, dragged
            return False
        self.contact = None
        if stamp.kind == 'ingress' and started.batch == stamp.batch:
            eligible = False
            self.pending = None
        if not eligible:
            return False
        if self.pending is not None:
            previous, position = self.pending
            if (stamp.ns-previous.ns <= self.interval_ns
                    and (stamp.kind != 'ingress' or previous.batch != started.batch)
                    and abs(origin[0]-position[0]) <= self.radius[0]
                    and abs(origin[1]-position[1]) <= self.radius[1]):
                self.pending = None
                return True
        self.pending = stamp, origin
        return False
