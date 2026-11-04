"""Shared local management startup, verified stale endpoints and idle recovery."""
import errno
import fcntl
import json
import os
from contextlib import closing
from pathlib import Path
import selectors
import _socket as socket
import stat
import subprocess
import tempfile
import threading
import time

if __package__:
    from .service_transport import SocketTransport, request_timeout
    from .wire import encode, read_socket
    from .owner import private_lock
else:
    from service_transport import SocketTransport, request_timeout
    from wire import encode, read_socket
    from owner import private_lock


def stop_process(process):
    if process.poll() is not None: return
    process.terminate()
    try: process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def endpoint_identity(info):
    return info.st_dev, info.st_ino, info.st_ctime_ns




class EndpointReceipt:
    """Identity and lifetime checks shared by managed and disposable sessions."""
    def __init__(self,path,identity):self.path,self.identity=Path(path),identity

    @property
    def receipt(self): return self.path.with_suffix('.receipt.json')

    def record(self, info):
        value = dict(version=2, owner=self.identity, device=info.st_dev, inode=info.st_ino, ctime_ns=info.st_ctime_ns)
        fd, temporary = tempfile.mkstemp(prefix='.owner-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(value, stream)
            os.replace(temporary, self.receipt)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)

    def known_stale(self, info):
        try:
            fd = os.open(self.receipt, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return False
        with os.fdopen(fd, 'rb') as stream:
            receipt = os.fstat(stream.fileno())
            if not stat.S_ISREG(receipt.st_mode) or receipt.st_uid != os.getuid() or receipt.st_mode & 0o077:
                raise ValueError('Unsafe local owner receipt')
            raw = stream.read(1025)
        if len(raw) > 1024: raise ValueError('Local owner receipt exceeds limit')
        value = json.loads(raw)
        return value == dict(version=2, owner=self.identity, device=info.st_dev, inode=info.st_ino, ctime_ns=info.st_ctime_ns)

    def endpoint_info(self):
        try: info = self.path.lstat()
        except FileNotFoundError: return None
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Refusing unknown or unsafe local owner endpoint')
        return info

    def remove_stale(self):
        parent=self.path.parent.lstat()
        if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=os.getuid() or parent.st_mode&0o077:
            raise ValueError('Owner socket directory must be private')
        try:
            with private_lock(self.path.with_suffix('.lifetime.lock'), blocking=False):
                info=self.endpoint_info()
                if info is None:return
                if not self.known_stale(info):
                    raise ValueError('Unrecognized inactive owner socket retained; inspect it before reconnecting')
                with closing(socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)) as probe:
                    probe.settimeout(.5)
                    try:probe.connect(str(self.path))
                    except OSError as error:
                        if error.errno==errno.ENOENT:return
                        if error.errno!=errno.ECONNREFUSED:raise
                    else:raise OSError(errno.EBUSY,'Owner endpoint is still listening; retained without removal')
                current=self.endpoint_info()
                if current is None or endpoint_identity(current)!=endpoint_identity(info):
                    raise ValueError('Owner endpoint changed; retained without removal')
                self.path.unlink()
        except BlockingIOError:
            raise OSError(errno.EBUSY,'Local owner lifetime lock is held; no duplicate owner started') from None

class ManagedOwner(EndpointReceipt):
    """Cancellable shared startup and event-triggered idle recovery with backoff."""
    managed = True

    def __init__(self, path, identity, plan, *, availability_only=False):
        super().__init__(path,identity)
        self.plan=plan
        self.socket = SocketTransport(str(path), availability_only=availability_only)
        self.cancelled = threading.Event()
        self.cancel_read, self.cancel_write = socket.socketpair()
        self.guard = threading.Lock()
        self.epoch, self.online, self.inode = 0, False, None
        self.retry = False
        self.delay = 0
        self.process = None
        self.disposed = False

    def existing(self, validate):
        info = self.endpoint_info()
        if info is None: return None
        try:
            state = self.socket.exchange(dict(version=1, action='snapshot'))
        except OSError as error:
            if error.errno not in (errno.ECONNREFUSED, errno.ENOENT): raise
            return None
        validate(state)
        current = self.endpoint_info()
        if current is None or endpoint_identity(current) != endpoint_identity(info):
            raise ValueError('Local owner endpoint changed during verification')
        self.record(current)
        return current

    def ensure(self, stopped):
        with private_lock(self.path.with_suffix('.startup.lock'), blocking=False):
            if stopped.is_set() or self.cancelled.is_set(): raise InterruptedError('Owner startup cancelled')
            command, validate = self.plan()
            info = self.existing(validate)
            if info is not None: return info
            self.remove_stale()
            read_fd, write_fd = os.pipe()
            process = None
            try:
                log_fd = os.open(self.path.parent / 'owner.log', os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                with os.fdopen(log_fd, 'ab') as log:
                    process = subprocess.Popen([*command, '--ready-fd', str(write_fd)], stdin=subprocess.DEVNULL,
                        stdout=log, stderr=log, pass_fds=(write_fd,), start_new_session=True)
                self.process = process
            finally:
                os.close(write_fd)
                if process is None: os.close(read_fd)
            accepted = False
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(read_fd, selectors.EVENT_READ, 'ready')
                    selector.register(self.cancel_read, selectors.EVENT_READ, 'cancel')
                    events = selector.select()
                    if stopped.is_set() or self.cancelled.is_set() or any(key.data == 'cancel' for key, _ in events):
                        raise InterruptedError('Owner startup cancelled')
                    if os.read(read_fd, 1) != b'R':
                        code = process.poll()
                        raise OSError('Management owner exited before listener readiness (exit ' + str(code) + ')')
                info = self.existing(validate)
                if info is None: raise OSError('Management owner did not publish a verified endpoint')
                accepted = True
                # A shared idle owner outlives the client that happened to start it.
                threading.Thread(target=process.wait, daemon=True, name='local-owner-exit').start()
                return info
            finally:
                os.close(read_fd)
                if not accepted and process.poll() is None:
                    stop_process(process)

    def subscribe(self, publish, stopped):
        self.retry = False
        try:
            info = self.ensure(stopped)
        except OSError:
            self.retry = not stopped.is_set() and not self.cancelled.is_set()
            if self.retry: self.delay = min(15, self.delay * 2 if self.delay else 0.25)
            raise
        with self.guard:
            self.inode = endpoint_identity(info)
            self.online = True
        started = time.monotonic()
        retryable = True
        def verified(state):
            # ensure() already validates the full station/device selection.
            # Availability streams retain that endpoint identity and use EOF
            # for loss/recovery; ordinary streams still validate every state.
            if not (self.socket.availability_only and state.get('scope') == 'availability'):
                _, validate = self.plan()
                validate(state)
            current = self.endpoint_info()
            if current is None or endpoint_identity(current) != self.inode:
                raise OSError('Local owner endpoint changed during subscription')
            publish(state)
        try:
            self.socket.subscribe(verified, stopped)
            if not stopped.is_set(): raise ConnectionError('Local owner subscription ended')
        except ValueError:
            retryable = False
            raise
        finally:
            with self.guard:
                self.online = False
                self.epoch += 1
            if retryable and not stopped.is_set() and not self.cancelled.is_set():
                self.retry = True
                self.delay = 0.25 if time.monotonic() - started >= 30 else min(15, self.delay * 2 if self.delay else 0.25)

    def wait_retry(self, stopped):
        return stopped.wait(self.delay)

    def exchange_queued(self, request, epoch):
        with self.guard:
            info = self.endpoint_info()
            if not self.online or epoch != self.epoch or info is None or endpoint_identity(info) != self.inode:
                raise OSError('Owner changed; queued action was not replayed')
            client = self.socket.connect()
        with closing(client):
            client.settimeout(request_timeout(request) + 10)
            client.sendall(encode(request))
            return read_socket(client)

    def close(self):
        self.cancelled.set()
        try: self.cancel_write.send(b'x')
        except OSError: pass
        self.socket.close()

    def dispose(self):
        with self.guard:
            if self.disposed: return
            self.disposed = True
            self.cancel_read.close()
            self.cancel_write.close()
