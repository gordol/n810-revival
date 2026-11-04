"""Reply-driven RNode connection lifecycle, independent of transport and UI."""


class Connection:
    fields = frozenset(('frequency', 'bandwidth', 'txpower', 'sf', 'cr', 'state'))

    def __init__(self, expected, detect, configure, close, publish):
        if set(expected) != self.fields:
            raise ValueError('Complete radio configuration required')
        self.expected = dict(expected)
        self.detect = detect
        self.configure = configure
        self.close = close
        self.publish = publish
        self.phase = 'idle'
        self.replies = {}
        self.generation = 0

    def start(self):
        if self.phase != 'idle':
            raise ValueError('Connection already started')
        self.generation += 1
        self.phase = 'detecting'
        self.publish(self.phase, None)
        if self.phase != 'detecting':
            return self.generation
        try:
            self.detect(self.generation)
        except Exception as error:
            self.failed(self.generation, str(error))
        return self.generation

    def detected(self, generation):
        if generation != self.generation or self.phase != 'detecting':
            return
        self.phase = 'configuring'
        self.publish(self.phase, None)
        if self.phase != 'configuring':
            return
        try:
            self.configure(generation, dict(self.expected))
        except Exception as error:
            self.failed(generation, str(error))

    def readback(self, generation, field, value):
        if generation != self.generation or self.phase != 'configuring':
            return
        if field not in self.fields:
            return
        expected = self.expected[field]
        matches = type(value) is int and (
            abs(expected - value) <= 100 if field == 'frequency' else expected == value)
        if not matches:
            self.failed(generation, 'Radio readback mismatch: ' + field)
            return
        self.replies[field] = value
        if self.replies.keys() == self.fields:
            self.phase = 'ready'
            self.publish(self.phase, None)

    def failed(self, generation, error):
        if generation != self.generation or self.phase not in ('detecting', 'configuring', 'ready'):
            return
        self.phase = 'failed'
        try:
            self.close(generation)
        finally:
            self.publish(self.phase, error)

    def cancel(self):
        if self.phase in ('cancelled', 'failed', 'idle'):
            return
        generation = self.generation
        self.phase = 'cancelled'
        self.generation += 1
        try:
            self.close(generation)
        finally:
            self.publish(self.phase, None)
