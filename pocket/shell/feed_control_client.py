"""Bounded control framing on the existing feed connection; no network owner."""
from collections import deque
import json
import math
import _socket as socket
import threading
import time
import os

ACTIONS = frozenset(('receive_start', 'receive_stop', 'radio_disconnect', 'controller_on', 'controller_off'))


def state_message(value):
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1 or value.get('type') != 'state':
        raise ValueError('Invalid feed state version/type')
    if type(value.get('revision')) is not int or value['revision'] < 0:
        raise ValueError('Invalid feed state revision')
    controller, reception, radio = (value.get(key) for key in ('controller', 'reception', 'radio'))
    if not all(isinstance(row, dict) for row in (controller, reception, radio)):
        raise ValueError('Invalid feed state sections')
    if controller.get('powered') is not None and type(controller['powered']) is not bool:
        raise ValueError('Invalid controller power observation')
    if type(controller.get('available')) is not bool or type(reception.get('enabled')) is not bool:
        raise ValueError('Invalid controller/reception capability')
    if 'stopping' in reception and type(reception['stopping']) is not bool:
        raise ValueError('Invalid reception stopping state')
    if radio.get('connected') is not None and type(radio['connected']) is not bool:
        raise ValueError('Invalid radio connection observation')
    if 'owner' in value:
        owner = value['owner']
        identity = owner.get('instance_id') if isinstance(owner, dict) else None
        if (not isinstance(owner, dict) or owner.get('context') != 'live_owner'
                or type(identity) is not str or len(identity) != 32
                or any(c not in '0123456789abcdefABCDEF' for c in identity)):
            raise ValueError('Invalid live owner identity/context')
    if 'observed_at' in radio:
        stamp = radio['observed_at']
        if stamp is not None and (type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0):
            raise ValueError('Invalid radio observation time')
    reason = reception.get('suspended_reason')
    if reason is not None and (not isinstance(reason, str) or len(reason) > 128 or not reason.isprintable()):
        raise ValueError('Invalid suspension reason')
    devices = controller.get('devices')
    if not isinstance(devices, list) or len(devices) > 32:
        raise ValueError('Connected devices exceed limit')
    for device in devices:
        if not isinstance(device, dict) or type(device.get('connected')) is not bool:
            raise ValueError('Invalid connected device')
        for key in ('name', 'id', 'address'):
            label = device.get(key)
            if label is not None and (not isinstance(label, str) or len(label) > 96 or label and not label.isprintable()):
                raise ValueError('Invalid device label')
    capabilities = value.get('capabilities')
    if not isinstance(capabilities, list) or len(capabilities) > 6 or any(type(action) is not str or action not in ACTIONS | {'subscribe'} for action in capabilities):
        raise ValueError('Invalid feed capability')
    return value


class FeedControl:
    """One queued intent; wake the existing feed thread and main selector."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.readable, self.worker_readable = socket.socketpair()
        self.readable.setblocking(False)
        self.worker_readable.setblocking(False)
        self.lock = threading.Lock()
        self.queue = deque(maxlen=2)
        self.snapshot = None
        self.online = False
        self._transport_connected = False
        self._subscribe_id = None
        self._subscription_acknowledged = False
        self._state_on_stream = False
        self.message = ''
        self.pending = None
        self.deadline = None
        self.closed = False

    def _wake(self, target):
        try:
            target.send(b'x')
        except (BlockingIOError, OSError):
            pass

    def notify(self):
        self._wake(self.worker_readable)

    @staticmethod
    def _drain(sock):
        try:
            while sock.recv(4096):
                pass
        except (BlockingIOError, OSError):
            pass

    def ready(self):
        self._drain(self.readable)

    def worker_ready(self):
        self._drain(self.worker_readable)

    @staticmethod
    def frame(action, request_id):
        return (json.dumps(dict(type='feed_control', version=1, request_id=request_id, action=action), separators=(',', ':')) + '\n').encode('ascii')

    def connected(self):
        # Subscription is read-only and can repeat on a new transport. Mutations cannot.
        with self.lock:
            self.queue.clear()
            if self.pending is not None:
                self.message = 'Connection changed; request outcome unknown. No automatic retry.'
            self.pending = self.deadline = None
            self.online = False
            self._transport_connected = True
            self._subscription_acknowledged = self._state_on_stream = False
            self._subscribe_id = os.urandom(16).hex()
            self.queue.append(self.frame('subscribe', self._subscribe_id))

    @property
    def owner_context(self):
        # Out-of-band live facts; retained snapshot alone never establishes this.
        with self.lock:
            return dict(transport_connected=self._transport_connected,
                        subscribed_on_this_stream=bool(self.online and self._subscription_acknowledged and self._state_on_stream),
                        state=self.snapshot)

    def disconnected(self):
        with self.lock:
            if self.pending is not None:
                self.message = 'Connection lost; request outcome unknown. No automatic retry.'
            self.pending = self.deadline = None
            self.queue.clear()
            self.online = False
            self._transport_connected = False
            self._subscription_acknowledged = self._state_on_stream = False
            self._subscribe_id = None
        self.notify()

    def request(self, action):
        with self.lock:
            snapshot = self.snapshot or {}
            if self.closed or not self.online or self.pending is not None or action not in ACTIONS or action not in snapshot.get('capabilities', ()):
                return False
            request_id = os.urandom(16).hex()
            self.pending = request_id
            self.deadline = self.clock() + 10
            self.message = 'Request sent; waiting for owner.'
            self.queue.append(self.frame(action, request_id))
        self._wake(self.readable)
        return True

    def take(self):
        with self.lock:
            return self.queue.popleft() if self.queue else b''

    def expire(self):
        with self.lock:
            if self.deadline is None or self.clock() < self.deadline:
                return
            self.pending = self.deadline = None
            self.queue.clear()
            self.message = 'No owner reply; request outcome unknown. No automatic retry.'
        self.notify()

    def line(self, raw):
        if not raw.startswith(b'@FEED '):
            return False
        try:
            if len(raw) > 32768:
                raise ValueError('Feed control update exceeds limit')
            value = json.loads(raw[6:])
            if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
                raise ValueError('Invalid feed control version')
            if value.get('type') == 'state':
                state_message(value)
                with self.lock:
                    self.snapshot = value
                    self._state_on_stream = self._transport_connected
                    self.online = (bool(self._transport_connected and self._subscription_acknowledged)
                                   if 'owner' in value else True)
            elif value.get('type') == 'reply':
                if type(value.get('ok')) is not bool:
                    raise ValueError('Invalid feed reply result')
                error = value.get('error')
                if error is not None and (not isinstance(error, str) or len(error) > 512 or not error.isprintable()):
                    raise ValueError('Invalid feed reply error')
                with self.lock:
                    if self._subscribe_id is not None and value.get('request_id') == self._subscribe_id:
                        self._subscription_acknowledged = bool(value['ok'] and self._transport_connected)
                        self.online = bool(self._subscription_acknowledged and self._state_on_stream)
                        if not value['ok']:self.message = error or 'Owner rejected subscription.'
                        self.notify()
                        return True
                    if value.get('request_id') != self.pending or self.pending is None:
                        return True
                    self.pending = self.deadline = None
                    self.message = 'Owner accepted request.' if value['ok'] else error or 'Owner rejected request.'
            else:
                raise ValueError('Unknown feed control message')
        except (ValueError, UnicodeError, TypeError, RecursionError, OverflowError) as error:
            with self.lock:
                self.online = False
                self._subscription_acknowledged = self._state_on_stream = False
                self._subscribe_id = None
                self.message = str(error)
        self.notify()
        return True

    def close(self):
        with self.lock:
            self.closed = True
            self.online = False
            self._transport_connected = False
            self._subscription_acknowledged = self._state_on_stream = False
            self.queue.clear()
            self.pending = self.deadline = None
        self.readable.close()
        self.worker_readable.close()
