"""Bounded status requests and per-peer grants on the existing RNS identity."""
import secrets
from threading import RLock
from service_bridge import Services, PATH as SERVICE_PATH, ACTIONS as SERVICE_ACTIONS
from service_transport import LIMIT as SERVICE_LIMIT

PATH = '/pocket/data/v1'
SERVICE = 'pocket.data.v1'
ACTIONS = ('service_discovery', 'data_bridge_connect', 'data_bridge_request', 'data_bridge_disconnect') + SERVICE_ACTIONS
FIELDS = {'service_online', 'interface_online', 'radio_state', 'observed_at', 'source'}
LIMIT = 16


def projection(state):
    radios = state.get('radios') or ()
    interface = radios[0].get('interface_online') if len(radios) == 1 else None
    phase = state.get('radio_state', 'unknown')
    return dict(service_online=state.get('owner_online') if type(state.get('owner_online')) is bool else None,
                interface_online=interface if type(interface) is bool else None,
                radio_state=phase if phase in ('idle', 'opening', 'online', 'closing', 'error') else 'unknown',
                observed_at=None, source='reticulum-session-cache')


class DataBridge:
    def __init__(self, owner):
        self.owner = owner
        self.lock = RLock()
        self.destination = None
        self.public_discovery = False
        self.grants, self.requests = {}, {}
        self.epoch = secrets.token_hex(8)
        self.status = projection({})
        self.services = Services(self)

    def changed(self):
        self.owner.post(dict(event='data_ready'))

    def snapshot(self):
        with self.lock:
            state = dict(state='sharing' if self.grants else 'off', public_discovery=self.public_discovery, grants=list(self.grants),
                        requests=[{k:v for k,v in row.items() if k not in ('link','key','token')}
                                  for row in self.requests.values()])
            services = self.services.snapshot()
            if services: state['services'] = services
            if self.services.grants:
                state['service_grants'] = [dict(peer=p,service=s,operations=sorted(v[1])) for (p,s),v in self.services.grants.items()]
            return state

    def update(self, state):
        with self.lock: self.status = projection(state)

    def verified(self, peer, key):
        record = self.owner.book.contacts.get(peer) or {}
        return (record.get('state') == 'verified' and isinstance(key, bytes)
                and record.get('card', {}).get('public_key') == key.hex())

    def selection(self, payload):
        if (not isinstance(payload, dict) or set(payload) != {'peer','expected_public_key','service','capabilities'}
                or payload['service'] != SERVICE or payload['capabilities'] != ['status']):
            raise ValueError('Select the peer and status service explicitly')
        peer, encoded = payload['peer'], payload['expected_public_key']
        if not isinstance(peer, str) or not isinstance(encoded, str) or len(encoded) != 128:
            raise ValueError('Invalid peer key')
        key = bytes.fromhex(encoded)
        if not self.verified(peer, key): raise ValueError('Verify the selected peer fingerprint first')
        if self.owner.identity is None or self.owner.stack is None: raise ValueError('Connect Reticulum first')
        return peer, key

    def dispatch(self, action, payload):
        if not isinstance(payload,dict): raise ValueError('Invalid service payload')
        if action == 'service_discovery':
            if set(payload)!={'enabled'} or type(payload['enabled']) is not bool:raise ValueError('Choose public discovery explicitly')
            if self.destination is None:raise ValueError('Grant access to a verified peer first')
            self.public_discovery=payload['enabled']
            if self.public_discovery:self.destination.announce()
            self.changed()
            return dict(version=1,public_discovery=self.public_discovery)
        if action == 'service_snapshot': return self.services.get(payload)
        if action == 'service_call': return self.services.call(payload)
        if action == 'service_share':
            result = self.services.grant(payload); self.changed(); return result
        if action == 'service_cancel':
            result = self.services.cancel(payload); self.changed(); return result
        with self.lock:
            if action == 'data_bridge_disconnect':
                if not isinstance(payload, dict) or set(payload) != {'peer'} or not isinstance(payload['peer'], str):
                    raise ValueError('Select a peer to disconnect')
                self.revoke(payload['peer'])
            elif action in ('data_bridge_connect', 'data_bridge_request'):
                peer, key = self.selection(payload)
                if action == 'data_bridge_connect': self.share(peer, key)
                else: self.request(peer, key)
            else: raise ValueError('Unknown data action')
        self.changed()

    def share(self, peer, key):
        if peer not in self.grants and len(self.grants) >= LIMIT: raise ValueError('Sharing limit reached')
        RNS = self.owner.RNS
        created = self.destination is None
        if created:
            self.destination = RNS.Destination(self.owner.identity, RNS.Destination.IN,
                                               RNS.Destination.SINGLE, 'pocket','data','v1')
            self.destination.set_max_request_size(SERVICE_LIMIT)
            announce=self.destination.announce
            def guarded_announce(*args,**kwargs):
                # RNS also calls announce when answering path probes. Suppress
                # both unsolicited announces and probe responses by default.
                if self.public_discovery:return announce(*args,**kwargs)
            self.destination.announce=guarded_announce
        previous = self.grants.get(peer)
        self.grants[peer] = key
        try:
            self._permissions()
            # Granting access never publishes service presence.
        except Exception:
            if previous is None: self.grants.pop(peer, None)
            else: self.grants[peer] = previous
            if created: self._remove_destination()
            else: self._permissions()
            raise

    def _permissions(self):
        if self.destination:
            self.destination.register_request_handler(PATH, response_generator=self.respond,
                allow=self.owner.RNS.Destination.ALLOW_LIST,
                allowed_list=[bytes.fromhex(peer) for peer in self.grants], auto_compress=False)

            self.destination.register_request_handler(SERVICE_PATH, response_generator=self.services.respond,
                allow=self.owner.RNS.Destination.ALLOW_LIST,
                allowed_list=[bytes.fromhex(peer) for peer in self.grants], auto_compress=False)

    def respond(self, path, data, request_id, link_id, remote_identity, requested_at):
        from discovery_codec import codec
        umsgpack = codec()
        with self.lock:
            if remote_identity is None: return None
            peer, key = remote_identity.hash.hex(), remote_identity.get_public_key()
            if self.grants.get(peer) != key or not self.verified(peer, key): return None
            if not isinstance(data, bytes) or len(data) > 256: return None
            try:
                request = umsgpack.unpackb(data)
                if type(request) is not dict or request != {'v':1,'cap':'status'} or type(request['v']) is not int: return None
            except (ValueError, TypeError, umsgpack.UnpackException): return None
            return umsgpack.packb(dict(v=1, station=self.owner.identity.hash.hex(), epoch=self.epoch,
                                      capability='status', snapshot=self.status))

    def request(self, peer, key):
        previous = self.requests.get(peer)
        if previous and previous['pending']: raise ValueError('A request to this peer is already pending')
        if previous is None and len(self.requests) >= LIMIT: raise ValueError('Disconnect an unused peer first')
        RNS = self.owner.RNS
        from private_rendezvous import destination_for
        destination, route = destination_for(self.owner,peer,key)
        token = secrets.token_hex(16)
        self.requests[peer] = dict(peer=peer,key=key,token=token,pending=True,response=None,error=None,link=None,rendezvous=route)
        try:
            link = RNS.Link(destination,
                established_callback=lambda link:self.established(peer,token,link),
                closed_callback=lambda link:self.failed(peer,token,'Peer link closed'))
            row = self.current(peer,token)
            if row and row['pending']: row['link'] = link
            else: link.teardown()
        except Exception:
            self.failed(peer,token,'Could not open peer link')
            raise

    def current(self, peer, token):
        row = self.requests.get(peer)
        return row if row and row['token'] == token and self.verified(peer,row['key']) else None

    def established(self, peer, token, link):
        from discovery_codec import codec
        umsgpack = codec()
        with self.lock:
            row = self.current(peer,token)
            remote = link.get_remote_identity()
            if not row or not row['pending'] or remote is None or remote.get_public_key() != row['key']:
                self.failed(peer,token,'Peer key did not match'); link.teardown(); return
            row['link'] = link
            link.identify(self.owner.identity)
            receipt = link.request(PATH, data=umsgpack.packb(dict(v=1,cap='status')),
                response_callback=lambda receipt:self.received(peer,token,receipt),
                failed_callback=lambda receipt:self.failed(peer,token,'Status request failed'),timeout=20,max_response_size=2048)
            if receipt is None: self.failed(peer,token,'Status request was not accepted')

    def received(self, peer, token, receipt):
        from discovery_codec import codec
        umsgpack = codec()
        try:
            raw = receipt.response
            if not isinstance(raw,bytes) or len(raw)>2048: raise ValueError('Invalid status size')
            value = umsgpack.unpackb(raw)
            if (type(value) is not dict or set(value) != {'v','station','epoch','capability','snapshot'}
                    or type(value['v']) is not int or value['v'] != 1 or value['station'] != peer
                    or value['capability'] != 'status' or not isinstance(value['epoch'],str) or len(value['epoch']) != 16):
                raise ValueError('Invalid status envelope')
            state = value['snapshot']
            if type(state) is not dict or set(state) != FIELDS: raise ValueError('Invalid status fields')
            if any(state[k] is not None and type(state[k]) is not bool for k in ('service_online','interface_online')):
                raise ValueError('Invalid status values')
            if (state['radio_state'] not in ('idle','opening','online','closing','error','unknown')
                    or state['observed_at'] is not None or state['source'] != 'reticulum-session-cache'):
                raise ValueError('Invalid status provenance')
            with self.lock:
                row = self.current(peer,token)
                if not row or not row['pending']: return
                row.update(response=state,pending=False,error=None)
                self.finish(row)
            self.changed()
        except (ValueError,TypeError,umsgpack.UnpackException): self.failed(peer,token,'Peer returned invalid status')

    def failed(self, peer, token, error):
        with self.lock:
            row = self.current(peer,token)
            if not row or not row['pending']: return
            row.update(pending=False,error=error)
            self.finish(row)
        self.changed()

    def finish(self, row):
        link, row['link'] = row['link'], None
        if link: link.teardown()

    def revoke(self, peer):
        self.services.revoke(peer)
        with self.lock:
            self.grants.pop(peer,None)
            row = self.requests.pop(peer,None)
            if row: self.finish(row)
            if self.destination:
                for link in tuple(self.destination.links):
                    identity = link.get_remote_identity()
                    if identity is None or identity.hash.hex() == peer: link.teardown()
                if self.grants: self._permissions()
                else: self._remove_destination()
        self.changed()

    def _remove_destination(self):
        self.public_discovery=False
        destination, self.destination = self.destination, None
        if destination:
            destination.deregister_request_handler(PATH)
            destination.deregister_request_handler(SERVICE_PATH)
            for link in tuple(destination.links): link.teardown()
            self.owner.RNS.Transport.deregister_destination(destination)

    def close(self):
        self.services.close()
        with self.lock:
            self.grants.clear()
            rows, self.requests = self.requests, {}
            for row in rows.values(): self.finish(row)
            self._remove_destination()
