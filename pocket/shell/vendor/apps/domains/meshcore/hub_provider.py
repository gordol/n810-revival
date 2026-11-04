"""Existing managed-owner client plus explicit per-service lifetime streams."""
import os
from pathlib import Path
import re
import socket
import stat
import sys
import threading
import time
import tomllib

# Both native app packages and direct owner executables use this client.
sys.path.insert(0,str(Path(__file__).resolve().parents[4]))
from vendor.apps.domains.reticulum.provider import Provider
from vendor.apps.domains.reticulum.local_owner import ManagedOwner,private_lock
from vendor.apps.domains.reticulum.wire import encode,read_socket
from vendor.apps.domains.meshcore.hub_owner import canonical_port,hub_identity


def state_root(directory=None):
    if directory is None:
        base=Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))
        directory=base/'pocket-hubs'
    root=Path(directory)
    if not root.is_absolute():raise ValueError('Hub state must use an absolute path')
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    info=root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('Hub state must be private and user-owned')
    return root


def configured_port(identity,directory=None):
    if not isinstance(identity,str) or not re.fullmatch(r'[0-9a-f]{24}',identity):raise ValueError('Choose a configured hub ID')
    root=state_root(directory)/identity
    info=root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('Unsafe configured hub directory')
    fd=os.open(root/'device.toml',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>1024:raise ValueError('Unsafe hub device configuration')
        config=tomllib.loads(stream.read(1025).decode())
    if set(config)!={'version','port'} or type(config['version']) is not int or config['version']!=1:raise ValueError('Unsupported hub device configuration')
    port=canonical_port(config['port'])
    if hub_identity(port)!=identity:raise ValueError('Hub configuration does not match selected ID')
    return port


def configure(port,directory=None):
    port=canonical_port(port);identity=hub_identity(port);root=state_root(directory)/identity
    root.mkdir(mode=0o700,exist_ok=True)
    info=root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('Unsafe configured hub directory')
    with private_lock(root/'configure.lock'):
        path=root/'device.toml'
        if not path.exists() and not path.is_symlink():
            # canonical_port's alphabet excludes TOML escapes and quotes.
            raw=('version = 1\nport = "'+port+'"\n').encode()
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        if configured_port(identity,directory)!=port:raise ValueError('Configured hub changed')
    return identity,root


def configured_hubs(directory=None):
    base=Path(directory) if directory is not None else Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'pocket-hubs'
    if not base.exists():return []
    root=state_root(base);result=[]
    for path in sorted(root.iterdir()):
        if not re.fullmatch(r'[0-9a-f]{24}',path.name):continue
        try:port=configured_port(path.name,root)
        except (OSError,ValueError):continue
        result.append(dict(id=path.name,label='HTIT '+port,port='hub://'+path.name+'/3'))
        if len(result)>=16:break
    return result


class HubProvider(Provider):
    def __init__(self,port=None,*,hub_id=None,directory=None,interpreter=None):
        if (port is None)==(hub_id is None):raise ValueError('Choose one physical device or configured hub ID')
        if hub_id is not None:port=configured_port(hub_id,directory)
        identity,root=configure(port,directory)
        self.hub_id=identity;self.changed=threading.Event()
        path=root/'owner.sock';port=canonical_port(port)
        command=[interpreter or sys.executable,'-B',str(Path(__file__).with_name('hub_owner.py')),
                 '--socket',str(path),'--state',str(root),'--station','hub-'+identity,'--port',port]
        def validate(existing):
            if existing.get('service_type')!='wireless-hub' or existing.get('hub_id')!=identity or existing.get('port')!=port:raise ValueError('Existing hub owner does not match configured device')
        transport=ManagedOwner(path,dict(service='wireless-hub',hub_id=identity),lambda:(command,validate))
        super().__init__(path,transport=transport)

    def _publish(self,state):
        super()._publish(state);self.changed.set()

    def close(self):
        self.changed.set()
        super().close()

    def wait(self,predicate,timeout,stopped=None):
        until=time.monotonic()+timeout
        while not self.stopped.is_set():
            self.changed.clear()
            if stopped is not None and stopped.is_set():raise InterruptedError('Hub attachment cancelled')
            state=self.snapshot()
            result=predicate(state)
            if result:return result
            remaining=until-time.monotonic()
            if remaining<=0:raise TimeoutError('Hub owner readiness timed out')
            self.changed.wait(min(remaining,.5) if stopped is not None else remaining)
        raise ConnectionError('Hub provider closed')

    def attach(self,service,*,timeout=90,stopped=None,**options):
        self.wait(lambda s:s.get('owner_online') and s.get('service_type')=='wireless-hub',timeout,stopped)
        client=self.transport.socket.connect()
        try:
            client.settimeout(20)
            client.sendall(encode(dict(version=1,action='attach',payload=dict(service=service,**options))))
            response=read_socket(client)
            if response.get('error') or not all(isinstance(response.get(key),str) for key in ('token','instance')):
                raise ConnectionError(response.get('error') or 'Hub rejected the service attachment')
            client.settimeout(None)
            attachment=HubAttachment(self,client,response['token'],response['instance'],service)
            attachment.wait_ready(timeout,stopped)
            return attachment
        except BaseException:client.close();raise


class HubAttachment:
    def __init__(self,provider,client,token,instance,service):
        self.provider,self.client,self.token,self.instance,self.service=provider,client,token,instance,service
        self.port=None;self.generation=None;self.closed=False

    def wait_ready(self,timeout=90,stopped=None):
        def ready(state):
            if state.get('owner_online') and state.get('instance')!=self.instance:raise ConnectionError('Hub owner restarted; reconnect explicitly')
            item=next((v for v in state.get('attachments',[]) if v.get('token')==self.token),None)
            if item and item.get('state') in ('error','detached'):raise ConnectionError(item.get('error') or 'Hub service detached')
            if item and item.get('state')=='ready':
                port=item.get('port','')
                if not re.fullmatch(r'/dev/(?:pts/[0-9]+|ttys[0-9]+)',port):raise ValueError('Invalid local hub endpoint')
                self.port=port;self.generation=item['generation'];return self
        return self.provider.wait(ready,timeout,stopped)

    def snapshot(self):
        state=self.provider.snapshot()
        if self.closed:raise ConnectionError('Hub attachment closed')
        if not state.get('owner_online') or state.get('instance')!=self.instance:
            raise ConnectionError('Hub connection owner disconnected; reconnect explicitly')
        item=next((v for v in state.get('attachments',[]) if v.get('token')==self.token),None)
        if not item or item.get('state')!='ready' or item.get('generation')!=self.generation:
            raise ConnectionError((item or {}).get('error') or 'Hub service disconnected; reconnect explicitly')
        return state

    def close(self):
        if self.closed:return
        self.closed=True
        try:self.client.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        self.client.close()
        self.provider.close()


def attach_hub(service,*,port=None,hub_id=None,directory=None,interpreter=None,timeout=90,stopped=None,**options):
    provider=HubProvider(port,hub_id=hub_id,directory=directory,interpreter=interpreter)
    try:return provider.attach(service,timeout=timeout,stopped=stopped,**options)
    except BaseException:provider.close();raise
