"""Explicit receive-service selection through the existing source contract."""
from pathlib import Path
import threading
from service_catalog import OWNER_IDS


class Connections:
    event_driven = True
    remote = False

    def __init__(self, directory, sources, runtime, factory=None):
        self.directory = Path(directory)
        self.sources = Path(sources)
        self.runtime = Path(runtime)
        self.factory = factory or self._connect
        self.source = None
        self.transport = None
        self.label = 'Local shell'
        self.suggested_address = ''
        self.ssh_key = None
        self.error = ''
        self.busy = False
        self.closed = False
        self.generation = 0
        self._wake = None
        self._view_wake = None
        self._lock = threading.RLock()
        self._pool = None
        self._future = None
        self._intent = None
        self._retry = None
        self._retry_delay = 1
        self._retry_failed = False
        self._local_start = None

    def attach_local_services(self):
        # Even worker setup imports must not hold the first screen's input loop.
        with self._lock:
            if self.closed or self._local_start is not None:return
            self._local_start=threading.Thread(target=self._attach_local_services,
                name='local-services',daemon=True)
            self._local_start.start()

    def _attach_local_services(self):
        # Load the existing executor before taking connection/selection locks:
        # their snapshots and cancellation remain available during cold imports.
        from concurrent.futures import ThreadPoolExecutor
        # Local observation and idle owners only; no saved remote endpoint replay.
        with self._lock:
            if self.closed or self.generation!=0:return
            if self.source is None and not self.busy:self.connect('local')
        for name in OWNER_IDS:
            selection=getattr(self,name,None)
            if selection is not None:
                with selection.lock:
                    if selection.generation==0 and selection.provider is None and not selection.busy:
                        selection.connect('local-auto')

    def bind_wakeup(self, callback):
        self._wake = callback

    def _needs_recovery(self):
        if self._retry_failed:return True
        provider=getattr(self.source,'catalogue_provider',None)
        if provider is None:return self.source is None
        snapshot=provider.snapshot()
        if not snapshot.get('owner_online'):return True
        # Owners can become ready after the device itself. Attach the new
        # service bundle without requiring another user connection action.
        if not getattr(self.source,'dynamic_services',False):return False
        adopted=getattr(self.source,'adopted',{})
        return any((row.get('available') or row.get('state')=='starting' and row.get('socket')) and row.get('id') in OWNER_IDS and row['id'] not in adopted and row['id'] not in getattr(self.source,'suppressed_services',())
                   for row in snapshot.get('services',()))

    def _schedule_recovery(self):
        with self._lock:
            if self.closed or self._intent is None or self.busy or self._retry is not None:return
            if self.source is None or not self._needs_recovery():return
            self._queue_retry()

    def _queue_retry(self):
        if self._retry is not None or self._intent is None or self.closed:return
        generation=self.generation
        def retry():
            with self._lock:
                self._retry=None
                if self.closed or generation!=self.generation or self._intent is None:return
                if not self._needs_recovery():
                    self._retry_delay=1
                    return
                if self._future is not None and not self._future.done():
                    self._queue_retry();return
                kind,address=self._intent
                self.connect(kind,address,_recovery=True)
        self._retry=threading.Timer(self._retry_delay,retry)
        self._retry.daemon=True
        self._retry_delay=min(15,self._retry_delay*2)
        self._retry.start()

    def notify(self):
        self._schedule_recovery()
        for callback in (self._wake, self._view_wake):
            if callback is not None and not self.closed:
                callback()

    def _connect(self, kind, address):
        from console_source import Source
        if kind == 'ssh':
            from receive_bridge import ensure_preferred
            root, target = ensure_preferred(target=address or None, key=self.ssh_key, runtime=self.runtime / 'ssh',require_receive=False)
            from device_connection import attach
            return attach(root,target,self.reticulum.registry,lambda:Source(root/'aprs.sock',root/'replay.sock',directory=self.directory,sources=self.sources,bridge=root)),target
        if kind == 'socket':
            root = Path(address).expanduser().resolve()
            if (root/'system.sock').is_socket():
                from device_connection import from_sockets
                return from_sockets(root,self.reticulum.registry,lambda:Source(root/'aprs.sock',root/'replay.sock',directory=self.directory,sources=self.sources)),str(root)
            if not all((root / name).is_socket() for name in ('aprs.sock', 'replay.sock')):
                raise ValueError('Choose a folder containing aprs.sock and replay.sock')
            return Source(root / 'aprs.sock', root / 'replay.sock', directory=self.directory,
                          sources=self.sources), str(root)
        if kind == 'peer':
            from device_connection import from_peer
            carrier=self.reticulum.carrier or self.reticulum.provider
            if carrier is None:raise ValueError('Attach a local Reticulum owner first')
            peer=address.strip()
            return from_peer(carrier,peer,self.reticulum.registry,self.directory,self.sources),'Reticulum peer '+peer
        if kind == 'local':
            from device_radio_source import DeviceSource
            from device_connection import local_telemetry
            registry=getattr(getattr(self,'reticulum',None),'registry',None)
            try:shared=local_telemetry(registry) if registry is not None else None
            except ImportError:shared=None
            return DeviceSource(directory=self.directory, sources=self.sources, shared_telemetry=shared), 'Local services'
        raise ValueError('Unknown transport')

    def connect(self, kind, address='', _recovery=False):
        with self._lock:
            if self.closed or self.busy or self._future is not None and not self._future.done():
                return False
            if self._retry is not None:self._retry.cancel();self._retry=None
            self._intent=(kind,address)
            if not _recovery:self._retry_delay=1;self._retry_failed=False
            self.generation += 1
            generation = self.generation
            self.busy = True
            self.error = ''
            if self._pool is None:
                from concurrent.futures import ThreadPoolExecutor
                self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='service-connect')
            self._future = self._pool.submit(self._run, generation, kind, address, _recovery)
            self._future.add_done_callback(lambda future: self.notify())
        self.notify()
        return True

    def _run(self, generation, kind, address, recovery=False):
        discarded = []
        candidate = None
        old = None
        try:
            candidate, label = self.factory(kind, address)
            with self._lock:
                if self.closed or generation != self.generation:
                    return
                old = self.source
                preserved=set(getattr(old,'suppressed_services',())) if recovery else set()
                if recovery:
                    for name,(provider,revision) in getattr(old,'service_choices',{}).items():
                        selection=getattr(self,name,None)
                        if selection is not None and (selection.provider is not provider or getattr(selection,'generation',None)!=revision):
                            preserved.add(name)
                self._detach_bindings(old, preserve=getattr(candidate,'gateway',None), skip=preserved)
                candidate.adopted = {}
                candidate.suppressed_services=preserved
                for name,provider in list(getattr(candidate,'bindings',{}).items()):
                    if name in preserved:
                        discarded.append(provider);del candidate.bindings[name];continue
                    getattr(self,name).adopt(provider,label,carrier=getattr(candidate,'gateway',None) if name=='reticulum' else None)
                    candidate.adopted[name]=provider
                    del candidate.bindings[name]
                candidate.service_choices={name:(getattr(self,name).provider,getattr(getattr(self,name),'generation',None))
                                           for name in OWNER_IDS if hasattr(getattr(self,name,None),'provider')}
                self.source = candidate
                candidate = None
                self.source.bind_wakeup(self.notify)
                self.label = label
                self.remote = kind in ('ssh','peer')
                self.transport = kind
                self._retry_failed = False
                self.busy = False
        except Exception as error:
            with self._lock:
                if generation == self.generation and not self.closed:
                    self.error = str(error)
                    self.busy = False
                    from receive_bridge import BridgeError
                    if isinstance(error,(OSError,EOFError,BridgeError)):
                        self._retry_failed=True
                        self.error += "; retrying automatically"
                        self._queue_retry()
        finally:
            for provider in discarded:provider.close()
            for source in (candidate, old):
                if source is not None:
                    source.bind_wakeup(None)
                    source.close()
            self.notify()

    def _detach_bindings(self, source, preserve=None, skip=()):
        for name,provider in getattr(source,'adopted',{}).items():
            if name in skip:continue
            selection=getattr(self,name,None)
            if selection is not None and selection.provider is provider:
                if provider is preserve:continue
                carrier=getattr(selection,'carrier',None)
                if carrier is not None:selection.adopt(carrier,'Local Reticulum gateway')
                else:selection.disconnect()

    def disconnect(self):
        with self._lock:
            self.generation += 1
            self._intent=None
            if self._retry is not None:self._retry.cancel();self._retry=None
            source, self.source = self.source, None
            self._detach_bindings(source)
            self.busy = False
            self.remote = False
            self.transport = None
            self.label = 'Local shell'
            self.error = ''
            if source is not None:
                source.bind_wakeup(None)
                self._pool.submit(source.close)
        self.notify()

    @property
    def receive(self):
        return self

    @property
    def control(self):
        source = getattr(self.source, 'receive', self.source)
        return getattr(source, 'control', None)

    @property
    def feed_control(self):
        return self.control.snapshot if self.control else None

    @property
    def feed_control_online(self):
        return bool(self.control and self.control.online)

    @property
    def owner_context(self):
        return self.control.owner_context if self.control else None

    def history_page(self,before=None,anchor=None):
        source=self.source
        method=getattr(source,'history_page',None)
        if method is None:raise ValueError('This connection does not provide packet history')
        return method(before,anchor=anchor)

    def request_feed_control(self, action):
        return bool(self.control and self.control.request(action))

    def delay(self,now=None):
        method=getattr(self.source,'delay',None)
        return method(now) if method is not None else None

    def refresh(self):
        if self.source is not None:
            self.source.refresh()

    def read(self, now):
        source = self.source
        payload=source.read(now) if source is not None else dict(catalog={},live=dict(data=dict(
            packets=[],raw_records=[],receive_connected=False,receive_subscription=False,captured=None)),connector={})
        live=payload.get('live',{});data=live.get('data',live)
        from system_links import project
        meshcore=getattr(self,'meshcore',None)
        data=dict(data,connectivity=project(data,meshcore.snapshot() if meshcore is not None else None,now=now))
        payload=dict(payload,live=dict(live,data=data))
        attachment=dict(service='device' if payload.get('connector',{}).get('device') else 'receive',owner=self.label if source is not None else None,
                        transport=self.transport,attached=source is not None,
                        connected=payload.get('connector',{}).get('device',{}).get('connected',data.get('receive_connected') is True),busy=self.busy,error=self.error)
        return dict(payload,connector=dict(payload.get('connector') or {},attachment=attachment))

    def close(self):
        if self.closed:
            return
        self.disconnect()
        self.closed = True
        self._wake = self._view_wake = None
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=False)
