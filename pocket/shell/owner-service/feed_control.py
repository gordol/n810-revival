"""Fixed control frames and reception intent for the existing feed owner."""
import copy
import json
import os
import socket
import struct
import tempfile
import time
import uuid
from pathlib import Path


def save_intent(path, enabled):
    path = Path(path)
    if not path.parent.is_dir():
        raise FileNotFoundError('Reception state directory is not established: '+str(path.parent))
    fd, temporary = tempfile.mkstemp(prefix='.reception-intent-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump({'enabled': enabled}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass

PREFIX = b'@FEED '
ACTIONS = frozenset(('subscribe', 'receive_start', 'receive_stop',
                     'radio_disconnect', 'controller_on', 'controller_off'))


def frame(value):
    result = PREFIX + json.dumps(value, separators=(',', ':')).encode() + b'\n'
    if len(result) > 32768:
        raise ValueError('control frame exceeds 32768 bytes')
    return result


def authorize(peer, uid=None):
    expected = os.getuid() if uid is None else uid
    _, actual, _ = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    return actual == expected


class Requests:
    def __init__(self):
        self.pending = bytearray()

    def feed(self, data):
        self.pending.extend(data)
        if len(self.pending) > 4096:
            raise ValueError('control input exceeds 4096 bytes')
        result = []
        while b'\n' in self.pending:
            line, _, rest = self.pending.partition(b'\n')
            self.pending[:] = rest
            request = json.loads(line)
            if (not isinstance(request, dict) or
                    set(request) != {'type', 'version', 'request_id', 'action'} or
                    request['type'] != 'feed_control' or type(request['version']) is not int or
                    request['version'] != 1 or not isinstance(request['request_id'], str) or
                    not 1 <= len(request['request_id']) <= 64 or
                    not request['request_id'].isascii() or
                    not request['request_id'].isprintable() or
                    not isinstance(request['action'], str) or request['action'] not in ACTIONS):
                raise ValueError('unsupported control request')
            result.append(request)
        return result


class Intent:
    def __init__(self, enabled=True):
        self.instance_id = uuid.uuid4().hex
        self.enabled = enabled
        self.controller = {'available': False, 'powered': None, 'devices': [],
                           'error': 'controller observation unavailable'}
        self.power_pending = None
        self.connected = None
        self.observed_at = None
        self.last_disconnect = None
        self.stopping = False
        self.revision = 0

    @property
    def suspension(self):
        if not self.enabled:
            return 'stopped'
        if self.power_pending is False or self.controller['powered'] is False:
            return 'controller_off'
        if self.controller['powered'] is None:
            return 'controller_unknown'
        return None

    @property
    def can_receive(self):
        return self.suspension is None

    def observe_controller(self, state):
        self.controller = copy.deepcopy(state)
        if state['powered'] is self.power_pending:
            self.power_pending = None
        if state['powered'] is False and self.connected is not False:
            self.observe_radio(False)
        self.revision += 1

    def observe_radio(self, connected, observed_at=None):
        self.connected = connected
        self.observed_at = time.time() if observed_at is None else observed_at
        if connected is False:self.last_disconnect = self.observed_at
        self.revision += 1

    def action(self, action):
        if action == 'receive_start':
            self.enabled = True
        elif action in ('receive_stop', 'radio_disconnect'):
            self.enabled = False
        elif action in ('controller_on', 'controller_off'):
            if not self.controller['available']:
                raise ValueError('controller control unavailable')
            self.power_pending = action == 'controller_on'
        elif action != 'subscribe':
            raise ValueError('unsupported action')
        self.revision += 1

    def snapshot(self):
        capabilities = ['subscribe', 'receive_start', 'receive_stop', 'radio_disconnect']
        if self.controller['available']:
            capabilities += ['controller_on', 'controller_off']
        return {'version': 1, 'type': 'state', 'revision': self.revision,
                'owner': {'instance_id': self.instance_id, 'context': 'live_owner'},
                'controller': copy.deepcopy(self.controller),
                'reception': {'enabled': self.enabled, 'suspended_reason': self.suspension,
                              'stopping': self.stopping},
                'radio': {'connected': self.connected, 'observed_at': self.observed_at, 'last_disconnect': self.last_disconnect},
                'capabilities': capabilities}
