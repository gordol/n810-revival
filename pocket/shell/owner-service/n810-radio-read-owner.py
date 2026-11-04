"""Bounded same-user Unix endpoint for the existing radio owner's read callbacks."""
import json
import os
from pathlib import Path
import selectors
import socket
import stat
import struct
import time

PATH = Path('/dev/shm/n810-radio-read/control.sock')
REQUEST_LIMIT = 4096
RESPONSE_LIMIT = 32768
CLIENT_LIMIT = 8
CLIENT_SECONDS = 2


def peer_uid(client):
    if not hasattr(socket, 'SO_PEERCRED'):
        raise OSError('Same-user peer authentication unavailable')
    raw = client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
    return struct.unpack('3i', raw)[1]


class Endpoint:
    def __init__(self, *, submit, status, cancel, path=PATH, authenticate=peer_uid, radio_live=None, tune=None):
        if authenticate is peer_uid and not hasattr(socket, 'SO_PEERCRED'):
            raise OSError('Same-user peer authentication unavailable')
        self.tune=tune
        self.submit = submit; self.status = status; self.cancel = cancel
        self.path = Path(path); self.authenticate = authenticate; self.radio_live = radio_live
        self.selector = selectors.DefaultSelector(); self.clients = {}
        self.server = None; self.inode = None; self.created_directory = False
        try:
            try:
                self.path.parent.mkdir(mode=0o700)
                self.created_directory = True
            except FileExistsError:
                pass
            info = self.path.parent.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
                raise ValueError('Endpoint directory must be a private same-user directory')
            self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server.bind(str(self.path)); self.inode = self.path.lstat().st_ino
            self.path.chmod(0o600); self.server.listen(CLIENT_LIMIT); self.server.setblocking(False)
            self.selector.register(self.server, selectors.EVENT_READ)
        except BaseException:
            self.close(); raise

    def drop(self, client):
        if client not in self.clients: return
        self.selector.unregister(client); del self.clients[client]; client.close()

    def respond(self, client, value):
        try:
            raw = json.dumps(value, separators=(',', ':'), allow_nan=False).encode() + b'\n'
        except (ValueError, TypeError, RecursionError):
            raw = b'{"version":1,"ok":false,"error":"Invalid owner response"}\n'
        if len(raw) > RESPONSE_LIMIT:
            raw = b'{"version":1,"ok":false,"error":"Response exceeds limit"}\n'
        self.clients[client]['output'] = raw
        self.selector.modify(client, selectors.EVENT_WRITE)

    def dispatch(self, raw):
        def constant(_): raise ValueError('Non-finite JSON number')
        value = json.loads(raw, parse_constant=constant)
        if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1:
            raise ValueError('Expected request version 1')
        operation = value.get('operation'); request_id = value.get('request_id')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 80:
            raise ValueError('Bounded request ID required')
        fields = {'version', 'operation', 'request_id'}
        if operation == 'read_current':
            if set(value) != fields | {'requested_at', 'expires_at'}:
                raise ValueError('Invalid read request fields')
            result = self.submit(value)
        elif operation=='tune_repeater' and self.tune is not None:
            if set(value)!=fields|{'repeater'}:raise ValueError('Invalid tuning request fields')
            result=self.tune(request_id,value['repeater'])
        elif operation=='tune_status' and self.tune is not None:
            if set(value)!=fields:raise ValueError('Invalid tuning status fields')
            result=self.tune(request_id,None)
        elif operation in ('status', 'cancel'):
            if set(value) != fields: raise ValueError('Invalid request fields')
            result = (self.status if operation == 'status' else self.cancel)(request_id)
        else:
            raise ValueError('Unsupported read operation')
        response = dict(version=1, ok=True, result=result)
        if self.radio_live is not None:
            state = self.radio_live()
            if not isinstance(state, dict): raise ValueError('Owner state unavailable')
            response['radio_live'] = state
        return response

    def next_deadline(self):
        return min((state['deadline'] for state in self.clients.values()),default=None)

    def poll(self, now=None):
        now = time.monotonic() if now is None else now
        for client, state in list(self.clients.items()):
            if now >= state['deadline']: self.drop(client)
        for key, mask in self.selector.select(0):
            client = key.fileobj
            if client is self.server:
                try: accepted, _ = self.server.accept()
                except BlockingIOError: continue
                try:
                    if len(self.clients) >= CLIENT_LIMIT or self.authenticate(accepted) != os.getuid():
                        accepted.close(); continue
                    accepted.setblocking(False)
                    self.clients[accepted] = dict(input=bytearray(), output=None, deadline=now + CLIENT_SECONDS)
                    self.selector.register(accepted, selectors.EVENT_READ)
                except OSError:
                    accepted.close()
                continue
            if client not in self.clients: continue
            state = self.clients[client]
            try:
                if mask & selectors.EVENT_READ:
                    block = client.recv(REQUEST_LIMIT + 1 - len(state['input']))
                    if not block: self.drop(client); continue
                    state['input'].extend(block)
                    if len(state['input']) > REQUEST_LIMIT:
                        self.respond(client, dict(version=1, ok=False, error='Request exceeds limit')); continue
                    if b'\n' not in state['input']: continue
                    line, tail = state['input'].split(b'\n', 1)
                    try:
                        if tail.strip(): raise ValueError('One request per connection')
                        response = self.dispatch(line)
                    except (ValueError, TypeError, RuntimeError, RecursionError) as error:
                        response = dict(version=1, ok=False, error=str(error)[:200])
                    self.respond(client, response)
                elif mask & selectors.EVENT_WRITE:
                    count = client.send(state['output'])
                    if not count: self.drop(client); continue
                    state['output'] = state['output'][count:]
                    if not state['output']: self.drop(client)
            except BlockingIOError:
                pass
            except OSError:
                self.drop(client)

    def close(self):
        for client in list(self.clients): self.drop(client)
        if self.server is not None: self.server.close()
        self.selector.close()
        if self.inode is not None:
            try:
                if self.path.lstat().st_ino == self.inode: self.path.unlink()
            except FileNotFoundError:
                pass
        if self.created_directory:
            try: self.path.parent.rmdir()
            except OSError: pass
