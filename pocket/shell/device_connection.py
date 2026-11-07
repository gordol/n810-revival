"""An authenticated device attachment composes the existing service clients."""
import shlex
from pathlib import Path
import time

from service_catalog import OWNER_IDS as SERVICES,owner_factory

def attach(directory,target,registry,radio_factory,remote_script='/usr/local/share/n810-pocket/device_services.py'):
    from receive_bridge import _run,_lock,_socket_owned,_read,_write,BridgeError
    # Multiplex only: never silently open a second SSH connection on failure.
    command=['ssh','-S',str(directory/'control'),'-o','ControlMaster=no','-o','BatchMode=yes',
             '-o','ProxyCommand=false',target]
    # Reuse the authenticated master's existing directory forwarding. A healthy
    # attachment needs a protocol request, not another remote Python process.
    import importlib
    registry.configure_reticulum(register=False)
    package='_pocket_reticulum_'+str(abs(hash(str((registry.root/'vendor/apps/domains/reticulum').resolve()))))
    protocol=importlib.import_module(package+'.owner')
    catalogue=None
    with _lock(directory/'services.lock'):
        previous=_read(directory/'services.msgpack') or {}
        local=directory/'system.sock'
        if previous.get('system') and _socket_owned(local):
            try:
                catalogue=protocol.exchange(local,dict(version=1,action='snapshot',scope='directory'))
                if catalogue.get('version')!=1 or not catalogue.get('owner_online') or not catalogue.get('services'):
                    catalogue=None
                else:catalogue['socket']=previous['system']
            except (OSError,ConnectionError,EOFError):pass
    if catalogue is None:
        result=_run(command+['python3 -I '+shlex.quote(remote_script)+' --ensure'],100)
        if result.returncode:raise BridgeError('Device services unavailable: '+result.stderr.decode(errors='replace')[-500:])
        catalogue=importlib.import_module(package+'.wire').decode(result.stdout)
    endpoints={'system':catalogue['socket'],'radio-control':'/dev/shm/n810-radio-read/control.sock'}
    for row in catalogue['services']:
        if row.get('id') in SERVICES and (row.get('available') or row.get('state') in ('starting','ready')) and row.get('socket'):
            endpoints[row['id']]=row['socket']
    forwarded={}
    with _lock(directory/'services.lock'):
        previous=_read(directory/'services.msgpack') or {}
        for name,remote in endpoints.items():
            if not isinstance(remote,str) or not remote.startswith('/') or len(remote.encode())>103 or any(c in remote for c in ':\r\n\x00'):
                raise BridgeError('Invalid device service endpoint')
            local=directory/(name+'.sock')
            if _socket_owned(local) and previous.get(name)!=remote:
                old=previous.get(name)
                if old is None:raise BridgeError('Unrecorded service forwarding endpoint')
                result=_run(command[:3]+['-O','cancel','-L',str(local)+':'+old,target],5)
                if result.returncode:raise BridgeError('Cannot replace previous '+name+' forwarding')
                if _socket_owned(local):local.unlink()
            if not _socket_owned(local):
                result=_run(command[:3]+['-O','forward','-o','StreamLocalBindMask=0177','-L',str(local)+':'+remote,target],5)
                if result.returncode:raise BridgeError('Cannot forward '+name+': '+result.stderr.decode(errors='replace')[-200:])
            forwarded[name]=local
            previous[name]=remote
            _write(directory/'services.msgpack',previous)
    attached=AttachedDevice(radio_factory(),registry,forwarded,catalogue,target)
    attached.dynamic_services=True
    return attached

def from_sockets(directory,registry,radio_factory):
    """Attach a local device bundle; a receive-only folder remains supported."""
    import importlib
    registry.configure_reticulum(register=False)
    package='_pocket_reticulum_'+str(abs(hash(str((registry.root/'vendor/apps/domains/reticulum').resolve()))))
    catalogue=importlib.import_module(package+'.owner').exchange(directory/'system.sock',dict(version=1,action='snapshot'))
    endpoints={name:directory/(name+'.sock') for name in ('system',*SERVICES) if (directory/(name+'.sock')).is_socket()}
    return AttachedDevice(radio_factory(),registry,endpoints,catalogue,str(directory))

def local_telemetry(registry,runtime=None):
    """Read the existing private directory; never start or reconnect an owner."""
    import importlib
    import os
    import stat
    registry.configure_reticulum(register=False)
    package='_pocket_reticulum_'+str(abs(hash(str((registry.root/'vendor/apps/domains/reticulum').resolve()))))
    exchange=importlib.import_module(package+'.wire').exchange
    runtime=Path(runtime) if runtime is not None else Path('/tmp')/('pocket-device-'+str(os.getuid()))
    def collect():
        info=runtime.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
            raise ValueError('Unsafe local device runtime')
        endpoint=runtime/'owner.sock';info=endpoint.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid():
            raise ValueError('Unsafe local device endpoint')
        result=exchange(endpoint,dict(version=1,action='snapshot',scope='directory'))
        if result.get('owner_online') is not True:raise ValueError('Device directory unavailable')
        return result.get('telemetry') or {}
    return collect

class AttachedDevice:
    event_driven=True
    remote=True
    def __init__(self,receive,registry,endpoints,catalogue,label):
        self.receive=receive;self.bindings={};self.catalogue=catalogue;self._wake=None
        self._init_saved_radio()
        self._sample_seen=None;self._sample_due=time.time()+30
        self.catalogue_provider=registry.configure_reticulum(socket_path=endpoints['system'],register=False)
        try:
            for name in SERVICES:
                if name in endpoints:
                    factory=owner_factory(registry,name)
                    self.bindings[name]=factory(socket_path=endpoints[name],register=False)
        except Exception:
            self.close();raise
        self.catalogue_provider.bind_wakeup(self.notify)
        self.receive.bind_wakeup(self.notify)
    def history_page(self,before=None,anchor=None):
        return self.catalogue_provider.transport.exchange(dict(version=1,action='snapshot',scope='history',payload=dict(before=before,anchor=anchor)))

    def notify(self):
        snapshot=self.catalogue_provider.snapshot() if hasattr(self.catalogue_provider,'snapshot') else {}
        system=(snapshot.get('telemetry') or {}).get('system') or {}
        sample=(system.get('boot_id'),system.get('observed_at'))
        if sample[1] is not None and sample!=getattr(self,'_sample_seen',None):
            self._sample_seen=sample;self._sample_due=time.time()+30
        try:
            self.catalogue_provider.drain()
            if hasattr(self.receive,'provider'):self.receive.refresh()
        except OSError:return  # A feed publication can race catalogue shutdown.
        if self._wake:self._wake()
    def bind_wakeup(self,callback):self._wake=callback
    def refresh(self):self.receive.refresh()
    def delay(self,now=None):
        # Peer radio services have their own subscription cadence and timeouts.
        if getattr(self,'gateway',None) is not None:return None
        return max(0.,getattr(self,'_sample_due',time.time()+30)-(time.time() if now is None else now))
    def _init_saved_radio(self):
        self._radio_catalog={};self._radio_revision=None;self._radio_pending=None;self._radio_pool=None;self._radio_error=None;self._radio_retry=0

    def _saved_radio(self,snapshot,now):
        from concurrent.futures import ThreadPoolExecutor
        from radio_catalog import fetch
        pending=getattr(self,'_radio_pending',None)
        if pending is not None and pending.done():
            try:
                revision,catalog=pending.result()
                self._radio_revision=revision;self._radio_catalog=catalog;self._radio_error=None
            except (OSError,ValueError,EOFError,ConnectionError) as error:
                self._radio_error=str(error);self._radio_retry=now+5
            self._radio_pending=None
        manifest=snapshot.get('radio_catalog') or {}
        if manifest.get('error'):self._radio_error=manifest['error']
        if manifest.get('revision') and manifest['revision']!=getattr(self,'_radio_revision',None) and self._radio_pending is None and now>=getattr(self,'_radio_retry',0):
            if getattr(self,'_radio_pool',None) is None:self._radio_pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='radio-catalog')
            def transfer():return manifest['revision'],fetch(self.catalogue_provider.transport.exchange,manifest)
            self._radio_pending=self._radio_pool.submit(transfer)
            self._radio_pending.add_done_callback(lambda _:self._wake() if self._wake else None)
        return getattr(self,'_radio_catalog',{})

    def read(self,now):
        if self.delay(now)==0:
            self._sample_due=now+30
            # A silent stream must not remain apparently connected forever.
            # Reopen just this read-only subscription; retain other owners.
            self.catalogue_provider.transport.close()
        payload=self.receive.read(now)
        snapshot=self.catalogue_provider.snapshot()
        live=dict(payload['live']);data=dict(live.get('data',{}))
        if snapshot.get('owner_online'):
            data.update(snapshot.get('telemetry',{}));self.catalogue=snapshot
        live['data']=data
        catalog=self._saved_radio(snapshot,now)
        return dict(payload,catalog=catalog,live=live,connector=dict(payload.get('connector',{}),device=dict(
            host=self.catalogue.get('device'),connected=bool(snapshot.get('owner_online')),
            services=self.catalogue.get('services',[]),radio_catalog_sync='loading' if self._radio_pending else 'failed: '+self._radio_error if self._radio_error else 'synced' if self._radio_revision else 'waiting for saved catalog')))
    def close(self):
        self._wake=None
        self.receive.bind_wakeup(None)
        self.catalogue_provider.bind_wakeup(None)
        for provider in self.bindings.values():provider.close()
        self.bindings.clear()
        self.catalogue_provider.close();self.receive.close()
        if getattr(self,'_radio_pool',None) is not None:self._radio_pool.shutdown(wait=False,cancel_futures=True)


def from_peer(carrier, peer, registry, directory=None, sources=None):
    """Attach only services granted by the verified peer; keep its gateway alive."""
    from device_feed import ServiceReceive
    import importlib
    registry.configure_reticulum(register=False)
    package='_pocket_reticulum_'+str(abs(hash(str((registry.root/'vendor/apps/domains/reticulum').resolve()))))
    transport=importlib.import_module(package+'.service_transport').ReticulumTransport(carrier.path,peer,'$catalog')
    try:catalogue=transport.exchange(dict(version=1,action='snapshot'))
    finally:transport.close()
    if catalogue.get('error'):raise ValueError(catalogue['error'])
    granted={row['id']:set(row.get('operations',())) for row in catalogue.get('services',())}
    if not {'snapshot','subscribe'}<=granted.get('device',set()):
        raise ValueError('Peer has not shared device read access. On that device, grant Device read in Reticulum → Data.')
    provider=carrier.remote(peer,'device')
    result=AttachedDevice.__new__(AttachedDevice)
    result.bindings={};result.catalogue={};result._wake=None;result.gateway=carrier
    result._init_saved_radio()
    result.catalogue_provider=provider
    result.receive=ServiceReceive(provider,directory,sources)
    try:
        for name in SERVICES:
            if {'snapshot','subscribe'}<=granted.get(name,set()):result.bindings[name]=carrier.remote(peer,name)
        provider.bind_wakeup(result.notify);result.receive.bind_wakeup(result.notify)
        result.notify()
        return result
    except Exception:result.close();raise
