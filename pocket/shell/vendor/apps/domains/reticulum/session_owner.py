"""Idle radio management with explicit native sessions and desktop Python sessions."""
import argparse
import errno
import json
import math
import os
from pathlib import Path
import signal
import selectors
import _socket as socket
import stat
import subprocess
import sys
import threading
import time

from lxmf_owner import LXMFBackend
from owner import Owner, exchange, serve, LIMIT
from heard import bounded_snapshot
from profile_store import ProfileStore, atomic_state
from discovery_codec import unpack,legacy_value
from provider import Provider


class SessionEvents(Provider):
    def __init__(self, path, parent, generation):
        self.parent, self.generation = parent, generation
        super().__init__(path)

    def _publish(self, state):
        super()._publish(state)
        self.parent.post(dict(kind='session_state', generation=self.generation, state=state))


class SessionOwner(LXMFBackend):
    NODE_INTERVAL=20
    def __init__(self, state, station, radio, connection, port, minimum, maximum, seed=None, prepare_nokia_spp=False, startup_timeout=30):
        if type(startup_timeout) not in (int, float) or not math.isfinite(startup_timeout) or not 5 <= startup_timeout <= 120:
            raise ValueError('Startup timeout must be a finite number from 5 to 120 seconds')
        self.startup_timeout = float(startup_timeout)
        state = Path(state)
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = state.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Management state must be private and user-owned')
        idle = state / 'management-config'
        idle.mkdir(mode=0o700, exist_ok=True)
        (idle / 'config').touch(mode=0o600, exist_ok=True)
        super().__init__(state, station, idle, radio, connection, management=True)
        self.store = ProfileStore(state, station, radio, connection, port, minimum, maximum, seed)
        self.connection = self.store.endpoint.connection
        self.prepare_nokia_spp = prepare_nokia_spp
        if prepare_nokia_spp and station != 'n810':
            raise ValueError('The fixed SPP helper is only for the configured Nokia Bluetooth endpoint')
        from external_node import load
        self.node_preferences=load(state/'external-node.msgpack')
        self.node_state=dict(state='unconfigured',offload_ready=False)
        self.node_wake=threading.Event();self.node_stop=threading.Event();self.node_thread=None
        self.node_generation=0;self.node_refresh=False;self.node_client=None
        self.runtime_backend=None;self.handoff_pending=False
        self.runtime_controls={};self.restoring_generation=None
        self.operation_condition=threading.Condition();self.inflight=0
        self.phase = 'idle'
        self.child = self.reader = None
        self.hub = None
        self.available_hubs = []
        self._hub_stopping_generation = None
        self.generation = 0
        self.cancel = threading.Event()
        self.cancel_read, self.cancel_write = socket.socketpair()
        self.cancel_read.setblocking(False)
        self.cancel_write.setblocking(False)
        self.lifecycle = threading.Lock()
        self.cached = {}
        self.closed = False
        self.pending_connect = None
        self.ble_setup = None
        self.setup_generation = 0
        self.bluetooth = dict(phase='idle', target=self.store.endpoint.port[6:] if self.connection == 'ble' else None,
                              devices=[], authenticated=None, error=None)
        self.runtime = state / 'session-runtime'
        self.runtime.mkdir(mode=0o700, exist_ok=True)
        self.worker_socket = self.runtime / 'owner.sock'
        from local_owner import EndpointReceipt
        self.session_endpoint=EndpointReceipt(self.worker_socket,dict(service='reticulum-session',station=station,radio=radio))
        self.public_path = state / 'session-public.msgpack'
        public_source=self.public_path if self.public_path.exists() or self.public_path.is_symlink() else self.public_path.with_suffix('.json')
        if public_source.exists() or public_source.is_symlink():
            if public_source.is_symlink() or public_source.stat().st_size > 4096:
                raise ValueError('Unsafe public identity cache')
            raw=public_source.read_bytes()
            self.cached=unpack(raw) if public_source==self.public_path else legacy_value(raw)
            if not isinstance(self.cached,dict):raise ValueError('Invalid public identity cache')
            if public_source!=self.public_path:atomic_state(self.public_path,self.cached)
        self._saved_public = {k: self.cached.get(k) for k in ('public_card', 'lxmf_destination')}
        self.configure_connection_recovery(lambda:dict(station=self.station,radio=self.transport_id,
            connection=self.connection,port=self.store.endpoint.port,
            profile=self.store.profiles.get(self.store.selected)),dict(station=self.station,radio=self.transport_id),reset_error=True)

        if self.node_preferences['endpoint'] and self.node_preferences['mode']!='disabled':self._watch_node()

    def _watch_node(self):
        if self.node_thread is None:
            def run():
                from contextlib import nullcontext
                from external_node import probe,Connection
                client=None;address=None
                try:
                    while not self.node_stop.is_set():
                        preferences=dict(self.node_preferences);generation=self.node_generation
                        refresh,self.node_refresh=self.node_refresh,False
                        enabled=preferences['endpoint'] and (preferences['mode']!='disabled' or refresh)
                        if client and (not enabled or address!=preferences['endpoint']):
                            client.__exit__(None,None,None);client=None
                        if enabled:
                            try:
                                if client is None:
                                    candidate=Connection(preferences['endpoint']);candidate.__enter__()
                                    client=candidate;address=preferences['endpoint']
                                state=probe(address,connection=lambda _:nullcontext(client))
                                self.node_client=client
                            except Exception as error:
                                if client:client.__exit__(None,None,None);client=None
                                self.node_client=None
                                state=dict(state='unavailable',offload_ready=False,error=str(error)[:240],observed_at=time.time())
                            if not self.node_stop.is_set():self.post(dict(kind='node_state',node_generation=generation,state=state))
                        if preferences['mode']=='disabled' and client:
                            client.__exit__(None,None,None);client=None
                        self.node_wake.wait(self.NODE_INTERVAL if preferences['endpoint'] and preferences['mode']!='disabled' else None)
                        self.node_wake.clear()
                finally:
                    if client:client.__exit__(None,None,None)
            self.node_thread=threading.Thread(target=run,name='external-node-status',daemon=True);self.node_thread.start()
        else:self.node_wake.set()

    def _prepare_bluetooth(self):
        helper = Path('/usr/local/sbin/n810-rnode-spp-prepare')
        if not helper.exists():raise ValueError('Nokia Bluetooth preparation helper is not installed')
        info=helper.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
            raise ValueError('Nokia Bluetooth preparation helper must be a protected root-owned file')
        # The helper's own 25-second alarm starts after its Python imports.
        # Allow cold interpreter/sudo startup too, without blocking cancellation.
        deadline=time.monotonic()+max(60,self.startup_timeout+30)
        process=subprocess.Popen(['/usr/bin/sudo','-n',str(helper)],stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            while True:
                if self.cancel.is_set():raise InterruptedError('Bluetooth preparation cancelled')
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('Bluetooth preparation startup deadline exceeded')
                try:stdout,stderr=process.communicate(timeout=min(.25,remaining));break
                except subprocess.TimeoutExpired:pass
        finally:
            if process.poll() is None:
                from local_owner import stop_process
                stop_process(process)
            process.stdout.close();process.stderr.close()
        if len(stdout)>4096 or len(stderr)>4096:raise ValueError('Invalid Bluetooth preparation response')
        result=json.loads(stdout) if stdout else {}
        if process.returncode or result.get('ok') is not True or result.get('error'):
            raise ValueError(result.get('error') or 'Nokia Bluetooth preparation is not authorized or failed')

    def snapshot(self):
        state = Owner.snapshot(self)
        state['bluetooth'] = dict(self.bluetooth)
        state['external_node']=dict(self.node_state,**self.node_preferences)
        state['external_node']['selected']=self.runtime_backend if self.phase=='online' else 'none'
        state['external_node']['switching']=self.handoff_pending
        state['external_node']['sample_age']=max(0,time.time()-self.node_state['observed_at']) if self.node_state.get('observed_at') else None
        state['hubs'] = list(self.available_hubs)
        if self.hub is not None:
            hub_state = self.hub.provider.snapshot()
            state['hub'] = dict(hub_id=hub_state.get('hub_id'), connection_state=hub_state.get('connection_state'), bridge=hub_state.get('bridge', {}))
        for field in ('public_card', 'lxmf_destination', 'backend', 'messaging_state', 'messaging_error', 'native_error'):
            if field in self.cached:
                state[field] = self.cached[field]
        if self.phase == 'online':
            for field in ('messages', 'packets', 'last_job', 'peers', 'peers_total', 'data_bridge', 'message_discovery'):
                if field in self.cached:
                    state[field] = self.cached[field]
        else:
            state.update(messages=list(self.messages), packets=list(self.packets))
        profile = self.store.profiles.get(self.store.selected)
        radio = dict(station_id=self.station, radio_id=self.transport_id, connection=self.connection,
                     port=self.store.endpoint.port, connected=False, interface_online=False,
                     settings=profile or {}, minimum_txpower=self.store.minimum,
                     maximum_txpower=self.store.maximum)
        if self.phase in ('opening', 'online') and self.cached.get('radios'):
            radio.update(self.cached['radios'][0])
            radio.update(settings=profile or {}, minimum_txpower=self.store.minimum,
                         maximum_txpower=self.store.maximum, port=self.store.endpoint.port)
        if self.runtime_backend=='external':
            radio.update(connection='external',port=self.node_preferences['endpoint'],settings=self.node_state.get('radio') or {})
        capabilities = list(state['capabilities']) if self.phase in ('idle', 'online') else []
        if self.phase == 'idle':
            capabilities += ['save_profile', 'select_profile', 'delete_profile']
            capabilities += ['select_connection', 'list_hubs', 'ble_scan', 'ble_pair', 'ble_stop']
            if self.connection == 'usb':
                capabilities += ['rnode_bluetooth_on', 'rnode_pairing_mode']
            if profile or self.node_state.get('offload_ready') or self.node_preferences['mode']=='external-only':
                capabilities += ['connect']
        elif self.phase in ('opening', 'online', 'error'):
            capabilities += ['disconnect']
            if self.phase == 'online':
                capabilities += [c for c in ('send', 'announce', 'message_discovery', 'data_bridge_connect', 'data_bridge_request', 'data_bridge_disconnect', 'service_call', 'service_share', 'service_cancel', 'service_snapshot', 'service_discovery') if c in self.cached.get('capabilities', ())]
        capabilities += ['refresh_node']
        if self.phase=='idle':capabilities += ['configure_node']
        state['heard'] = list(self.cached.get('heard', [])) if self.phase == 'online' else self.heard_store.rows(self.book.contacts)[:12]
        state['heard_total'] = self.cached.get('heard_total', 0) if self.phase == 'online' else len(self.heard_store.records)
        if self.phase in ('idle', 'online'):
            capabilities += ['save_heard', 'rename_peer']
        state.update(heard_error=self.cached.get('heard_error', self.heard_error), message_error=self.cached.get('message_error') if self.phase in ('opening', 'online', 'error') else None, radio_event=self.cached.get('radio_event') if self.phase in ('opening', 'online') else None, capabilities=capabilities, radios=[radio], profiles=[dict(p, selected=p['id'] == self.store.selected)
                     for p in self.store.profiles.values()], selected_profile=profile,
                     radio_state=self.phase, radio_status=self.error or self.phase,
                     messaging=self.cached.get('messaging','official-lxmf'), packet_coverage='LXMF message and validated announce events; not a raw radio packet capture',
                     links=None, link_coverage='Active link observations are unavailable',
                     service_type='reticulum-session', startup_timeout=self.startup_timeout)
        return bounded_snapshot(state, LIMIT)

    def _signal_child(self):
        child = self.child
        if child is not None and child.poll() is None and getattr(self, '_terminating_child', None) is not child:
            self._terminating_child = child
            child.terminate()

    def _stop_child(self):
        try:
            reader, self.reader = self.reader, None
            if reader:
                reader.close()
            self._signal_child()
            child, self.child = self.child, None
            if child:
                if child.poll() is None:
                    try:
                        child.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=3)
                        raise RuntimeError('Forced session stop; radio shutdown needs operator verification')
                if child.returncode not in (0, -signal.SIGTERM):
                    raise RuntimeError('Radio session exited abnormally; verify radio shutdown')
            if os.path.lexists(self.worker_socket):
                self.session_endpoint.remove_stale()
        finally:
            attachment, self.hub = getattr(self, 'hub', None), None
            if attachment is not None: attachment.close()

    @staticmethod
    def _hub_api():
        sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
        from vendor.apps.domains.meshcore import hub_provider
        return hub_provider

    def _stop_failed_hub(self, generation):
        with self.lifecycle:
            if generation != self.generation:return
            try:self._stop_child()
            except Exception as error:
                self.post(dict(kind='error', generation=generation,
                               error=(self.error or 'Hub disconnected')+'; cleanup: '+str(error)))

    def _start(self, request, generation):
        with self.lifecycle:
            try:
                if self.cancel.is_set():
                    return
                from external_node import selection
                selected=selection(self.node_preferences['mode'],self.node_state)
                remote=None
                if selected=='external':
                    if self.node_client is None:raise ConnectionError('External connection changed before attach')
                    node_generation=self.node_generation
                    def failed(error):self.post(dict(kind='node_state',node_generation=node_generation,state=dict(state='unavailable',offload_ready=False,error=str(error))))
                    remote=dict(transport=self.node_client.owner_transport(),info=self.node_state['offload'],failure=failed)
                    native=True;directory=self.config
                else:
                    if self.node_preferences['endpoint']==self.store.endpoint.port:
                        raise ValueError('This port is assigned to the external node; choose a separate local radio for fallback')
                    from native_owner import use_native
                    native=use_native(self.connection)
                    prepare=self.prepare_nokia_spp and self.connection=='bluetooth' and self.store.endpoint.port=='/dev/rfcomm0'
                    if prepare:self._prepare_bluetooth()
                    resolved_port = None
                    if self.connection == 'hub':
                        attachment = self._hub_api().attach_hub(3, hub_id=self.store.endpoint.port[6:30],
                            interpreter=sys.executable, timeout=self.startup_timeout, stopped=self.cancel)
                        self.hub = attachment
                        attachment.provider.bind_wakeup(lambda:self.post(dict(kind='hub_state', generation=generation)))
                        resolved_port = attachment.port
                    if self.connection != 'ble':
                        port = Path(resolved_port or self.store.endpoint.port)
                        if not port.exists():
                            raise ValueError('Serial mapping is missing: ' + str(port) + '. Prepare the selected device with the system radio helper.')
                        if not stat.S_ISCHR(port.stat().st_mode) or not os.access(port, os.R_OK | os.W_OK):
                            raise ValueError('Serial device is not accessible to this user: ' + str(port))
                    config = self.store.configuration(resolved_port=resolved_port) if self.connection == 'hub' else self.store.configuration()
                    directory = self.book.directory / 'selected-radio'
                    directory.mkdir(mode=0o700, exist_ok=True)
                    path = directory / 'config'
                    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                    with os.fdopen(fd, 'w') as stream:
                        stream.write(config)
                if os.path.lexists(self.worker_socket):
                    self.session_endpoint.remove_stale()
                command = [sys.executable, '-B', str(Path(__file__).with_name('lxmf_owner.py')),
                           '--socket', str(self.worker_socket), '--state', str(self.book.directory),
                           '--station', self.station, '--transport-id', self.transport_id,
                           '--connection', self.connection, '--rns-config', str(directory)]
                if getattr(self,'service_socket',None) is not None:
                    command += ['--service-owner-socket', str(self.service_socket)]
                ready_read, ready_write = os.pipe()
                try:
                    command += ['--ready-fd', str(ready_write)]
                    if native:
                        from native_session import NativeSession
                        self.child=NativeSession(self.worker_socket,self.book.directory,self.station,directory,
                            self.transport_id,self.connection,ready_write,getattr(self,'service_socket',None),remote=remote)
                    else:
                        self.child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                                      start_new_session=True, pass_fds=(ready_write,))
                finally:
                    os.close(ready_write)
                try:
                    if self.cancel.is_set():
                        if self.child.poll() is None:
                            self._signal_child()
                        return
                    with selectors.DefaultSelector() as selector:
                        selector.register(ready_read, selectors.EVENT_READ, 'ready')
                        selector.register(self.cancel_read, selectors.EVENT_READ, 'cancel')
                        while True:
                            events = selector.select()
                            if self.cancel.is_set() or any(key.data == 'cancel' for key, _ in events):
                                if self.child.poll() is None:
                                    self._signal_child()
                                return
                            if any(key.data == 'ready' for key, _ in events):
                                ready = os.read(ready_read, 1)
                                break
                finally:
                    os.close(ready_read)
                if self.cancel.is_set():
                    return
                if ready != b'R':
                    raise RuntimeError('Radio session exited before listener readiness')
                info=self.session_endpoint.endpoint_info()
                if info is not None:self.session_endpoint.record(info)
                response = exchange(self.worker_socket, request)
                if self.cancel.is_set():
                    return
                if response.get('error'):
                    raise RuntimeError(response['error'])
                job = response.get('job') or {}
                if job.get('state') == 'failed':
                    raise RuntimeError(job.get('error') or 'Radio session initialization failed')
                # The subscription supplies its initial snapshot. A second,
                # synchronous snapshot here imposed a two-second deadline on
                # a healthy busy Nokia and could kill its just-started radio.
                self.runtime_backend=selected
                self.reader = SessionEvents(self.worker_socket, self, generation)
            except Exception as error:
                if not self.cancel.is_set():
                    try:
                        self._stop_child()
                    except Exception as cleanup:
                        error = RuntimeError(str(error) + '; ' + str(cleanup))
                    self.post(dict(kind='error', generation=generation, error=str(error),
                                   job=dict(id=request['request_id'], action='connect', state='failed', error=str(error))))

    def _disconnect(self, request, generation):
        with self.lifecycle:
            try:
                self._stop_child()
                history = LXMFBackend(self.book.directory, self.station, self.config, self.transport_id, self.connection, management=True)
                self.post(dict(kind='closed', generation=generation, messages=history.messages, book=history.book, heard_store=history.heard_store,
                               job=dict(id=request['request_id'], action='disconnect', state='complete')))
            except Exception as error:
                self.post(dict(kind='error', generation=generation, error=str(error),
                               job=dict(id=request['request_id'], action='disconnect', state='failed', error=str(error))))

    def _remember_control(self,action,payload,response):
        if response.get('error'):return
        if action in ('revoke_peer','data_bridge_disconnect'):
            peer=payload.get('peer')
            self.runtime_controls={key:value for key,value in self.runtime_controls.items() if key[1]!=peer}
            if not any(key[0] in ('service_share','data_bridge_connect') for key in self.runtime_controls):
                self.runtime_controls.pop(('service_discovery','',''),None)
        elif action in ('service_share','data_bridge_connect','service_discovery','message_discovery'):
            key=(action,payload.get('peer',''),payload.get('service',''))
            value=dict(payload)
            if 'operations' in value:value['operations']=list(value['operations'])
            self.runtime_controls[key]=value

    def _restore_controls(self,generation):
        try:
            with self.lifecycle:
                controls=list(self.runtime_controls.items())
                controls.sort(key=lambda row:row[0][0] in ('service_discovery','message_discovery'))
                for (action,_,_),payload in controls:
                    if generation!=self.generation or self.closed or self.cancel.is_set():return
                    response=exchange(self.worker_socket,dict(version=1,action=action,payload=payload,
                        request_id='runtime-control-'+str(time.time_ns())))
                    if response.get('error'):raise ValueError('Cannot restore sharing: '+str(response['error']))
                self.post(dict(kind='controls_restored',generation=generation))
        except Exception as error:
            self.post(dict(kind='error',generation=generation,error=str(error),
                job=dict(id=self.pending_connect,action='connect',state='failed',error=str(error))))

    def dispatch(self, request):
        if not isinstance(request, dict) or request.get('version') != 1 or self.closed:
            raise ValueError('Invalid management request')
        action = request.get('action')
        payload = request.get('payload', {})
        if action == 'snapshot':
            return self.snapshot()
        if action in ('configure_node','refresh_node'):
            from external_node import MODES,endpoint,save
            if not isinstance(payload,dict):raise ValueError('Invalid external node request')
            if action=='configure_node':
                if self.phase!='idle':raise ValueError('Disconnect before changing external node preferences')
                if not payload or set(payload)-{'mode','endpoint'}:raise ValueError('Choose mode or external node connection')
                value=dict(self.node_preferences,**payload)
                if 'endpoint' in payload:value.pop('node_identity',None)
                if value['mode'] not in MODES:raise ValueError('Choose Auto, Disabled or External only')
                if not isinstance(value['endpoint'],str):raise ValueError('Choose an external node connection')
                if value['endpoint']:
                    value['endpoint']=endpoint(value['endpoint'])
                save(self.book.directory/'external-node.msgpack',value)
                self.node_preferences=value;self.node_generation+=1
                self.node_state=dict(state='waiting' if value['endpoint'] else 'unconfigured',offload_ready=False)
            elif payload:raise ValueError('Refresh node takes no arguments')
            self.node_refresh=True
            if self.node_preferences['endpoint']:self._watch_node()
            self.revision+=1
            return dict(version=1,external_node=dict(self.node_state,**self.node_preferences))
        if action == 'list_hubs':
            if self.phase != 'idle' or payload != {}:raise ValueError('Disconnect the radio before choosing a hub')
            self.available_hubs = self._hub_api().configured_hubs()
            self.revision += 1
            return dict(version=1, hubs=self.available_hubs)
        if action in ('select_connection', 'ble_scan', 'ble_pair', 'ble_stop', 'rnode_bluetooth_on', 'rnode_pairing_mode'):
            if self.phase != 'idle':
                raise ValueError('Disconnect the radio before Bluetooth setup')
            if self.bluetooth.get('phase') == 'configuring_usb' and action != 'ble_stop':
                raise ValueError('Stop or finish USB setup before changing the connection')
            if action == 'select_connection':
                from endpoints import Endpoint
                if not isinstance(payload, dict) or set(payload) != {'connection', 'port'}:
                    raise ValueError('Choose connection and device explicitly')
                endpoint = Endpoint(self.station, self.transport_id, payload['connection'], payload['port'])
                if self.node_preferences['endpoint']==endpoint.port:raise ValueError('This connection is selected for node status; shared node/radio integration is not implemented')
                if endpoint.connection == 'hub':self._hub_api().configured_port(endpoint.port[6:30])
                if self.ble_setup is not None:
                    self.ble_setup.close(); self.ble_setup = None
                self.setup_generation += 1
                atomic_state(self.book.directory / 'radio-device.msgpack', dict(version=1, station=self.station,
                            radio=self.transport_id, connection=endpoint.connection, port=endpoint.port))
                self.store.endpoint = endpoint
                self.connection = endpoint.connection
                self.bluetooth = dict(phase='idle', target=endpoint.port[6:] if self.connection == 'ble' else None,
                                      devices=[], authenticated=None, error=None)
            elif payload:
                raise ValueError('Bluetooth setup does not accept additional arguments')
            else:
                if action.startswith('rnode_') and self.connection != 'usb':
                    raise ValueError('Select the USB connection for RNode Bluetooth setup')
                if action in ('ble_scan', 'ble_pair') and self.connection != 'ble':
                    raise ValueError('Select a BLE device before scanning or pairing')
                if self.ble_setup is None and action != 'ble_stop':
                    from ble_setup import BLESetup
                    generation = self.setup_generation
                    self.ble_setup = BLESetup(self.bluetooth['target'],
                        lambda state: self.post(dict(kind='ble_state', setup_generation=generation, state=state)),
                        port=self.store.endpoint.port)
                if self.ble_setup is not None:
                    self.bluetooth.update(phase='configuring_usb' if action.startswith('rnode_') else 'stopping' if action == 'ble_stop' else 'scanning', error=None)
                    self.ble_setup.submit(action)
            self.revision += 1
            return dict(version=1, bluetooth=dict(self.bluetooth))
        if action in ('connect', 'disconnect'):
            if payload != dict(station=self.station, radio=self.transport_id) or not isinstance(request.get('request_id'), str):
                raise ValueError('Select this station and radio explicitly')
            if action == 'connect':
                if self.bluetooth.get('phase') in ('scanning', 'pairing', 'authenticating', 'stopping', 'configuring_usb'):
                    raise ValueError('Stop Bluetooth setup before connecting the radio')
                if self.phase != 'idle' or self.store.selected is None and not (self.node_state.get('offload_ready') or self.node_preferences['mode']=='external-only'):
                    raise ValueError('Select a profile while idle before connecting')
                self.connection_requested(True)
                while True:
                    try:
                        if not self.cancel_read.recv(4096):
                            break
                    except BlockingIOError:
                        break
                self.cancel.clear()
                self.pending_connect = request['request_id']
                for key in ('radios', 'radio_event', 'message_error', 'heard_error'):
                    self.cached.pop(key, None)
                self.phase = 'opening'
                target = self._start
            else:
                if self.phase not in ('opening', 'online', 'error'):
                    raise ValueError('Radio is already idle or stopping')
                self.connection_requested(False)
                if not self._connection_internal:self.runtime_controls.clear()
                self._notify_cancel()
                self.handoff_pending=False
                self.phase = 'closing'
                if self.child and self.child.poll() is None:
                    self._signal_child()
                target = self._disconnect
            self.generation += 1
            self.last_job = dict(id=request['request_id'], action=action, state='running')
            self.revision += 1
            self.error = None
            threading.Thread(target=target, args=(request, self.generation), daemon=True).start()
            return dict(version=1, job=self.last_job)
        if action in ('save_profile', 'select_profile', 'delete_profile'):
            if self.phase != 'idle' or not isinstance(payload, dict):
                raise ValueError('Disconnect before changing profiles')
            identity = self.store.dispatch(action, payload)
            self.last_job = dict(id=request.get('request_id'), action=action, state='complete', profile=identity)
            self.revision += 1
            return dict(version=1, job=self.last_job)
        if self.phase == 'online' and action in ('send', 'announce', 'message_discovery', 'import_peer', 'verify_peer', 'revoke_peer', 'save_heard', 'rename_peer', 'data_bridge_connect', 'data_bridge_request', 'data_bridge_disconnect', 'service_call', 'service_share', 'service_cancel', 'service_snapshot', 'service_discovery'):
            with self.operation_condition:
                if self.handoff_pending:raise ValueError('Runtime switching; command was not sent')
                self.inflight+=1
            try:
                response=exchange(self.worker_socket, request)
                self._remember_control(action,payload,response)
                return response
            finally:
                with self.operation_condition:
                    self.inflight-=1;self.operation_condition.notify_all()

        if action in ('send', 'announce'):
            raise ValueError('Connect explicitly before transmitting')
        if self.phase != 'idle':
            raise ValueError('Wait for radio lifecycle operation to finish')
        if action in ('save_heard', 'rename_peer'):
            return LXMFBackend.dispatch(self, request)
        response=Owner.dispatch(self, request)
        self._remember_control(action,payload,response)
        return response

    def drain(self):
        while not self.events.empty():
            event = self.events.get()
            if event.get('kind') == 'ble_state':
                if event.get('setup_generation') == self.setup_generation and not self.closed:
                    self.bluetooth = event['state']
                    self.revision += 1
                continue
            if event.get('kind')=='node_state':
                if not self.closed and event['node_generation']==self.node_generation:
                    state=event['state'];pin=self.node_preferences.get('node_identity')
                    identity=state.get('identity')
                    if pin and identity and pin!=identity:
                        state=dict(state,state='unavailable',offload_ready=False,reason='Node identity changed; reselect the board to approve it')
                    elif identity and not pin:
                        from external_node import save
                        self.node_preferences=dict(self.node_preferences,node_identity=identity)
                        save(self.book.directory/'external-node.msgpack',self.node_preferences)
                    self.node_state=state;self.revision+=1
                    self._reconcile_runtime()
                    if self.phase=='error' and not self.handoff_pending and self._connection_wanted and state.get('offload_ready') and self.node_preferences['mode']!='disabled':
                        self._connection_due=time.monotonic();self.recover_connection()
                continue
            if event.get('generation') != self.generation or self.closed:
                continue
            kind = event['kind']
            if kind=='controls_restored':
                self.phase='online';self.error=None
                self.last_job=dict(id=self.pending_connect,action='connect',state='complete')
                self.revision+=1;self._reconcile_runtime();continue
            if kind=='handoff_ready':
                self.handoff_pending=False;self.runtime_backend=None
                self.phase='idle';self.cached={}
                if event['target']=='blocked':
                    self.phase='error';self.error=self.node_state.get('reason') or self.node_state.get('error') or 'External node unavailable; local fallback disabled'
                else:
                    try:self.dispatch(dict(version=1,action='connect',request_id='auto-runtime-'+str(time.time_ns()),payload=dict(station=self.station,radio=self.transport_id)))
                    except (OSError,ValueError) as error:self.phase,self.error='error',str(error)
                self.revision+=1
                continue

            if kind == 'hub_state':
                if self.hub is not None:
                    try:self.hub.snapshot()
                    except (OSError, ValueError) as error:
                        self.phase, self.error = 'error', str(error)
                        self.last_job = dict(id=self.pending_connect, action='connect', state='failed', error=self.error)
                        self._notify_cancel(); self._signal_child()
                        if self._hub_stopping_generation != self.generation:
                            self._hub_stopping_generation = self.generation
                            threading.Thread(target=self._stop_failed_hub, args=(self.generation,), daemon=True).start()
                self.revision += 1
                continue
            if kind in ('session_state', 'opened'):
                state = event['state']
                self.cached.update(state)
                public = {k: state.get(k) for k in ('public_card', 'lxmf_destination')}
                if all(public.values()) and public != getattr(self, '_saved_public', None):
                    atomic_state(self.public_path, public)
                    self._saved_public = public
                radio_event = state.get('radio_event') or {}
                child_job = state.get('last_job') or {}
                if (self.phase == 'opening' and child_job.get('id') == self.pending_connect
                        and child_job.get('action') == 'connect' and child_job.get('state') == 'failed'):
                    self.phase, self.error = 'error', child_job.get('error') or 'Radio session initialization failed'
                    self.last_job = dict(id=self.pending_connect, action='connect', state='failed', error=self.error)
                elif radio_event.get('phase') == 'failed':
                    self.phase, self.error = 'error', radio_event.get('error')
                    self.last_job = dict(id=self.pending_connect, action='connect', state='failed', error=self.error)
                elif self.phase == 'opening' and (state.get('lxmf_destination') or state.get('backend') in ('native-microreticulum','external-microreticulum')) and any(r.get('interface_online') for r in state.get('radios', [])):
                    if self.runtime_controls:
                        if self.restoring_generation!=self.generation:
                            self.restoring_generation=self.generation
                            threading.Thread(target=self._restore_controls,args=(self.generation,),daemon=True,name='runtime-sharing').start()
                    else:
                        self.phase = 'online'
                        self.last_job = dict(id=self.pending_connect, action='connect', state='complete')
                elif not state.get('owner_online'):
                    self.phase, self.error = 'error', state.get('error') or 'Radio session disconnected'
            elif kind == 'closed':
                self.phase, self.error = 'idle', None
                self.messages = event['messages']
                self.book = event['book']
                self.heard_store = event['heard_store']
                self.packets = []
            elif kind in ('error','handoff_failed'):
                self.phase, self.error = 'error', event['error']
                if kind=='handoff_failed':self.handoff_pending=False;self.runtime_backend=None
            if 'job' in event:
                self.last_job = event['job']
            self.revision += 1
            self._reconcile_runtime()

    def _reconcile_runtime(self):
        if self.phase not in ('online','error') or self.handoff_pending or not self.runtime_backend:return
        from external_node import selection
        try:target=selection(self.node_preferences['mode'],self.node_state)
        except ValueError:target='blocked'
        if target==self.runtime_backend:return
        self.handoff_pending=True;generation=self.generation
        self.last_job=dict(action='handoff',state='running',target=target)
        def stop():
            try:
                with self.operation_condition:
                    while self.inflight and generation==self.generation and not self.closed:self.operation_condition.wait(.5)
                with self.lifecycle:
                    if generation!=self.generation or self.closed:return
                    self._stop_child()
                self.post(dict(kind='handoff_ready',generation=generation,target=target))
            except Exception as error:self.post(dict(kind='handoff_failed',generation=generation,error=str(error)))
        threading.Thread(target=stop,name='runtime-handoff',daemon=True).start()

    def _notify_cancel(self):
        self.cancel.set()
        try:
            self.cancel_write.send(b'x')
        except (BlockingIOError, OSError):
            pass

    def close(self):
        self.node_stop.set();self.node_wake.set()
        self.stop_connection_recovery()
        self.closed = True
        if self.ble_setup is not None:
            self.ble_setup.close()
        self._notify_cancel()
        if self.child and self.child.poll() is None:
            self._signal_child()
        with self.lifecycle:
            self._stop_child()
        self.cancel_read.close()
        self.cancel_write.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('socket', 'state', 'station', 'radio-id', 'connection', 'port'):
        parser.add_argument('--' + name, required=True)
    for name in ('minimum-txpower', 'maximum-txpower'):
        parser.add_argument('--' + name, type=int, required=True)
    parser.add_argument('--seed-profile')
    parser.add_argument('--prepare-nokia-spp', action='store_true')
    parser.add_argument('--startup-timeout', type=float, default=30)
    parser.add_argument('--ready-fd', type=int)
    args = parser.parse_args()
    def stop(signum, frame):
        raise SystemExit(0)
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, stop)
    os.umask(0o077)
    factory = lambda state, station: SessionOwner(state, station, args.radio_id, args.connection,
                args.port, args.minimum_txpower, args.maximum_txpower, args.seed_profile, args.prepare_nokia_spp, args.startup_timeout)
    serve(args.socket, args.state, args.station, factory, ready_fd=args.ready_fd)


if __name__ == '__main__':
    main()
