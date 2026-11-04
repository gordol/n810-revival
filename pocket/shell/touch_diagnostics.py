"""Fixed-size in-memory touch counters. No I/O, clock calls or input decisions."""

FIELDS = ('drains', 'read_calls', 'bytes', 'records', 'reports', 'emitted_reports',
          'suppressed_reports', 'syn_dropped', 'resyncs', 'cancel_events',
          'discarded_records', 'mapped_events', 'coalesced_moves', 'invalid_timestamps')


class TouchDiagnostics:
    def __init__(self, per_record=False):
        self.per_record = bool(per_record)
        self.counts = dict.fromkeys(FIELDS, 0)
        self.last = self.empty()

    @staticmethod
    def empty():
        return dict(**dict.fromkeys(FIELDS, 0), source_time_ns=[None, None],
                    raw_bounds=[None, None, None, None])

    def begin(self):
        self.last = self.empty()
        self.bump('drains')

    def bump(self, name, amount=1):
        self.counts[name] += amount
        self.last[name] += amount

    def record(self, seconds, microseconds, kind, code, value):
        if not self.per_record:return
        self.bump('records')
        if seconds >= 0 and 0 <= microseconds < 1000000:
            ns = seconds*1000000000+microseconds*1000
            span = self.last['source_time_ns']
            span[0] = ns if span[0] is None else min(span[0], ns)
            span[1] = ns if span[1] is None else max(span[1], ns)
        else:
            self.bump('invalid_timestamps')
        if kind == 0 and code == 0:
            self.bump('reports')
        if kind == 3 and code in (0, 1):
            bounds = self.last['raw_bounds']
            bounds[code] = value if bounds[code] is None else min(bounds[code], value)
            bounds[code+2] = value if bounds[code+2] is None else max(bounds[code+2], value)

    def mapped(self, events):
        self.bump('mapped_events', sum(e[0] == 'mouse' for e in events))

    def snapshot(self, reader, mapper_down=None):
        counts = dict(self.counts)
        last = {key: list(value) if isinstance(value, list) else value
                for key, value in self.last.items()}
        if not self.per_record:
            for field in ('records', 'reports', 'invalid_timestamps'):
                counts[field] = None
                last[field] = None
            last['source_time_ns'] = None
            last['raw_bounds'] = None
        return dict(version=1, collection_mode='per-record' if self.per_record else 'basic',
            counts=counts,
            last_drain=last,
            state=dict(armed=reader.armed, dropping=reader.dropping, pressed=reader.pressed,
                       mapper_down=mapper_down, buffer_bytes=len(reader.buffer), closed=reader.fd is None))
