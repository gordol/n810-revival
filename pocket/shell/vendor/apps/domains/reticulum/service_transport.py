"""Owner protocol adapters. Services keep their existing requests and events."""
import os
from contextlib import closing
import math
import _socket as socket
import threading

if __package__:
    from .wire import LIMIT, encode, decode, read_socket
else:
    from wire import LIMIT, encode, decode, read_socket


def request_timeout(request):
    # An explicit device-read grant may start the existing local catalogue.
    if request.get('action')=='service_share':return 120
    value = request.get('payload', {}).get('timeout',25) if request.get('action')=='service_call' else 25
    if type(value) not in (int,float) or not math.isfinite(value) or not 5 <= value <= 600:
        raise ValueError('Service timeout must be between 5 and 600 seconds')
    return value


class SocketTransport:
    """Device-local Unix or numeric loopback TCP stream; remote traffic needs encryption."""
    def __init__(self, address, family=socket.AF_UNIX, *, availability_only=False):
        if family != socket.AF_UNIX:
            if family not in (socket.AF_INET, socket.AF_INET6):
                raise ValueError('Use SSH or Reticulum for connections between devices')
            import ipaddress
            try:
                ip = ipaddress.ip_address(address[0])
                local = (ip.ipv4_mapped or ip).is_loopback if ip.version == 6 else ip.is_loopback
            except (ValueError, TypeError, IndexError):
                local = False
            if not local:
                raise ValueError('Cleartext owner TCP is restricted to numeric loopback addresses; use SSH or Reticulum')
        self.address, self.family = address, family
        self.availability_only = availability_only
        self.active = None
        self.lock = threading.Lock()

    def connect(self):
        client = socket.socket(self.family, socket.SOCK_STREAM)
        client.settimeout(3)
        try: client.connect(self.address)
        except BaseException: client.close(); raise
        return client

    def exchange(self, request):
        with closing(self.connect()) as client:
            client.settimeout(request_timeout(request)+10)
            client.sendall(encode(request))
            return read_socket(client)

    def subscribe(self, publish, stopped):
        with closing(self.connect()) as client:
            with self.lock: self.active = client
            try:
                if stopped.is_set(): return
                request = dict(version=1, action='subscribe')
                if self.availability_only:request['scope']='availability'
                client.sendall(encode(request))
                client.settimeout(None)
                while not stopped.is_set():
                    publish(read_socket(client))
            finally:
                with self.lock: self.active = None

    def close(self):
        with self.lock:
            if self.active:
                try: self.active.shutdown(socket.SHUT_RDWR)
                except OSError: pass


class ReticulumTransport:
    """Same owner protocol through a selected local RNS gateway, without importing RNS."""
    def __init__(self, gateway, peer, service='reticulum', timeout=25):
        if len(peer) != 32 or any(c not in '0123456789abcdef' for c in peer):
            raise ValueError('Select a full verified peer identity')
        self.timeout = request_timeout(dict(action='service_call',payload=dict(timeout=timeout)))
        self.gateway, self.peer, self.service = str(gateway), peer, service
        self.events = SocketTransport(self.gateway)
        self.cancelled = threading.Event()
        self.session = os.urandom(8).hex()

    def payload(self, request):
        return dict(peer=self.peer, service=self.service, session=self.session, request=request, timeout=self.timeout)

    def exchange(self, request):
        # The gateway waits for this operation once. Failure never replays a command.
        return SocketTransport(self.gateway).exchange(dict(version=1, action='service_call',
                    request_id=os.urandom(8).hex(), payload=self.payload(request)))

    def subscribe(self, publish, stopped):
        initial = self.exchange(dict(version=1, action='subscribe'))
        publish(initial)
        revision = [None]
        def update(state):
            for row in state.get('data_bridge', {}).get('services', ()):
                if row.get('peer') == self.peer and row.get('service') == self.service and row.get('session') == self.session:
                    if row.get('error'): raise ValueError(row['error'])
                    if row.get('revision') != revision[0]:
                        revision[0] = row.get('revision')
                        value = SocketTransport(self.gateway).exchange(dict(version=1, action='service_snapshot', request_id=os.urandom(8).hex(),
                            payload=dict(peer=self.peer,service=self.service,session=self.session)))
                        publish(value)
                    return
            raise ValueError('Selected service subscription ended; reconnect')
        self.events.subscribe(update, stopped)

    def close(self):
        self.events.close()
        if not self.cancelled.is_set():
            self.cancelled.set()
            try:
                SocketTransport(self.gateway).exchange(dict(version=1, action='service_cancel', request_id=os.urandom(8).hex(),
                    payload=dict(peer=self.peer, service=self.service, session=self.session)))
            except (OSError, ValueError): pass
