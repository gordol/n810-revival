"""Station owner using official RNS/LXMF APIs; run in the approved isolated runtime."""
import argparse
import hashlib
import importlib
from pathlib import Path
import queue
import signal
import threading
import time
from discovery_codec import legacy_value
import os
import tempfile

from heard import HeardStore, AnnounceObserver, bounded_snapshot
from wire import encode,decode

if __package__:
    from .owner import Owner, serve, LIMIT
    from .contacts import card, public_key
    from .endpoints import token
else:
    from owner import Owner, serve, LIMIT
    from contacts import card, public_key
    from endpoints import token


def load_stack():
    """Load desktop Python RNS/LXMF; native sessions share policy code, not this stack."""
    from backend_policy import require_stock_allowed
    require_stock_allowed()
    from desktop_stack import load_stack as load_desktop_stack
    return load_desktop_stack()


class LXMFBackend(Owner):
    def __init__(self, state, station, config, transport_id, connection, *, management=False):
        super().__init__(state, station)
        self.config = Path(config)
        if not (self.config / 'config').is_file():
            raise ValueError('Select an existing explicit Reticulum config')
        self.transport_id = token(transport_id, 'transport identity')
        self.connection = connection
        self.stack = self.router = self.identity = self.delivery = None
        self.RNS = self.LXMF = None
        self.busy = False
        self.message_discovery = False
        self.data_bridge = None
        if not management:
            from data_bridge import DataBridge
            self.data_bridge = DataBridge(self)
        self.radio_event = None
        self.heard_store = HeardStore(self.book.directory)
        self.announce_observer = None
        self.heard_error = None
        self.error = None
        self.message_error = None
        self._cache_contract_verified = False
        self.messages = []
        self.packets = []
        self.message_directory = self.book.directory / 'messages'
        self.message_directory.mkdir(mode=0o700, exist_ok=True)
        self.history_path = self.book.directory / 'message-history.msgpack'
        legacy=self.book.directory/'message-history.json'
        source=self.history_path if self.history_path.exists() else legacy
        if source.exists():
            if source.is_symlink() or source.stat().st_mode & 0o077 or source.stat().st_size > 32768:
                raise ValueError('Unsafe message history file')
            history = decode(source.read_bytes()) if source==self.history_path else legacy_value(source.read_bytes())
            if not isinstance(history, dict) or history.get('version') != 1 or not isinstance(history.get('messages'), list):
                raise ValueError('Unsupported message history')
            for row in history['messages'][-32:]:
                if not isinstance(row, dict) or not isinstance(row.get('id'), str):
                    raise ValueError('Invalid stored message')
                if row.get('state') == 'queued':
                    row = dict(row, state='unknown_after_restart')
                self.messages.append(row)

    def _save_history(self):
        while True:
            try:raw = encode(dict(version=1, messages=self.messages));break
            except ValueError:
                if not self.messages:raise
                self.messages.pop(0)
        fd, temporary = tempfile.mkstemp(prefix='.messages-', dir=self.book.directory)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.history_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def snapshot(self):
        state = super().snapshot()
        online = None
        interfaces = []
        if self.stack:
            interfaces = self.RNS.Transport.interfaces
            online = any(getattr(interface, 'online', False) for interface in interfaces)
        radio = dict(station_id=self.station, radio_id=self.transport_id, connection=self.connection,
                     connected=online, interface_online=online,
                     rx_bytes=sum(getattr(interface, 'rxb', 0) for interface in interfaces),
                     tx_bytes=sum(getattr(interface, 'txb', 0) for interface in interfaces))
        state['message_discovery']=self.message_discovery
        state['heard'] = self.heard_store.rows(self.book.contacts)[:12]
        state['heard_total'] = len(self.heard_store.records)
        state['capabilities'] += ['save_heard', 'rename_peer']
        state.update(heard_error=self.heard_error, message_error=self.message_error, radio_event=self.radio_event, radios=[radio], messages=list(self.messages), packets=list(self.packets),
                     messaging='official-lxmf', radio_status=self.error or 'Connect selected transport explicitly',
                     packet_coverage='LXMF message and validated announce events; not a raw radio packet capture')
        if self.identity:
            state['public_card'] = card(self.identity.get_public_key(), self.station)
            state['lxmf_destination'] = self.delivery.hash.hex() if self.delivery else None
        if not self.busy:
            if self.stack is None:
                state['capabilities'] += ['connect']
            elif self.delivery is not None and online:
                state['capabilities'] += ['send', 'announce', 'message_discovery']
        self.data_bridge.update(state)
        state['data_bridge'] = self.data_bridge.snapshot()
        if self.delivery is not None and online:
            from data_bridge import ACTIONS
            state['capabilities'] += list(ACTIONS)
        return bounded_snapshot(state, LIMIT)

    def _connect(self):
        RNS,LXMF=load_stack()
        from driver import install
        install(lambda event: self.post(dict(event='radio_state', radio_event=event)))
        self.RNS, self.LXMF = RNS, LXMF
        self.announce_observer = AnnounceObserver(self)
        RNS.Transport.register_announce_handler(self.announce_observer)
        handlers = {number: signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)}
        try:
            self.stack = RNS.Reticulum(configdir=str(self.config))
        finally:
            # RNS installs process handlers. This service owns its socket lifetime
            # and calls the standard shutdown hooks from serve() cleanup.
            for number, handler in handlers.items():
                signal.signal(number, handler)
        self._seed_verified_peers()
        self._load_identity(RNS)
        try:
            self.router = LXMF.LXMRouter(storagepath=str(self.book.directory / 'lxmf'), autopeer=False,
                                         delivery_limit=16)
            self.delivery = self.router.register_delivery_identity(self.identity, display_name=self.station)
            self.router.register_delivery_callback(self._received)
            announce=self.delivery.announce
            def guarded_announce(*args,**kwargs):
                if self.message_discovery:return announce(*args,**kwargs)
            self.delivery.announce=guarded_announce
        finally:
            # LXMF installs its own handlers too; preserve the service lifetime.
            for number, handler in handlers.items():
                signal.signal(number, handler)
        if self.delivery is None:
            raise RuntimeError('Official LXMF router did not register a delivery identity')

    def _load_identity(self, RNS):
        identity_path = self.book.directory / 'identity'
        if identity_path.exists():
            if identity_path.is_symlink() or identity_path.stat().st_mode & 0o077:
                raise ValueError('Private identity permissions must be 0600')
            self.identity = RNS.Identity.from_file(str(identity_path))
            if self.identity is None:
                raise ValueError('Cannot read existing identity; refusing replacement')
        else:
            self.identity = RNS.Identity()
            fd = os.open(identity_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(self.identity.get_private_key())

    def _peer_mapping(self, peer):
        record = self.book.contacts[peer]
        key = public_key(record['card']['public_key'])
        identity = self.RNS.Identity(create_keys=False)
        identity.load_public_key(key)
        if identity.hash.hex() != peer:
            raise ValueError('Saved peer identity does not match its key')
        destination = self.RNS.Destination.hash_from_name_and_identity('lxmf.delivery', identity)
        try:
            existing = self.RNS.Identity.recall(destination, _no_use=True)
        except (TypeError, IndexError, KeyError) as error:
            raise ValueError('Conflicting or malformed Reticulum key mapping') from error
        if existing is not None and existing.get_public_key() != key:
            raise ValueError('Conflicting Reticulum key for saved LXMF destination')
        return destination, key, existing

    def _remember_verified_peer(self, peer):
        if self.book.contacts[peer]['state'] != 'verified':
            return
        if not self._cache_contract_verified:
            source = Path(importlib.import_module('RNS.Identity').__file__)
            if hashlib.sha256(source.read_bytes()).hexdigest() != '447d6a8406ab0f824c9c6488de1f14434003d21bdfef65d33d79b20d8a2698e3':
                raise ValueError('Peer lookup requires the reviewed Reticulum cache contract')
            self._cache_contract_verified = True
        destination, key, _ = self._peer_mapping(peer)
        identity = self.RNS.Identity
        with identity.known_destinations_lock:
            if destination in identity.known_destinations:
                existing = identity.known_destinations[destination]
                if not isinstance(existing, list) or len(existing) != 5 or existing[2] != key:
                    raise ValueError('Conflicting Reticulum key for saved LXMF destination')
                return
            identity.known_destinations[destination] = [time.time(), None, key, None, 0]

    def _seed_verified_peers(self):
        for peer, record in self.book.contacts.items():
            if record['state'] == 'verified':
                self._remember_verified_peer(peer)

    def _received(self, message):
        if not message.signature_validated:
            reason = getattr(message, 'unverified_reason', None)
            if reason == self.LXMF.LXMessage.SOURCE_UNKNOWN:
                code, error = 'source_unknown', 'LXMF sender identity is unknown'
            elif reason == self.LXMF.LXMessage.SIGNATURE_INVALID:
                code, error = 'signature_invalid', 'LXMF signature is invalid'
            else:
                code, error = 'validation_failed', 'LXMF signature could not be validated'
            self.post(dict(event='invalid_message', reason=code, error=error,
                           message_hash=message.hash.hex() if message.hash else None,
                           source=message.source_hash.hex() if message.source_hash else None))
            return
        source = message.get_source()
        identity = getattr(source, 'identity', None)
        peer = identity.hash.hex() if identity else None
        record = self.book.contacts.get(peer)
        message.write_to_directory(str(self.message_directory))
        text = message.content_as_string()
        self.post(dict(event='message', id=message.hash.hex(), direction='rx', peer=peer,
                       destination=message.source_hash.hex(), text=text.encode()[:512].decode('utf-8', errors='replace'),
                       state='received', signature_valid=True,
                       peer_verified=bool(record and record['state'] == 'verified'),
                       contact=card(identity.get_public_key(), 'Discovered peer ' + peer[:8]) if identity else None,
                       bytes=len(message.content), timestamp=message.timestamp))

    def _send(self, request):
        payload = request['payload']
        peer = payload['peer']
        record = self.book.contacts.get(peer)
        if not record or record['state'] != 'verified':
            raise ValueError('Compare and verify this exact peer key before sending')
        identity = self.RNS.Identity(create_keys=False)
        identity.load_public_key(public_key(record['card']['public_key']))
        destination = self.RNS.Destination(identity, self.RNS.Destination.OUT,
                                           self.RNS.Destination.SINGLE, 'lxmf', 'delivery')
        message = self.LXMF.LXMessage(destination, self.delivery, payload['text'], '',
                                      desired_method=self.LXMF.LXMessage.DIRECT)
        def event(state, delivered):
            if state == 'delivered':
                delivered.write_to_directory(str(self.message_directory))
            return dict(event='message', id=request['request_id'], direction='tx', peer=peer,
                        destination=destination.hash.hex(), text=payload['text'], state=state,
                        message_hash=delivered.hash.hex() if delivered.hash else None,
                        bytes=len(payload['text'].encode()), timestamp=time.time())
        message.register_delivery_callback(lambda delivered: self.post(event('delivered', delivered)))
        message.register_failed_callback(lambda failed: self.post(event('failed', failed)))
        self.post(event('queued', message))
        self.router.handle_outbound(message)

    def _run(self, request):
        try:
            if request['action'] == 'connect':
                self._connect()
            elif request['action'] == 'announce':
                self.message_discovery=True
                self.router.announce(self.delivery.hash)
            elif request['action'] == 'send':
                self._send(request)
            self.post(dict(id=request['request_id'], action=request['action'], state='complete'))
        except Exception as error:
            self.post(dict(id=request['request_id'], action=request['action'], state='failed', error=str(error)[:512]))
        finally:
            self.busy = False
            self.post(dict(event='ready'))

    def dispatch(self, request):
        action = request.get('action') if isinstance(request, dict) else None
        if action=='message_discovery':
            payload=request.get('payload',{})
            if self.delivery is None or set(payload)!={'enabled'} or type(payload['enabled']) is not bool:raise ValueError('Choose messaging discovery explicitly')
            self.message_discovery=payload['enabled']
            if self.message_discovery:self.router.announce(self.delivery.hash)
            self.revision+=1
            return dict(version=1,message_discovery=self.message_discovery)
        if self.data_bridge is not None and isinstance(action,str) and action.startswith(('service_', 'data_bridge_')):
            from data_bridge import ACTIONS
            if action not in ACTIONS:raise ValueError('Unsupported data action')
            if request.get('version') != 1 or not isinstance(request.get('request_id'), str):
                raise ValueError('Invalid data request')
            result = self.data_bridge.dispatch(action, request.get('payload'))
            if action in ('service_call', 'service_cancel', 'service_share', 'service_snapshot', 'service_discovery'): return result
            self.last_job = dict(id=request['request_id'], action=action, state='complete')
            self.revision += 1
            return dict(version=1, job=self.last_job)
        if action in ('save_heard', 'rename_peer'):
            payload = request.get('payload')
            required = {'destination', 'label'} if action == 'save_heard' else {'peer', 'label'}
            if request.get('version') != 1 or not isinstance(payload, dict) or set(payload) != required:
                raise ValueError('Invalid local naming request')
            label = payload['label']
            if not isinstance(label, str) or not 1 <= len(label) <= 64 or not label.strip() or not label.isprintable():
                raise ValueError('Nickname must contain 1–64 printable characters')
            if action == 'save_heard':
                observation = self.heard_store.records.get(payload['destination'])
                if observation is None:
                    raise ValueError('Heard destination is no longer available')
                peer = self.book.import_contact(card(bytes.fromhex(observation['public_key']),label))
            else:
                peer = payload['peer']
            self.book.rename(peer, label)
            self.last_job = dict(id=request.get('request_id'), action=action, state='complete', peer=peer)
            self.revision += 1
            return dict(version=1, job=self.last_job)
        if action not in ('connect', 'send', 'announce'):
            refresh = action == 'verify_peer' and self.stack is not None
            if refresh and request.get('version') == 1 and isinstance(request.get('payload'), dict) and set(request['payload']) == {'peer', 'fingerprint'}:
                self._peer_mapping(request['payload']['peer'])
            result = super().dispatch(request)
            if action == 'revoke_peer':
                self.data_bridge.revoke(request['payload']['peer'])
            if refresh:
                self._remember_verified_peer(request['payload']['peer'])
            return result
        if request.get('version') != 1 or self.busy or not isinstance(request.get('request_id'), str):
            raise ValueError('Invalid request or owner busy')
        payload = request.get('payload', {})
        if not isinstance(payload, dict):
            raise ValueError('Invalid message parameters')
        if action == 'connect':
            if self.stack is not None or payload != dict(station=self.station, radio=self.transport_id):
                raise ValueError('Wrong transport owner or transport already started')
        elif self.delivery is None:
            raise ValueError('Connect the configured transport first')
        elif action == 'send':
            if set(payload) != {'peer', 'text'} or not isinstance(payload['text'], str) or not 1 <= len(payload['text'].encode()) <= 240:
                raise ValueError('Message must contain 1–240 UTF-8 bytes')
        elif payload:
            raise ValueError('Announce takes no parameters')
        self.busy = True
        self.last_job = dict(id=request['request_id'], action=action, state='running')
        self.revision += 1
        if action == 'connect':
            # Official RNS installs signal handlers during initialisation.
            # Keep this on the owner main thread; the desktop client is async.
            self._run(request)
        else:
            threading.Thread(target=self._run, args=(request,), daemon=True, name='official-lxmf-job').start()
        return dict(version=1, job=self.last_job)

    def drain(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            if event.get('event') == 'message':
                self.message_error = None
                contact = event.pop('contact', None)
                if contact:
                    self.book.import_contact(contact)
                self.messages = [m for m in self.messages if m['id'] != event['id']]
                self.messages = (self.messages + [event])[-32:]
                self._save_history()
                self.packets = (self.packets + [dict(station_id=self.station, radio_id=self.transport_id,
                    direction=event['direction'], kind='lxmf_' + event['state'], bytes=event['bytes'])])[-20:]
            elif event.get('event') == 'heard_ready':
                try:
                    observations = self.announce_observer.take()
                    self.heard_store.observe(observations)
                    self.heard_error = None
                    self.packets = (self.packets + [dict(station_id=row['station_id'], radio_id=row['radio_id'],
                        direction='rx', kind='announce:' + row['service'], bytes=None) for row in observations])[-20:]
                except (OSError, ValueError, TypeError) as error:
                    self.heard_error = ('Cannot save Heard observations: ' + str(error))[:240]
            elif event.get('event') == 'radio_state':
                self.radio_event = event['radio_event']
                self.error = self.radio_event.get('error')
                if self.radio_event.get('phase') in ('failed', 'offline', 'closed'):
                    self.data_bridge.close()
            elif event.get('event') == 'invalid_message':
                self.message_error = {key: event.get(key) for key in ('reason', 'error', 'message_hash', 'source')}
            elif event.get('event') == 'data_ready':
                # Service caches changed: wake subscribers even without a radio event.
                pass
            elif event.get('event') != 'ready':
                self.last_job = event
                self.error = event.get('error')
            self.revision += 1

    def close(self):
        self.data_bridge.close()
        if self.announce_observer and self.RNS:
            self.RNS.Transport.deregister_announce_handler(self.announce_observer)
            self.announce_observer = None
        if self.router:
            self.router.exit_handler()
        if self.stack:
            self.stack.exit_handler()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('socket', 'state', 'station', 'rns-config', 'transport-id'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--connection', required=True, choices=('usb', 'bluetooth', 'ble', 'hub', 'kiss', 'loopback'))
    parser.add_argument('--ready-fd', type=int)
    parser.add_argument('--service-owner-socket', type=Path)
    args = parser.parse_args()
    def stop(signum, frame):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    def factory(state, station):
        backend=LXMFBackend
        if args.connection in ('usb','bluetooth','hub','loopback'):
            from native_owner import installed_library,NativeBackend
            if installed_library() is not None:backend=NativeBackend
        owner = backend(state, station, args.rns_config, args.transport_id, args.connection)
        owner.service_owner_socket = args.service_owner_socket
        return owner
    serve(args.socket, args.state, args.station, factory, ready_fd=args.ready_fd)


if __name__ == '__main__':
    main()
