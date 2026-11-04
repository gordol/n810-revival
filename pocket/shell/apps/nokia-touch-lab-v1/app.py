"""Input-driven comparison control; never reads an input device."""
from collections import deque


class TouchLab:
    def __init__(self, host):
        self.host = host
        self.width, self.height = 60, 21
        self.square = (5, 10)
        self.anchor = None
        self.state = 'ready'
        self.counts = dict(down=0, move=0, up=0, cancel=0)
        self.history = deque(maxlen=4)
        self.evidence = ()
        self.snapshot()

    @property
    def pointer_captured(self):
        return self.anchor is not None

    def snapshot(self):
        trace = getattr(self.host, 'pointer_trace', None)
        source = getattr(trace, 'input_source', None)
        data = source() if callable(source) else {}
        data = data or {}
        last = data.get('last_drain', {})
        state = data.get('state', {})
        counts = data.get('counts', {})
        rows = tuple(getattr(trace, 'rows', ()))
        dispatch = next((r for r in reversed(rows) if r.get('kind') == 'dispatch'), {})
        owners = [name for name, form in getattr(self.host, 'app_forms', {}).items()
                  if getattr(form, 'pointer_captured', False)]
        self.evidence = (
            'Snapshot on input only; Space refreshes.',
            'Raw bounds: ' + str(last.get('raw_bounds', 'unavailable')),
            'Contact: %s  mapped down: %s' % (state.get('pressed', '?'), state.get('mapper_down', '?')),
            'Mapped: %s  dropped: %s  cancels: %s' % (counts.get('mapped_events', '?'), counts.get('syn_dropped', '?'), counts.get('cancel_events', '?')),
            'WM capture: %s  app: %s' % (bool(getattr(self.host, 'drag', None)), ','.join(owners) or 'none'),
            'Last trace: %s %s' % (dispatch.get('route', 'unavailable'), dispatch.get('local', '')),
        )

    def pointer(self, column, row, width, button=0, released=False):
        self.width = width
        if released:
            self.counts['up'] += 1
            self.state = 'released'
            self.anchor = None
        elif button & 32:
            self.counts['move'] += 1
            self.state = 'dragging' if self.anchor else 'move without capture'
            if self.anchor:
                dx, dy = self.anchor
                self.square = (max(1, min(width-6, column-dx)), max(9, min(self.height-5, row-dy)))
        elif button & 3 == 0:
            self.counts['down'] += 1
            x, y = self.square
            hit = x <= column < x+5 and y <= row < y+3
            self.anchor = (column-x, row-y) if hit else None
            self.state = 'pressed square' if hit else 'pressed outside square'
        else:
            return False
        self.history.append('%s (%s,%s)' % (self.state, column, row))
        self.snapshot()
        return True

    def cancel_pointer(self):
        if self.anchor is not None:
            self.counts['cancel'] += 1
            self.state = 'cancelled; reason unknown'
            self.history.append(self.state)
        self.anchor = None
        self.snapshot()

    def key(self, key):
        if key.lower() == 'r':
            self.cancel_pointer()
            self.square = (5, 10)
            self.state = 'ready'
        elif key != ' ':
            return False
        self.snapshot()
        return True

    def lines(self):
        rows = ['Drag ### square; then this window title.',
                self.state + ' | capture=' + str(self.pointer_captured),
                'Down {down} Move {move} Up {up} Cancel {cancel}'.format(**self.counts),
                *self.evidence]
        rows += [''] * max(0, self.height-len(rows))
        x, y = self.square
        for offset in range(3):
            if 9 <= y+offset < self.height-2:
                rows[y+offset] = ' '*x + '#####'
        rows[-2:] = ['Space: snapshot  R: reset | map uses real app',
                     self.history[-1] if self.history else 'Waiting for your stylus.']
        return tuple(line[:self.width] for line in rows)
