"""Small, persistent receive-only OpenSSH bridge. No device service is started.

ensure() returns a directory containing aprs.sock and replay.sock. The dedicated
SSH master survives desktop exit; stop() is explicit. Only records created here
are eligible for reuse or cleanup. No discovery, TX forwarding or remote shell.
"""
import contextlib
import fcntl
import hashlib
from runtime_codec import pack,unpack
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import subprocess
import tempfile
import threading
import time

DEFAULT_TARGET = 'nokia@10.10.30.80'
USB_TARGET = 'nokia@192.168.10.1'
N810_HOST_KEY_ALIAS = '10.10.30.80'
DEFAULT_KEY = '~/.ssh/id_rsa_n810'
REMOTE_PATHS = {'aprs.sock': '/dev/shm/n810-aprs.sock',
                'replay.sock': '/dev/shm/n810-aprs-replay.sock'}


class BridgeError(RuntimeError):
    pass


def ensure_preferred(target=None,key=None,runtime=None,report=None,require_receive=True):
    """Select at launch only; explicit targets never fall back to another host."""
    errors=[]
    for candidate in ((target,) if target else (USB_TARGET,DEFAULT_TARGET)):
        if report:report('Connecting receive bridge via '+('USB' if candidate==USB_TARGET else 'Wi-Fi' if candidate==DEFAULT_TARGET else candidate)+'…')
        try:
            directory=ensure(target=candidate,key=key,runtime=runtime,require_receive=require_receive)
            if report:report('Receive bridge: '+candidate)
            return directory,candidate
        except BridgeError as error:
            errors.append(candidate+': '+str(error))
            if report:report('Receive bridge unavailable: '+candidate)
    raise BridgeError(('No receive connection available.' if require_receive else 'SSH device connection failed.')+'\n'+'\n'.join(errors))


def _configuration(target, key):
    target = target or DEFAULT_TARGET
    if not isinstance(target, str) or not re.fullmatch(r'[A-Za-z0-9_@.:[\]-]+', target) or target.startswith('-'):
        raise BridgeError('Use an SSH host or user@host, without command options.')
    return {'version': 1, 'target': target,
            'key': str(Path(key or DEFAULT_KEY).expanduser().absolute()),
            'remote_paths': REMOTE_PATHS}


def _private_directory(path):
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise BridgeError('Bridge directory must be owned by you with permissions 0700: ' + str(path))
    except OSError as error:
        raise BridgeError('Cannot use private bridge directory: ' + str(error)) from error


def _paths(config, runtime):
    root = Path(runtime) if runtime is not None else Path('/tmp') / ('cw-rx-' + str(os.getuid()))
    root = root.absolute()
    _private_directory(root)
    identity=hashlib.sha256(pack((config['version'],config['target'],config['key'],tuple(sorted(config['remote_paths'].items()))))).hexdigest()[:16]
    record=root/(identity+'.msgpack')
    if not record.exists():
        # Reuse an earlier authenticated master under its existing lock/name.
        # Binary records take precedence, so migration is a one-way read.
        for suffix in ('.msgpack','.json'):
            for candidate in sorted(root.glob('*'+suffix)):
                if not re.fullmatch(r'[0-9a-f]{16}',candidate.stem):continue
                try:prior=_read(candidate)
                except BridgeError:continue  # Never alter an unrelated/unreadable registry.
                if isinstance(prior,dict) and prior.get('config')==config:
                    identity=candidate.stem;break
            else:continue
            break
    return root, root/(identity+'.msgpack'),root/(identity+'.lock')


@contextlib.contextmanager
def _lock(path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise BridgeError('Unsafe bridge lock: ' + str(path))
        # A valid repair may spend 12s checking retained endpoints, then stop,
        # reconnect and check again. Wait longer than that bounded operation.
        deadline = time.monotonic() + 45
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise BridgeError('Another desktop is setting up this bridge; try again shortly.')
                time.sleep(.05)
        yield
    finally:
        os.close(fd)


def _binary_path(path):
    path=Path(path)
    return path.with_suffix('.msgpack') if path.suffix=='.json' else path


def _read(path):
    path=_binary_path(path)
    if not path.exists() and not path.is_symlink() and path.suffix=='.msgpack':path=path.with_suffix('.json')
    try:
        info = path.lstat()
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size > 8192:
            raise BridgeError('Unsafe bridge ownership record: ' + str(path))
        raw=path.read_bytes()
        if raw.lstrip().startswith(b'{'):
            from legacy_state import decode
            return decode(raw)
        return unpack(raw,8192)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise BridgeError('Cannot read bridge ownership record: ' + str(path)) from error


def _write(path, value):
    path=_binary_path(path)
    fd, temporary = tempfile.mkstemp(prefix='.record-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(pack(value))
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _owned(record, config, root):
    if not isinstance(record, dict) or record.get('config') != config:
        raise BridgeError('Bridge record has a different target or forwarding configuration; refusing to replace it.')
    directory = Path(record.get('directory', ''))
    if directory.parent != root or not re.fullmatch(r'b-[0-9a-f]{12}', directory.name):
        raise BridgeError('Bridge record points outside its private registry.')
    if not os.path.lexists(directory):
        return directory  # A removed temporary directory leaves a harmless stale record.
    _private_directory(directory)
    if _read(directory / 'owner.json') != record:
        raise BridgeError('Bridge owner marker does not match; refusing to touch it.')
    return directory


def _run(command, timeout):
    try:
        return subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BridgeError('SSH bridge command failed: ' + str(error)) from error


def _master(directory, target, operation):
    result = _run(['ssh', '-S', str(directory / 'control'), '-O', operation, target], 3)
    return result.returncode == 0


def _socket_owned(path):
    try:
        info = path.lstat()
        return stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077
    except FileNotFoundError:
        return False


def _ready(directory):
    # A byte of retained RX/snapshot data verifies the remote endpoint too. We
    # never send application bytes. Cold N810 endpoints can need more than a
    # second. Share one deadline so two slow endpoints cannot double the wait.
    deadline = time.monotonic() + 12
    for name in REMOTE_PATHS:
        path = directory / name
        if not _socket_owned(path):
            return False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                client.settimeout(min(8, remaining))
                client.connect(str(path))
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                client.settimeout(min(8, remaining))
                if not client.recv(1):
                    return False
        except OSError:
            return False
    return True


def _clear_sockets(directory):
    # Called only after ownership verification, and after the master is stopped.
    for name in (*REMOTE_PATHS, 'system.sock', 'reticulum.sock', 'meshcore.sock', 'control'):
        path = directory / name
        if path.exists():
            if not _socket_owned(path):
                raise BridgeError('Unexpected file in owned bridge; leaving it alone: ' + str(path))
            path.unlink()


def _remove_metadata(path):
    canonical=_binary_path(path)
    for candidate in (canonical,canonical.with_suffix('.json')):
        try:info=candidate.lstat()
        except FileNotFoundError:continue
        if info.st_uid!=os.getuid() or not stat.S_ISREG(info.st_mode) or info.st_mode&0o077:
            raise BridgeError('Unsafe obsolete bridge record: '+str(candidate))
        candidate.unlink()


def _cleanup(directory, record_path):
    _clear_sockets(directory)
    _remove_metadata(directory/'owner.msgpack')
    _remove_metadata(directory/'services.msgpack')
    lock=directory/'services.lock'
    if lock.exists():
        with _lock(lock):lock.unlink()
    try:
        directory.rmdir()
    except OSError:
        pass  # Never remove unknown files, even in our own directory.
    _remove_metadata(record_path)


def ensure(target=None, key=None, runtime=None, require_receive=True):
    """Reuse or start an owned bridge; return its Path. Errors are BridgeError."""
    config = _configuration(target, key)
    root, record_path, lock_path = _paths(config, runtime)
    with _lock(lock_path):
        record = _read(record_path)
        reusing = record is not None
        directory = None
        if record is not None:
            directory = _owned(record, config, root)
            if _master(directory, config['target'], 'check'):
                if not require_receive or _ready(directory):
                    _write(directory/'owner.msgpack',record);_write(record_path,record)
                    return directory
                # Only our verified private master is eligible for repair.
                # Keep socket paths stable: running apps reconnect to these.
                if not _master(directory, config['target'], 'exit'):
                    raise BridgeError('Could not stop the stale owned receive bridge; record retained.')
            _clear_sockets(directory)
        if directory is None:
            directory = root / ('b-' + secrets.token_hex(6))
        directory.mkdir(mode=0o700, exist_ok=True)
        if len(os.fsencode(directory / 'replay.sock')) > 103:
            directory.rmdir()
            raise BridgeError('Bridge runtime path is too long for Unix sockets; use a short private runtime directory.')
        record = {'config': config, 'directory': str(directory), 'token': secrets.token_hex(16)}
        _write(directory / 'owner.json', record)
        _write(record_path, record)
        try:connect_timeout=int(os.environ.get('POCKET_SSH_CONNECT_TIMEOUT','15'))
        except ValueError:raise BridgeError('POCKET_SSH_CONNECT_TIMEOUT must be an integer') from None
        if not 1<=connect_timeout<=120:raise BridgeError('POCKET_SSH_CONNECT_TIMEOUT must be between 1 and 120 seconds')
        command = ['ssh', '-fMN', '-S', str(directory / 'control'), '-i', config['key'],
                   '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout='+str(connect_timeout),
                   '-o', 'ExitOnForwardFailure=yes', '-o', 'StreamLocalBindMask=0177',
                   '-o', 'StreamLocalBindUnlink=no', '-o', 'ServerAliveInterval=30',
                   '-o', 'ServerAliveCountMax=3']
        if config['target'] in (USB_TARGET,DEFAULT_TARGET):
            command += ['-o','HostKeyAlias='+N810_HOST_KEY_ALIAS]
        for name, remote in REMOTE_PATHS.items():
            command += ['-L', str(directory / name) + ':' + remote]
        command.append(config['target'])
        try:
            result = _run(command, connect_timeout+4)
            if result.returncode:
                detail = result.stderr.decode(errors='replace').strip()[-600:]
                reason='SSH did not respond before the timeout' if 'timed out' in detail.lower() or 'banner exchange' in detail.lower() else 'SSH authentication failed' if 'Permission denied' in detail else 'SSH host key was not accepted' if 'Host key verification failed' in detail else 'SSH connection failed'
                raise BridgeError(reason+' for '+config['target']+'.\n'+detail)
            if not _master(directory, config['target'], 'check') or (require_receive and not _ready(directory)):
                raise BridgeError('SSH connected to '+config['target']+', but receive endpoints did not become ready: '+', '.join(REMOTE_PATHS.values())+'. One owned bridge repair was attempted; remote services were not restarted.')
            return directory
        except BridgeError:
            # A timed-out startup may still have created its master. Address
            # only this invocation's private control socket, never other SSH.
            if _socket_owned(directory / 'control'):
                try:
                    if not _master(directory, config['target'], 'exit'):
                        raise BridgeError('Could not stop failed bridge; ownership record retained for explicit stop.')
                except BridgeError:
                    raise BridgeError('Bridge setup failed; owned master could not be stopped. Retry stop() for ' + str(directory))
            if reusing:
                _clear_sockets(directory)  # Preserve paths across bounded retry.
            else:
                _cleanup(directory, record_path)
            raise


class Recovery:
    """One launcher-owned worker; bounded checks/retries, no remote service control."""
    def __init__(self, directory, target=None, key=None, runtime=None):
        self.directory=Path(directory);self.target=target;self.key=key;self.runtime=runtime
        self.stopped=threading.Event();self.thread=None
        self.status_path=self.directory.parent/(self.directory.name+'-status.msgpack')
        self._status(True, '')

    def _status(self, online, error):
        _write(self.status_path, dict(online=online,error=error,source=self.target or DEFAULT_TARGET,observed=time.time()))

    def check(self):
        try:
            if _master(self.directory,self.target or DEFAULT_TARGET,'check') and _ready(self.directory):
                self._status(True,'');return True
            self._status(False,'Receive bridge reconnecting')
            directory=ensure(self.target,self.key,self.runtime)
            if directory!=self.directory:
                # Refuse to attach clients to a different bridge identity.
                raise BridgeError('Receive bridge path changed; relaunch the desktop to use '+str(directory))
            self._status(True,'');return True
        except BridgeError as error:
            self._status(False,str(error));return False

    def _work(self):
        delay=15
        while not self.stopped.wait(delay):
            delay=15 if self.check() else min(60,delay*2)

    def start(self):
        self.thread=threading.Thread(target=self._work,name='receive-recovery',daemon=True)
        self.thread.start();return self

    def close(self):
        self.stopped.set()


def radio_status(directory):
    """Read one fixed owner file through our existing authenticated master only."""
    directory=Path(directory).absolute()
    record=_read(directory/'owner.json')
    if not record:raise BridgeError('Receive bridge ownership unavailable')
    saved=record.get('config',{})
    config=_configuration(saved.get('target'),saved.get('key'))
    root,registry,_=_paths(config,directory.parent)
    if _read(registry)!=record or _owned(record,config,root)!=directory or not _socket_owned(directory/'control'):
        raise BridgeError('Receive bridge owner/control mismatch')
    # ProxyCommand=false prevents ssh from silently opening another connection
    # if the existing master disappears between validation and multiplexing.
    result=_run(['ssh','-S',str(directory/'control'),'-o','ControlMaster=no',
                 '-o','BatchMode=yes','-o','ProxyCommand=false',config['target'],
                 'head -c 65537 /dev/shm/n810-radio-live.json'],5)
    if result.returncode:raise BridgeError('Radio owner status unavailable through receive bridge')
    if len(result.stdout)>65536:raise BridgeError('Radio owner status exceeds 64 KiB')
    try:
        from legacy_state import decode
        value=decode(result.stdout)
    except (ValueError,UnicodeError) as error:raise BridgeError('Invalid radio owner status') from error
    if not isinstance(value,dict):raise BridgeError('Invalid radio owner status')
    return value


class Status:
    """Small client-local recovery banner, sampled at most once per second."""
    def __init__(self,path):
        self.path=Path(path);self.due=0;self.online=False;self.error='Receive bridge status unavailable'

    def update(self,now):
        if now<self.due:return
        self.due=now+1
        try:
            value=_read(self.path)
            self.online=bool(value and value.get('online') is True and time.time()-value['observed']<120)
            self.error='' if self.online else (value or {}).get('error','Receive bridge status unavailable')
        except (BridgeError,KeyError,TypeError,ValueError):
            self.online=False;self.error='Receive bridge status unavailable'


def stop(target=None, key=None, runtime=None):
    """Stop only the matching recorded master. Return False if none is owned."""
    config = _configuration(target, key)
    root, record_path, lock_path = _paths(config, runtime)
    with _lock(lock_path):
        record = _read(record_path)
        if record is None:
            return False
        directory = _owned(record, config, root)
        if _master(directory, config['target'], 'check') and not _master(directory, config['target'], 'exit'):
            raise BridgeError('SSH did not stop its owned bridge; record retained.')
        _cleanup(directory, record_path)
        return True


def forward_radio_control(directory):
    """Add only the explicit radio-control socket to an owned SSH master."""
    directory=Path(directory).absolute();record=_read(directory/'owner.json')
    if not record:raise BridgeError('Receive bridge ownership unavailable')
    saved=record.get('config',{});config=_configuration(saved.get('target'),saved.get('key'))
    root,registry,_=_paths(config,directory.parent)
    if _read(registry)!=record or _owned(record,config,root)!=directory or not _socket_owned(directory/'control'):
        raise BridgeError('Receive bridge owner/control mismatch; reconnect Device in Connections')
    local=directory/'radio-control.sock';remote='/dev/shm/n810-radio-read/control.sock'
    with _lock(directory/'services.lock'):
        if not _socket_owned(local):
            result=_run(['ssh','-S',str(directory/'control'),'-O','forward','-o','StreamLocalBindMask=0177','-L',str(local)+':'+remote,config['target']],5)
            if result.returncode:raise BridgeError('Radio control forwarding failed; reconnect Device in Connections')
        services=_read(directory/'services.msgpack') or {};services['radio-control']=remote
        _write(directory/'services.msgpack',services)
    return local
