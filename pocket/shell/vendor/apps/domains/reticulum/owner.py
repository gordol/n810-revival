"""Private station-owned Reticulum contact/control socket; no implicit radio start."""
import os
import fcntl
from contextlib import contextmanager, closing
import _socket as socket
import stat
import sys
import time
import _queue as queue

if __package__:
    from .wire import encode, decode, frame_size, read, exchange
else:
    from wire import encode, decode, frame_size, read, exchange

LIMIT = 32768


@contextmanager
def private_lock(path, blocking=True):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Owner lock must be a private user-owned regular file')
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        yield fd
    finally:
        os.close(fd)


class ServiceOwner:
    """Shared event lifecycle without Reticulum contacts or radio state."""
    def __init__(self, state, station):
        self.station = station
        self.revision = 0
        self.last_job = None
        self.events = queue.SimpleQueue()
        self.wake = None

    def post(self, event):
        self.events.put(event)
        if self.wake:
            try:
                self.wake.send(b'x')
            except (BlockingIOError, OSError):
                pass

    def drain(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            self.last_job = event
            self.revision += 1

class Owner(ServiceOwner):
    def __init__(self, state, station):
        if __package__:
            from .contacts import ContactBook
            from .endpoints import token
        else:
            from contacts import ContactBook
            from endpoints import token
        super().__init__(state, token(station, 'station identity'))
        self.book = ContactBook(state)
        self._connection_recovery = None

    def configure_connection_recovery(self, identity, payload, reset_error=False):
        """Resume only a persisted, explicitly requested connection to this target."""
        self._connection_recovery = (identity, payload, reset_error)
        self._connection_timer = None
        self._connection_due = None
        self._connection_delay = 5
        self._connection_stopping = self._connection_internal = False
        self._connection_path = self.book.directory/'connection.msgpack'
        self._connection_record = None
        try:
            fd=os.open(self._connection_path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        except FileNotFoundError:pass
        else:
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>4096:
                    raise ValueError('Unsafe connection intent')
                self._connection_record=decode(stream.read(4097))
            if type(self._connection_record.get('enabled')) is not bool:
                raise ValueError('Invalid connection intent')
        saved=self._connection_record or {}
        self._connection_wanted=saved.get('enabled') is True and saved.get('target')==identity()

    def connection_requested(self, enabled):
        if self._connection_recovery is None or self._connection_internal:return
        record=dict(version=1,target=self._connection_recovery[0](),enabled=enabled)
        if record!=self._connection_record:
            import tempfile
            fd,name=tempfile.mkstemp(prefix='.connection-',dir=self.book.directory)
            try:
                with os.fdopen(fd,'wb') as stream:
                    stream.write(encode(record));stream.flush();os.fsync(stream.fileno())
                os.replace(name,self._connection_path)
            finally:
                if os.path.exists(name):os.unlink(name)
            self._connection_record=record
        self._connection_wanted=enabled
        if not enabled and self._connection_timer is not None:
            self._connection_timer.cancel();self._connection_timer=None
        self._connection_due=None

    def recover_connection(self):
        if self._connection_recovery is None or self._connection_stopping or not self._connection_wanted:return
        phase=self.phase
        if phase=='online':
            self._connection_delay=5;self._connection_due=None
            return
        if phase not in ('idle','error'):return
        if phase=='error':
            if self._connection_due is None:
                self._connection_due=time.monotonic()+self._connection_delay
                self._connection_delay=min(60,self._connection_delay*2)
                import threading
                self._connection_timer=threading.Timer(self._connection_due-time.monotonic(),lambda:self.post(dict(kind='connection_retry')))
                self._connection_timer.daemon=True;self._connection_timer.start()
                return
            if time.monotonic()<self._connection_due:return
        self._connection_due=None
        self._connection_internal=True
        try:
            action='disconnect' if phase=='error' and self._connection_recovery[2] else 'connect'
            self.dispatch(dict(version=1,action=action,payload=self._connection_recovery[1],request_id='resume-'+str(time.time_ns())))
        except (OSError,ValueError) as error:
            self.phase='error';self.error=str(error);self.revision+=1
            self.recover_connection()
        finally:self._connection_internal=False

    def stop_connection_recovery(self):
        if self._connection_recovery is not None:
            self._connection_stopping=True
            if self._connection_timer is not None:self._connection_timer.cancel()

    def snapshot(self):
        return dict(version=1, station_id=self.station, revision=self.revision,
                    owner_online=True, capabilities=['import_peer', 'verify_peer', 'revoke_peer'],
                    peers=self.book.rows()[:16], peers_total=len(self.book.contacts),
                    radios=[], messages=[], packets=[],
                    last_job=self.last_job,
                    radio_status='No Reticulum radio backend attached')

    def dispatch(self, request):
        if not isinstance(request, dict) or request.get('version') != 1:
            raise ValueError('Unsupported Reticulum control version')
        action = request.get('action')
        payload = request.get('payload', {})
        if not isinstance(payload, dict):
            raise ValueError('Invalid Reticulum control payload')
        if action == 'snapshot':
            return self.snapshot()
        if action == 'import_peer' and set(payload) == {'card'}:
            peer = self.book.import_contact(payload['card'])
        elif action == 'verify_peer' and set(payload) == {'peer', 'fingerprint'}:
            peer = payload['peer']
            self.book.verify(peer, payload['fingerprint'])
        elif action == 'revoke_peer' and set(payload) == {'peer'}:
            peer = payload['peer']
            self.book.revoke(peer)
        else:
            raise ValueError('Action is not available on this Reticulum owner')
        self.revision += 1
        self.last_job = dict(id=request.get('request_id'), action=action,
                             state='complete', peer=peer, completed_at=time.time())
        return dict(version=1, job=self.last_job)


def serve(path, state, station, owner_factory=Owner, ready_fd=None, stopped=None):
    """Serve ordinary owners, with optional nonblocking attachment hooks.

    attach_client(client, request) returns a success frame for explicit attach.
    That stream stays open for lifetime only; closing it detaches. detach_client
    runs once for every accepted client, including those without attachments.
    """
    path = os.fspath(path)
    parent=os.path.dirname(path) or '.'
    os.makedirs(parent,mode=0o700,exist_ok=True)
    info=os.lstat(parent)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Owner socket directory must be private (0700)')
    with private_lock(os.path.splitext(path)[0]+'.lifetime.lock', blocking=False):
        return _serve(path, state, station, owner_factory, ready_fd, stopped)


def _serve(path, state, station, owner_factory=Owner, ready_fd=None, stopped=None):
    import selectors
    path = os.fspath(path)
    parent=os.path.dirname(path) or '.'
    os.makedirs(parent,mode=0o700,exist_ok=True)
    info=os.lstat(parent)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Owner socket directory must be private (0700)')
    owner = owner_factory(state, station)
    owner.service_socket = path
    if getattr(owner, 'data_bridge', None) is not None:
        from pathlib import Path
        path=Path(path)
        owner.service_socket=path
        operations = set(owner.snapshot().get('capabilities', ())) | {'send', 'announce', 'rename_peer'}
        operations = {op for op in operations if not op.startswith(('service_', 'data_bridge_'))}
        endpoint = getattr(owner,'service_owner_socket',None) or path
        if endpoint != path: operations |= {'connect','disconnect','pair','save_profile','select_profile','delete_profile'}
        owner.data_bridge.services.register('reticulum', endpoint, operations)
        # Registration is local only; the peer still needs an explicit read grant.
        device_entry=Path(__file__).resolve().parents[4]/'device_services.py'
        if device_entry.is_file():
            def prepare_device():
                import subprocess,sys
                result=subprocess.run([sys.executable,'-I',str(device_entry),'--ensure'],capture_output=True,timeout=100)
                if result.returncode:raise ValueError('Device services unavailable: '+result.stderr.decode(errors='replace')[-240:])
            owner.data_bridge.services.register('device', Path('/tmp')/('pocket-device-'+str(os.getuid()))/'owner.sock', (), prepare=prepare_device)
        configuration = Path(state) / 'service-exports.json'
        if configuration.exists():
            import json
            info = configuration.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('Service export configuration must be private and user-owned')
            if info.st_size > 8192: raise ValueError('Service export configuration exceeds limit')
            for name, item in json.loads(configuration.read_text()).items():
                owner.data_bridge.services.register(name, item['socket'], item['operations'])
    # Refuse any existing endpoint rather than remove somebody else's owner.
    with closing(socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)) as listener:
        listener.bind(str(path))
        os.chmod(path, 0o600)
        identity = os.stat(path).st_ino
        listener.listen(4)
        listener.setblocking(False)
        selector = selectors.DefaultSelector()
        selector.register(listener, selectors.EVENT_READ)
        wake_read, wake_write = socket.socketpair()
        wake_read.setblocking(False)
        wake_write.setblocking(False)
        owner.wake = wake_write
        selector.register(wake_read, selectors.EVENT_READ)
        clients = {}
        workers = None
        # At most four active calls each enqueue one completion.
        completions = queue.SimpleQueue()
        active_calls = set()
        published_revision = owner.revision
        def remote_call(client, request):
            try: result = owner.dispatch(request)
            except Exception as error: result = dict(version=1,error=str(error)[:512])
            completions.put((client,result))
            try: wake_write.send(b'x')
            except OSError: pass


        def disconnect(client):
            if clients.pop(client, None) is None:
                return
            try:
                selector.unregister(client)
            except (KeyError, ValueError, OSError):
                pass
            try:
                detach = getattr(owner, 'detach_client', None)
                if callable(detach):
                    # Also called for observational and malformed clients.
                    # Owners must ignore clients that hold no attachment.
                    detach(client)
            except Exception as error:
                try: print('Owner client detach failed: ' + str(error)[:240], file=sys.stderr)
                except OSError: pass
            finally:
                client.close()

        def publish(client, response):
            try: raw = encode(response)
            except ValueError: raw = encode(dict(version=1,error='Owner snapshot exceeds framing limit'))
            publish_raw(client, raw)

        def publish_raw(client, raw):
            data = clients[client]
            if len(data['output']) + len(raw) > LIMIT * 2:
                disconnect(client)
                return
            data['output'] += raw
            selector.modify(client, selectors.EVENT_READ | selectors.EVENT_WRITE)

        def snapshot_raw():
            try:
                framed = getattr(owner, 'snapshot_frame', None)
                return framed() if framed is not None else encode(owner.snapshot())
            except ValueError:
                return encode(dict(version=1,error='Owner snapshot exceeds framing limit'))

        def broadcast():
            nonlocal published_revision
            revision = owner.revision
            subscribers = [client for client in clients if clients[client]['subscribed'] and not clients[client].get('availability_only')]
            if subscribers:
                raw = snapshot_raw()
                for client in subscribers:
                    publish_raw(client, raw)
            published_revision = revision

        try:
            if ready_fd is not None:
                if callable(ready_fd):ready_fd()
                else:
                    os.write(ready_fd, b'R')
                    os.close(ready_fd)
            recover_connection=getattr(owner,'recover_connection',lambda:None)
            recover_connection()
            while stopped is None or not stopped.is_set():
                for key, mask in selector.select():
                    client = key.fileobj
                    if client is wake_read:
                        wake_read.recv(4096)
                        while True:
                            try: finished, result = completions.get_nowait()
                            except queue.Empty: break
                            active_calls.discard(finished)
                            if finished in clients: publish(finished,result)
                        owner.drain()
                        recover_connection()
                        if owner.revision != published_revision:
                            broadcast()
                        continue
                    if client is listener:
                        fd, _ = listener._accept()
                        try:peer=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM,fileno=fd)
                        except BaseException:
                            os.close(fd);raise
                        if len(clients) >= 8:
                            peer.close()
                            continue
                        peer.setblocking(False)
                        clients[peer] = dict(input=b'', output=b'', subscribed=False, attached=False, handled=False)
                        selector.register(peer, selectors.EVENT_READ)
                        continue
                    data = clients.get(client)
                    if data is None:
                        continue
                    try:
                        if mask & selectors.EVENT_READ:
                            chunk = client.recv(4096)
                            if not chunk:
                                disconnect(client)
                                continue
                            if data['handled']:
                                disconnect(client)
                                continue
                            data['input'] += chunk
                            if len(data['input']) > LIMIT:
                                disconnect(client)
                                continue
                            try: size = frame_size(data['input'])
                            except ValueError:
                                disconnect(client); continue
                            if size is not None and len(data['input']) >= size:
                                data['handled'] = True
                                try:
                                    request = decode(data['input'])
                                    if isinstance(request, dict) and request.get('version') == 1 and request.get('action') == 'subscribe':
                                        scope = request.get('scope', 'state')
                                        if scope not in ('state', 'availability'):
                                            raise ValueError('Unknown subscription scope')
                                        data['subscribed'] = True
                                        data['availability_only'] = scope == 'availability'
                                        if data['availability_only']:
                                            publish(client, dict(version=1,owner_online=True,capabilities=[],scope='availability'))
                                        else:
                                            publish_raw(client, snapshot_raw())
                                    elif (isinstance(request, dict) and type(request.get('version')) is int
                                          and request['version'] == 1 and request.get('action') == 'attach'
                                          and callable(getattr(owner, 'attach_client', None))):
                                        previous = owner.revision
                                        try:
                                            if not callable(getattr(owner, 'detach_client', None)):
                                                raise ValueError('Attachment cleanup hook is required')
                                            response = owner.attach_client(client, request)
                                            if not isinstance(response, dict) or type(response.get('version')) is not int or response['version'] != 1 or response.get('error'):
                                                raise ValueError('Attachment was not accepted')
                                            raw = encode(response)
                                        except Exception as error:
                                            raise ValueError('Attachment failed: ' + str(error)[:400]) from error
                                        data['attached'] = True
                                        publish_raw(client, raw)
                                        if owner.revision != previous:
                                            broadcast()
                                    elif isinstance(request,dict) and request.get('action') in ({'service_call'} | set(getattr(owner,'concurrent_actions',()))):
                                        if len(active_calls)>=4: raise ValueError('Service request limit reached')
                                        if workers is None:
                                            from concurrent.futures import ThreadPoolExecutor
                                            workers = ThreadPoolExecutor(max_workers=4, thread_name_prefix='service-call')
                                        active_calls.add(client)
                                        workers.submit(remote_call,client,request)
                                    else:
                                        previous = owner.revision
                                        publish(client, owner.dispatch(request))
                                        if owner.revision != previous:
                                            broadcast()
                                except (ValueError, KeyError, TypeError, OSError) as error:
                                    publish(client, dict(version=1, error=str(error)[:512]))
                        if client in clients and mask & selectors.EVENT_WRITE:
                            data = clients[client]
                            sent = client.send(data['output'])
                            data['output'] = data['output'][sent:]
                            if not data['output']:
                                response_sent=getattr(owner,'response_sent',None)
                                if response_sent is not None:response_sent()
                                if not data['subscribed'] and not data['attached']:
                                    disconnect(client)
                                else:
                                    selector.modify(client, selectors.EVENT_READ)
                    except (ConnectionError, OSError):
                        if client in clients:
                            disconnect(client)
        finally:
            for client in list(clients):
                disconnect(client)
            if workers is not None:workers.shutdown(wait=False, cancel_futures=True)
            selector.close()
            wake_read.close()
            wake_write.close()
            owner.wake = None
            if os.path.exists(path) and os.stat(path).st_ino == identity:
                os.unlink(path)
            if hasattr(owner, 'close'):
                owner.close()


if __name__ == '__main__':
    import argparse
    import signal
    def stop(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket', required=True)
    parser.add_argument('--state', required=True)
    parser.add_argument('--station', required=True)
    args = parser.parse_args()
    serve(args.socket, args.state, args.station)
