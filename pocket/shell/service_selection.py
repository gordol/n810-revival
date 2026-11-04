"""Stable application provider with explicit asynchronous owner selection."""
from pathlib import Path
import _socket as socket
import threading


class Selection:
    def __init__(self, registry, state, initial=None, service_name="reticulum"):
        self.service_name=service_name
        self.registry, self.state_directory = registry, Path(state)
        self.provider = initial
        self.carrier = None
        self.label = 'Configured owner' if initial else 'Not attached'
        self.error = ''
        self.busy = self.closed = False
        self.generation = 0
        self.lock = threading.RLock()
        self.pool = self.future = None
        self.retired = []
        self.readable, self.writable = socket.socketpair()
        self.readable.setblocking(False)
        self.writable.setblocking(False)

    def notify(self):
        try: self.writable.send(b'x')
        except (BlockingIOError, OSError): pass

    def drain(self):
        try:
            while self.readable.recv(4096): pass
        except (BlockingIOError, OSError): pass
        with self.lock:
            if self.provider: self.provider.drain()
            if self.carrier: self.carrier.drain()
            self._dispose_retired()

    def readiness_sources(self, callback):
        with self.lock:
            sources = [(self.readable, callback)]
            if self.provider: sources.append((self.provider.readable, callback))
            if self.carrier: sources.append((self.carrier.readable, callback))
            return tuple(sources)

    def snapshot(self):
        with self.lock:
            if self.provider: return self.provider.snapshot()
            return dict(version=1, owner_online=False, capabilities=[], peers=[], radios=[],
                        messages=[], packets=[], error=self.error or 'Select a '+self.service_name+' owner in Connections')

    def request(self, action, payload):
        with self.lock:
            if not self.provider: raise ValueError('Select a '+self.service_name+' owner in Connections')
            return self.provider.request(action, payload)

    def connect(self, kind, address=''):
        with self.lock:
            if self.closed or self.busy or self.future is not None and not self.future.done(): return False
            self.generation += 1
            self.busy, self.error = True, ''
            if self.pool is None:
                from concurrent.futures import ThreadPoolExecutor
                self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='owner-select')
            self.future = self.pool.submit(self._connect, self.generation, kind, address)
        self.notify()
        return True

    def _connect(self, generation, kind, address):
        candidate = old = None
        from service_catalog import owner_factory
        factory=owner_factory(self.registry,self.service_name)
        try:
            if kind == 'peer':
                if self.service_name!='reticulum':raise ValueError('Use the MeshCore owner socket, optionally forwarded through SSH')
                with self.lock: carrier = self.carrier or self.provider
                if carrier is None: raise ValueError('Attach a local Reticulum owner first')
                candidate = carrier.remote(address.strip())
                label = 'Reticulum peer ' + address.strip()
            elif kind == 'socket':
                path = Path(address).expanduser().resolve()
                if not path.is_socket(): raise ValueError('Select an existing Reticulum owner.sock')
                candidate = factory(socket_path=path, register=False)
                label = str(path)
            elif kind in ('local','local-auto'):
                from app_registry import saved_reticulum_selection
                # Reading a configuration does not activate the radio.
                directory = Path(address).expanduser() if address else self.state_directory
                if self.service_name=='meshcore':
                    from meshcore_service import saved_selection
                    try:selection=saved_selection(directory)
                    except FileNotFoundError:
                        if kind!='local-auto':raise
                        selection=None
                else:selection = saved_reticulum_selection(directory)
                if kind=='local-auto' and (selection is None or selection['mode']!='local'):
                    with self.lock:
                        if generation==self.generation:self.busy=False
                    return
                if selection is None: raise ValueError('Choose a folder containing '+('meshcore-owner.toml' if self.service_name=='meshcore' else 'reticulum-owner.msgpack'))
                if selection['mode'] == 'external':
                    candidate = factory(socket_path=selection['socket'], register=False)
                else:
                    options = {k:v for k,v in selection.items() if k not in ('mode','state')}
                    candidate = factory(local_state=selection['state'], local_options=options, register=False)
                label = selection.get('station', selection.get('socket', 'Local owner'))
            else: raise ValueError('Choose local configuration, owner socket, or verified peer')
            with self.lock:
                if self.closed or generation != self.generation: return
                if self.carrier is None and kind != 'peer' and self.provider is not None and getattr(candidate, 'path', None) is not None and candidate.path == getattr(self.provider, 'path', None):
                    self.busy = False
                    return
                if kind == 'peer' and self.carrier is None:
                    self.carrier, self.provider = self.provider, None
                elif kind != 'peer' and self.carrier is not None:
                    if getattr(candidate,'path',None) == getattr(self.carrier,'path',None):
                        self.retired.append(candidate)
                        candidate = self.carrier
                    else: self.retired.append(self.carrier)
                    self.carrier = None
                old, self.provider = self.provider, candidate
                candidate = None
                self.label, self.busy = label, False
                if old is not None: self.retired.append(old)
                old = None
        except Exception as error:
            with self.lock:
                if generation == self.generation and not self.closed:
                    self.error, self.busy = str(error), False
        finally:
            for provider in (candidate, old):
                if provider is not None: self._close_provider(provider)
            self.notify()

    def adopt(self, provider, label, carrier=None):
        """Commit a device attachment, invalidating any older pending selection."""
        with self.lock:
            if self.closed: raise ValueError('Service selection is closed')
            self.generation += 1
            for old in (self.provider,self.carrier):
                if old is not None and old is not provider and old is not carrier:self.retired.append(old)
            self.provider,self.carrier=provider,carrier
            self.label,self.error,self.busy=label,'',False
        self.notify()

    def disconnect(self):
        with self.lock:
            self.generation += 1
            old, self.provider = self.provider, None
            self.busy, self.error, self.label = False, '', 'Not attached'
            if old is not None: self.retired.append(old)
            if self.carrier is not None:
                self.retired.append(self.carrier); self.carrier = None
        self.notify()

    def _close_provider(self, provider):
        try: provider.close()
        except Exception as error:
            with self.lock: self.error = 'Owner cleanup failed: ' + str(error)
            if self.closed:
                import sys
                print(self.error, file=sys.stderr)
            self.notify()

    def _dispose_retired(self):
        if self.retired and self.pool is None:
            from concurrent.futures import ThreadPoolExecutor
            self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='owner-select')
        for provider in self.retired: self.pool.submit(self._close_provider, provider)
        self.retired.clear()

    def close(self):
        if self.closed: return
        self.disconnect()
        self.closed = True
        with self.lock: self._dispose_retired()
        self.readable.close(); self.writable.close()
        if self.pool: self.pool.shutdown(wait=False)
