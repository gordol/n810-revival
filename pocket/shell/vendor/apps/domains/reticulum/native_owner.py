"""Pocket's existing service and message policies over native RNS and LXMF."""
import os
from pathlib import Path
from lxmf_owner import LXMFBackend
from heard import AnnounceObserver
import backend_policy

def installed_library():
    configured=os.environ.get('POCKET_RNS_LIBRARY')
    if configured=='stock':
        backend_policy.require_stock_allowed()
        return None
    if configured:
        if not Path(configured).is_file():raise ValueError('Configured native Reticulum library is missing')
        return Path(configured)
    root=Path(__file__).resolve().parents[4]
    candidate=root/'vendor/native'/('libpocket_rns.dylib' if os.sys.platform=='darwin' else 'libpocket_rns.so')
    if candidate.is_file():return candidate
    if backend_policy.native_required():
        raise ValueError('This Nokia release requires its packaged microReticulum library; reinstall a complete native release')
    return None

def use_native(connection):
    """Service-owned implementation policy shared by every local launcher."""
    if connection == 'ble':
        if backend_policy.native_required():
            label = 'Direct BLE'
            raise ValueError(label + ' Reticulum is not supported by the Nokia native backend; use USB, Classic Bluetooth or the shared hub')
        return False
    return installed_library() is not None

def selected_backend(connection):
    """Resolve an owner implementation; apps consume the owner API unchanged."""
    return NativeBackend if use_native(connection) else LXMFBackend


class NativeBackend(LXMFBackend):
    def __init__(self,*args,library=None,remote=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.remote=remote
        self.library=library or (None if remote else installed_library())
        if not remote and (not self.library or not Path(self.library).is_file()):raise ValueError('Native Reticulum library is not installed')
        self.native_radio=None
    def _radio_status(self,event):
        if self.remote and self.native_radio:self.native_radio.online=event['phase']=='ready'
        try:self.stack.call('online',event['phase']=='ready')
        except (OSError,ValueError,ConnectionError):
            if not self.remote:raise
        self.post(dict(event='radio_state',radio_event=event))
        if self.remote and event['phase']=='failed' and self.remote.get('failure'):self.remote['failure'](event.get('error') or 'External runtime failed')
    def _connect(self):
        try:return self._connect_runtime()
        except Exception as error:
            if self.remote and self.remote.get('failure'):self.remote['failure'](error)
            raise
    def _connect_runtime(self):
        import native_stack as RNS
        import native_lxmf as LXMF
        from native_radio import configuration,RNode,TCPPackets,SerialPackets,KISSPackets
        if self.remote:
            from native_rpc import Library
            from types import SimpleNamespace
            api=Library(self.remote['transport'],self.remote['info'])
            self.native_radio=SimpleNamespace(online=False,name='External microReticulum',rxb=0,txb=0,close=lambda:None)
            adapter=config=None
        else:
            api=None;config=configuration(self.config/'config')
            adapter={'RNodeInterface':RNode,'SerialInterface':SerialPackets,'KISSInterface':KISSPackets,'TCPClientInterface':TCPPackets,'TCPServerInterface':TCPPackets}.get(config.get('type'))
            if adapter is None:raise ValueError('Selected interface is not supported by the native owner')
        storage=self.book.directory/'native-rns';storage.mkdir(mode=0o700,exist_ok=True)
        self.RNS,self.LXMF=RNS,LXMF
        self.stack=RNS.Engine(self.library,storage,lambda data:self.native_radio.send(data) if self.native_radio and not self.remote else False,api=api)
        self._load_identity(RNS)
        self.announce_observer=AnnounceObserver(self)
        RNS.Transport.register_announce_handler(self.announce_observer)
        self.router=LXMF.Router(self);self.delivery=self.router.delivery
        for peer,record in self.book.contacts.items():
            if record['state']=='verified':self._remember_verified_peer(peer)
        self.stack.failure=lambda error:self._radio_status(dict(phase='failed',error=str(error),readbacks={}))
        if adapter:self.native_radio=adapter(config,self.stack.receive,self._radio_status)
        else:self._radio_status(dict(phase='ready',error=None,readbacks={}))
        RNS.Transport.interfaces=[self.native_radio]
        self.stack.start()
    def dispatch(self,request):
        result=super().dispatch(request)
        action=request.get('action')
        if action=='service_discovery' and self.data_bridge.destination is not None:self.data_bridge.destination.set_public_discovery(request['payload']['enabled'])
        if action=='message_discovery':self.stack.call('lxmf_public',request['payload']['enabled'])
        return result
    def snapshot(self):
        state=super().snapshot()
        online=bool(self.native_radio and self.native_radio.online)
        state.update(native_error=self.stack.last_error if self.stack else None,backend='external-microreticulum' if self.remote else 'native-microreticulum',messaging='native-microlxmf',
            radio_state='online' if online else getattr(self.native_radio,'phase','opening') if self.stack else 'idle',radio_status=self.error or ('online' if online else getattr(self.native_radio,'phase','opening') if self.stack else 'idle'),
            messaging_state='ready' if self.delivery and online else 'starting' if self.stack else 'unavailable')
        self.data_bridge.update(state);state['data_bridge']=self.data_bridge.snapshot()
        return state
    def _peer_mapping(self,peer):
        record=self.book.contacts.get(peer,{})
        identity=self.RNS.Identity(create_keys=False);identity.load_public_key(bytes.fromhex(record.get('card',{}).get('public_key','')))
        if identity.hash.hex()!=peer:raise ValueError('Saved peer identity does not match its key')
        return identity,self.RNS.Destination.hash_from_name_and_identity('lxmf.delivery',identity)
    def _remember_verified_peer(self,peer):self.router.remember(self._peer_mapping(peer)[0])
    def close(self):
        if self.stack:
            try:self.stack.cancel_stamp()
            except (OSError,ValueError,ConnectionError):
                if not self.remote:raise
        self.data_bridge.close()
        if self.native_radio:self.native_radio.close()
        if self.stack:
            try:self.stack.close()
            except (OSError,ValueError,ConnectionError):
                if not self.remote:raise
