"""Nonblocking native-app client for one explicitly selected Reticulum owner."""
import os
import math
import queue
import threading
import json
import _socket as socket
import subprocess
import sys
import tempfile
from pathlib import Path

if __package__:
    from .owner import exchange
    from .service_transport import SocketTransport
else:
    from owner import exchange
    from service_transport import SocketTransport


class Provider:
    def __init__(self, path, transport=None):
        self._wakeup = None
        self.path = str(path)
        self.transport = transport or SocketTransport(self.path)
        self.state = dict(version=1, owner_online=False, capabilities=[], peers=[],
                          radios=[], messages=[], packets=[],
                          error='Reticulum owner connecting')
        self.pending = queue.Queue(maxsize=8)
        self.stopped = threading.Event()
        self.client = None
        self.readable, self.writable = socket.socketpair()
        self.readable.setblocking(False)
        self.writable.setblocking(False)
        self.worker = threading.Thread(target=self._work, name='reticulum-owner', daemon=True)
        self.sender = threading.Thread(target=self._send, name='reticulum-requests', daemon=True)
        self.worker.start()
        self.sender.start()

    def remote(self, peer, service='reticulum'):
        if __package__:
            from .service_transport import ReticulumTransport
        else:
            from service_transport import ReticulumTransport
        return Provider(self.path, transport=ReticulumTransport(self.path, peer, service))

    def snapshot(self):
        return self.state

    def bind_wakeup(self, callback):
        self._wakeup = callback

    def _publish(self, state):
        self.state = state
        try:
            self.writable.send(b'x')
        except (BlockingIOError, OSError):
            pass

        if self._wakeup is not None: self._wakeup()

    def drain(self):
        try:
            while self.readable.recv(4096):
                pass
        except BlockingIOError:
            pass

    def request(self, action, payload):
        if action not in self.state.get('capabilities', ()):
            raise ValueError('Selected owner does not provide ' + action)
        request_id = os.urandom(8).hex()
        try:
            request = dict(version=1, request_id=request_id, action=action, payload=payload)
            if getattr(self.transport, 'managed', False): request['_local_epoch'] = self.transport.epoch
            self.pending.put_nowait(request)
        except queue.Full:
            raise ValueError('Reticulum owner request queue is full') from None
        return request_id

    def _send(self):
        while not self.stopped.is_set():
            request = self.pending.get()
            if request is None:
                return
            try:
                if getattr(self.transport, 'managed', False):
                    self.transport.exchange_queued(request, request.pop('_local_epoch'))
                else:
                    self.transport.exchange(request)
            except (OSError, ValueError) as error:
                self._publish(dict(self.state, last_job=dict(id=request['request_id'], action=request['action'],
                                                          state='failed', error=str(error))))

    def _work(self):
        while not self.stopped.is_set():
            try:
                self.transport.subscribe(self._publish, self.stopped)
            except (OSError, ValueError) as error:
                if not self.stopped.is_set():
                    self._publish(dict(self.state, owner_online=False, capabilities=[], error=str(error)))
                    if getattr(self.transport, 'managed', False):
                        if not self.transport.retry: return
                        if self.transport.wait_retry(self.stopped): return
                    else:
                        self.stopped.wait(1)
            finally:
                self.client = None
                if self.stopped.is_set() and getattr(self.transport, 'managed', False): self.transport.dispose()

    def close(self):
        self._wakeup = None
        self.stopped.set()
        self.transport.close()
        if self.client:
            try:
                self.client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        try:
            self.pending.put_nowait(None)
        except queue.Full:
            pass
        self.worker.join(timeout=3)
        self.sender.join(timeout=3)
        if getattr(self.transport, 'managed', False) and not self.worker.is_alive(): self.transport.dispose()
        self.readable.close()
        self.writable.close()


class LocalProvider(Provider):
    """Own or borrow the explicitly selected local station management service."""
    def __init__(self, state, station='mac', *, interpreter=None, radio_id=None,
                 connection=None, port=None, minimum_txpower=None, maximum_txpower=None,
                 seed_profile=None, prepare_nokia_spp=False, startup_timeout=None, availability_only=False):
        options = (interpreter, radio_id, connection, port, minimum_txpower, maximum_txpower)
        session = any(value is not None for value in options) or seed_profile is not None or prepare_nokia_spp or startup_timeout is not None
        if session and any(value is None for value in options):
            raise ValueError('Local radio management requires all explicit runtime and device options')
        if startup_timeout is not None and (type(startup_timeout) not in (int, float) or not math.isfinite(startup_timeout) or not 5 <= startup_timeout <= 120):
            raise ValueError('Startup timeout must be a finite number from 5 to 120 seconds')
        self.process = self.log = self.runtime = None
        state = Path(state).expanduser().absolute()
        if session:
            import stat
            if __package__:
                from .endpoints import Endpoint, saved_endpoint
            else:
                from endpoints import Endpoint, saved_endpoint
            endpoint = saved_endpoint(state, Endpoint(station, radio_id, connection, port))
            connection, port = endpoint.connection, endpoint.port
            state.mkdir(mode=0o700, parents=True, exist_ok=True)
            for directory in (state, state / 'management-runtime'):
                directory.mkdir(mode=0o700, exist_ok=True)
                info = directory.lstat()
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                    raise ValueError('Local management state must be private and user-owned')
            root = state / 'management-runtime'
            python = Path(interpreter)
            if not python.is_absolute() or not python.is_file():
                raise ValueError('Select an existing approved absolute interpreter')
            command = [str(python), '-B', str(Path(__file__).with_name('session_owner.py')),
                       '--socket', str(root / 'owner.sock'), '--state', str(state), '--station', station,
                       '--radio-id', radio_id, '--connection', connection, '--port', port,
                       '--minimum-txpower', str(minimum_txpower), '--maximum-txpower', str(maximum_txpower)]
            if prepare_nokia_spp:
                command.append("--prepare-nokia-spp")
            if startup_timeout is not None:
                command += ['--startup-timeout', str(startup_timeout)]
            if seed_profile is not None:
                seed = Path(seed_profile)
                if not seed.is_absolute() or not seed.is_file():
                    raise ValueError('Select an existing explicit seed profile JSON')
                command += ['--seed-profile', str(seed)]
            if __package__:
                from .local_owner import ManagedOwner
            else:
                from local_owner import ManagedOwner
            def plan():
                selected_connection, selected_port = self._session_endpoint(state, station, radio_id, connection, port)
                selected_command = list(command)
                selected_command[selected_command.index('--connection') + 1] = selected_connection
                selected_command[selected_command.index('--port') + 1] = selected_port
                def validate(existing):
                    radio = next(iter(existing.get('radios', [])), {})
                    if existing.get('service_type') != 'reticulum-session' or existing.get('station_id') != station or radio.get('radio_id') != radio_id or radio.get('connection') != selected_connection or radio.get('port') != selected_port or radio.get('minimum_txpower') != minimum_txpower or radio.get('maximum_txpower') != maximum_txpower:
                        raise ValueError('Existing local owner does not match the explicit selection')
                    if startup_timeout is not None and existing.get('startup_timeout') != float(startup_timeout):
                        raise ValueError('Existing local owner uses a different startup timeout')
                return selected_command, validate
            identity = dict(service='reticulum-session', station=station, radio=radio_id)
            transport = ManagedOwner(root / 'owner.sock', identity, plan, availability_only=availability_only)
            super().__init__(root / 'owner.sock', transport=transport)
            return
        else:
            self.runtime = tempfile.TemporaryDirectory(prefix='rnc-', dir='/tmp')
            root = Path(self.runtime.name)
            command = [sys.executable, '-B', str(Path(__file__).with_name('owner.py')),
                       '--socket', str(root / 'owner.sock'), '--state', str(state), '--station', station]
        self.log = (root / 'owner.log').open('ab')
        try:
            self.process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=self.log,
                                            stderr=subprocess.STDOUT, close_fds=True, start_new_session=True)
            super().__init__(root / 'owner.sock', transport=SocketTransport(str(root / 'owner.sock'),availability_only=availability_only))
        except BaseException:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=25)
            self.log.close()
            if self.runtime:
                self.runtime.cleanup()
            raise

    def _session_endpoint(self, state, station, radio, connection, port):
        if __package__:
            from .endpoints import Endpoint, saved_endpoint
        else:
            from endpoints import Endpoint, saved_endpoint
        endpoint = saved_endpoint(state, Endpoint(station, radio, connection, port))
        return endpoint.connection, endpoint.port

    def close(self):
        super().close()
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
                raise RuntimeError('Management shutdown required a forced kill; verify radio cleanup')
        if self.log:
            self.log.close()
        if self.runtime:
            self.runtime.cleanup()


class CarrierProvider(LocalProvider):
    """Own or borrow an idle gateway using the standard RNS carrier implementations."""
    def __init__(self,state,station,interpreter,carriers,relay=False,availability_only=False):
        import hashlib
        import stat
        if __package__:
            from .carriers import configuration
        else:
            from carriers import configuration
        config=configuration(carriers,relay)
        digest=hashlib.sha256(config.encode()).hexdigest()
        self.process=self.log=self.runtime=None
        state=Path(state).expanduser().absolute();root=state/'carrier-runtime'
        for directory in (state,root):
            directory.mkdir(mode=0o700,parents=True,exist_ok=True)
            info=directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
                raise ValueError('Carrier state must be private and user-owned')
        python=Path(interpreter)
        if not python.is_absolute() or not python.is_file():raise ValueError('Select an existing absolute interpreter with RNS and LXMF')
        path=root/'owner.sock'
        command=[str(python),'-B',str(Path(__file__).with_name('carrier_owner.py')),
                 '--socket',str(path),'--state',str(state),'--station',station,
                 '--carriers',json.dumps(carriers,separators=(',',':'))]
        if relay:command.append('--relay')
        if __package__:
            from .local_owner import ManagedOwner
        else:
            from local_owner import ManagedOwner
        def validate(existing):
            if existing.get('service_type')!='reticulum-carrier' or existing.get('station_id')!=station or existing.get('carrier_config_sha256')!=digest:
                raise ValueError('Existing carrier owner differs; choose a separate state directory for different carriers')
        transport=ManagedOwner(path,dict(service='reticulum-carrier',station=station),lambda:(command,validate),availability_only=availability_only)
        Provider.__init__(self,path,transport=transport)


class MeshCoreProvider(LocalProvider):
    """MeshCore uses the same binary owner client and owned process lifecycle."""
    def __init__(self,state,station,interpreter,port,trusted_peripheral=False,baudrate=115200,availability_only=False):
        import stat
        from pathlib import Path
        self.process=self.log=self.runtime=None
        state=Path(state);root=state/'meshcore-runtime'
        for directory in (state,root):
            directory.mkdir(mode=0o700,parents=True,exist_ok=True)
            info=directory.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('MeshCore state must be private and user-owned')
        path=root/'owner.sock'
        command=[interpreter,'-B',str(Path(__file__).resolve().parents[1]/'meshcore/owner.py'),
                 '--socket',str(path),'--state',str(state),'--station',station,'--port',port,'--baudrate',str(baudrate)]
        if trusted_peripheral:command.append('--trusted-peripheral')
        if __package__:
            from .local_owner import ManagedOwner
        else:
            from local_owner import ManagedOwner
        def validate(existing):
            if existing.get('service_type')!='meshcore-companion' or existing.get('station_id')!=station or existing.get('port')!=port or existing.get('baudrate')!=baudrate or existing.get('trusted_peripheral') is not trusted_peripheral:
                raise ValueError('Existing MeshCore owner does not match the explicit device and trust selection')
        transport=ManagedOwner(path,dict(service='meshcore-companion',station=station),lambda:(command,validate),availability_only=availability_only)
        Provider.__init__(self,path,transport=transport)
