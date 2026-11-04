"""RNS adapter for existing owner services; explicit grants, bounded push subscriptions."""
from collections import OrderedDict
import hashlib
import secrets
from pathlib import Path
import threading
import time

from service_transport import SocketTransport, encode, decode, LIMIT, request_timeout

PATH = '/pocket/services/v2'
ACTIONS = ('service_share', 'service_call', 'service_cancel', 'service_snapshot')
MAX_PEERS = 16


class Services:
    def __init__(self, bridge):
        self.bridge = bridge
        self.exports, self.grants, self.clients, self.subscribers = {}, {}, {}, {}
        self.prepare = {}
        self.completed = OrderedDict()
        self.inflight = {}
        self.path_requests = OrderedDict()
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(4)
        self.closed = False

    def register(self, name, path, operations, prepare=None):
        if not isinstance(name, str) or not 1 <= len(name) <= 64 or not name.replace('-', '').replace('.', '').isalnum():
            raise ValueError('Invalid service name')
        if not Path(path).is_absolute(): raise ValueError('Service socket path must be absolute')
        if not isinstance(operations,(list,tuple,set,frozenset)) or len(operations)>32 or any(not isinstance(op,str) or not 1<=len(op)<=64 for op in operations):
            raise ValueError('Invalid service operations')
        if len(self.exports) >= MAX_PEERS and name not in self.exports: raise ValueError('Service limit reached')
        self.exports[name] = (str(path), frozenset(operations) | {'snapshot', 'subscribe'})
        if prepare is not None:self.prepare[name]=prepare

    def snapshot(self):
        with self.lock:
            return [dict(peer=p, service=s, session=session, revision=row.get('revision',0), error=row.get('error'))
                    for (p,s,session),row in self.clients.items()]

    def get(self,payload):
        with self.lock:
            row=self.clients.get((payload.get('peer'),payload.get('service'),payload.get('session')))
            if row is None or row.get('error'):raise ValueError((row or {}).get('error') or 'Service is not attached')
            if row.get('snapshot') is None:raise ValueError('Waiting for service snapshot')
            return row['snapshot']

    def grant(self, payload):
        if self.closed: raise ValueError('Service transport is closed')
        peer, key = self.bridge.selection(dict(peer=payload.get('peer'), expected_public_key=payload.get('expected_public_key'),
                                       service='pocket.data.v1', capabilities=['status']))
        service, operations = payload.get('service'), payload.get('operations')
        if service not in self.exports or not isinstance(operations,list) or not operations or any(not isinstance(v,str) for v in operations):
            raise ValueError('Choose an exported service and its operations')
        if not set(operations) <= self.exports[service][1]: raise ValueError('Operation is not exported')
        if service in self.prepare:self.prepare[service]()
        with self.lock:
            if (peer,service) not in self.grants and len(self.grants)>=MAX_PEERS: raise ValueError('Grant limit reached')
            previous=self.grants.get((peer,service))
            self.grants[peer,service] = (key, frozenset(operations))
            try: self.bridge.share(peer,key)
            except BaseException:
                if previous is None:self.grants.pop((peer,service),None)
                else:self.grants[peer,service]=previous
                raise
            if 'subscribe' not in operations:
                for identifier,row in list(self.subscribers.items()):
                    if identifier[:2]==(peer,service):
                        row['stop'].set();row['transport'].close();row['link'].teardown()
                        self.subscribers.pop(identifier,None)
        return dict(version=1, service=service, operations=operations)

    def allowed(self, peer, key, service, operation):
        grant = self.grants.get((peer,service))
        return bool(grant and grant[0] == key and operation in grant[1] and self.bridge.verified(peer,key))

    def filtered(self, state, peer, service):
        result = dict(state)
        result.pop('data_bridge',None)
        result['capabilities'] = [a for a in result.get('capabilities',()) if a in self.grants.get((peer,service),(None,()))[1]]
        # Bridge housekeeping is not an application event and must not echo itself.
        if str((result.get('last_job') or {}).get('action','')).startswith(('service_', 'data_bridge_')):
            result['last_job'] = None
        return result

    def respond(self,path,data,request_id,link_id,remote_identity,requested_at):
        if not self.slots.acquire(blocking=False): return encode(dict(version=1,error='Service busy; command was not executed'))
        try:
            if remote_identity is None: return None
            peer,key=remote_identity.hash.hex(),remote_identity.get_public_key()
            envelope=decode(data)
            service,request=envelope.get('service'),envelope.get('request')
            if not isinstance(request,dict) or type(request.get('version')) is not int or request['version']!=1: raise ValueError('Invalid owner request')
            operation=request.get('action');identity=envelope.get('id')
            if not isinstance(identity,str) or len(identity)!=32 or not isinstance(service,str): raise ValueError('Invalid request identity')
            with self.lock:
                if self.closed or not self.bridge.verified(peer,key):raise ValueError('Service identity is not verified')
                if service=='$catalog' and operation=='snapshot':
                    return encode(dict(version=1,services=[dict(id=name,operations=sorted(grant[1]))
                        for (granted_peer,name),grant in self.grants.items() if granted_peer==peer and grant[0]==key]))
                if not self.allowed(peer,key,service,operation): raise ValueError('Service operation not granted')
                export=self.exports[service]
                cache_key=(peer,service,identity)
                fingerprint=hashlib.sha256(data).digest()
                if cache_key in self.completed:
                    previous,result=self.completed[cache_key]
                    if previous!=fingerprint:raise ValueError('Request ID reused for a different operation')
                    return result
                # Reserve before dispatch: concurrent duplicate commands never execute twice.
                self.completed[cache_key]=(fingerprint,encode(dict(version=1,error='Request already accepted; outcome unavailable')))
                while len(self.completed)>128:self.completed.popitem(last=False)
            transport=SocketTransport(export[0])
            if operation=='subscribe':
                link=next((l for l in self.bridge.destination.links if l.link_id==link_id),None)
                if link is None:raise ValueError('Subscription link unavailable')
                result=self.filtered(transport.exchange(dict(version=1,action='snapshot')),peer,service)
                self.subscribe(peer,key,service,link,transport)
            else:
                result=transport.exchange(request)
                if operation=='snapshot':result=self.filtered(result,peer,service)
            raw=encode(result)
            with self.lock:
                # Recheck authorization after a potentially slow operation.
                if not self.allowed(peer,key,service,operation):return encode(dict(version=1,error='Service grant revoked'))
                self.completed[cache_key]=(fingerprint,raw)
            return raw
        except (ValueError,TypeError,KeyError,OSError) as error:return encode(dict(version=1,error=str(error)[:240]))
        finally:self.slots.release()

    def subscribe(self,peer,key,service,link,transport):
        identifier=(peer,service,link.link_id)
        with self.lock:
            if identifier in self.subscribers:return
            if len(self.subscribers)>=MAX_PEERS:raise ValueError('Subscription limit reached')
            stop=threading.Event()
            row=dict(stop=stop,transport=transport,link=link,latest=None,sending=False,previous=None)
            self.subscribers[identifier]=row
        def publish(state):
            state=self.filtered(state,peer,service)
            # Ignore revisions caused solely by gateway activity.
            comparable=dict(state);comparable.pop('revision',None)
            comparable['radios']=[{k:v for k,v in radio.items() if k not in ('rx_bytes','tx_bytes')} for radio in comparable.get('radios',())]
            with self.lock:
                if stop.is_set() or row['previous']==comparable:return
                row['sequence']=row.get('sequence',0)+1
                raw=encode(dict(version=1,sequence=row['sequence'],snapshot=state))
                row['previous']=comparable;row['latest']=raw
            self.push(identifier)
        def closed(link):
            stop.set();transport.close()
        link.set_link_closed_callback(closed)
        def watch():
            try:transport.subscribe(publish,stop)
            except (OSError,ValueError):link.teardown()
            finally:
                with self.lock:self.subscribers.pop(identifier,None)
                transport.close()
        threading.Thread(target=watch,name='service-events',daemon=True).start()

    def push(self,identifier):
        peer,service,_=identifier
        with self.lock:
            row=self.subscribers.get(identifier)
            grant=self.grants.get((peer,service))
            if not row or row['stop'].is_set():return
            if not grant or not self.allowed(peer,grant[0],service,'subscribe'):
                row['stop'].set();row['transport'].close();row['link'].teardown();return
            if row['sending'] or row['latest'] is None:return
            raw,row['latest']=row['latest'],None;row['sending']=True
        def delivered(resource):
            with self.lock:row['sending']=False
            if resource.status!=self.bridge.owner.RNS.Resource.COMPLETE:
                row['stop'].set();row['transport'].close();row['link'].teardown()
            else:self.push(identifier)
        self.bridge.owner.RNS.Resource(raw,row['link'],callback=delivered,auto_compress=False)

    def accept_update(self,identifier,row,raw):
        frame=decode(raw)
        if set(frame)!={'version','sequence','snapshot'} or type(frame['sequence']) is not int or not 1<=frame['sequence']<2**63:
            raise ValueError('Invalid service update sequence')
        value=frame['snapshot']
        if not isinstance(value,dict) or type(value.get('version')) is not int or value['version']!=1:
            raise ValueError('Invalid service snapshot')
        if value.get('error'):raise ValueError(str(value['error'])[:240])
        with self.lock:
            if self.clients.get(identifier) is not row or not row['active'] or not self.bridge.verified(identifier[0],row['key']):return
            if frame['sequence']<=row.get('sequence',0):return
            row['sequence']=frame['sequence'];row['snapshot']=value;row['error']=None
            row['revision']=row.get('revision',0)+1
        self.bridge.changed()

    def call(self,payload):
        if self.closed: raise ValueError('Service transport is closed')
        timeout=request_timeout(dict(action='service_call',payload=payload))
        peer,service,session=payload.get('peer'),payload.get('service'),payload.get('session')
        request=payload.get('request')
        if not isinstance(service,str) or not isinstance(session,str) or len(session)!=16 or not isinstance(request,dict):raise ValueError('Invalid selected service')
        contact=self.bridge.owner.book.contacts.get(peer,{})
        key=bytes.fromhex(contact.get('card',{}).get('public_key',''))
        if not self.bridge.verified(peer,key):raise ValueError('Verify selected peer first')
        RNS=self.bridge.owner.RNS
        if RNS is None or self.bridge.owner.identity is None:raise ValueError('Connect Reticulum first')
        from private_rendezvous import destination_for
        destination,route=destination_for(self.bridge.owner,peer,key)
        raw=encode(dict(version=1,id=secrets.token_hex(16),service=service,request=request))
        done=threading.Event();result={};identifier=(peer,service,session)
        subscribed=request.get('action')=='subscribe'
        row=dict(snapshot=None,error=None,link=None,key=key,active=True)
        invocation=secrets.token_hex(16)
        with self.lock:
            if len(self.inflight)>=4:raise ValueError('Service request limit reached')
            if subscribed and len(self.clients)>=MAX_PEERS and identifier not in self.clients:raise ValueError('Selected service limit reached')
            self.inflight[invocation]=(peer,row,done,result)
        if subscribed:
            with self.lock:
                self.cancel(dict(peer=peer,service=service,session=session))
                self.clients[identifier]=row
        def fail(message):
            row['active']=False
            if not done.is_set():result['error']=message;done.set()
            if subscribed:
                with self.lock:
                    if self.clients.get(identifier) is row:row['error']=message
                self.bridge.changed()
        def receive(resource):
            if resource.status!=RNS.Resource.COMPLETE:return
            try:
                self.accept_update(identifier,row,resource.data.read(LIMIT+1))
            except (OSError,ValueError) as error:fail(str(error))
        def response(receipt):
            try:
                value=decode(receipt.response)
                if not row['active']:raise ValueError('Service request cancelled')
                if not self.bridge.verified(peer,key):raise ValueError('Peer verification revoked')
                result['value']=value
                if subscribed:
                    with self.lock:
                        if self.clients.get(identifier) is row and row.get('snapshot') is None:
                            row['snapshot']=value;row['revision']=row.get('revision',0)+1
                    self.bridge.changed()
            except (ValueError,TypeError) as error:result['error']=str(error)
            done.set()
        def established(link):
            remote=link.get_remote_identity()
            if not remote or remote.get_public_key()!=key:fail('Peer identity mismatch');link.teardown();return
            if not row['active']:link.teardown();return
            row['link']=link
            if subscribed:
                link.set_resource_strategy(RNS.Link.ACCEPT_APP)
                link.set_resource_callback(lambda advertisement: advertisement.get_data_size()<=LIMIT and row['active'])
                link.set_resource_concluded_callback(receive)
            link.identify(self.bridge.owner.identity)
            receipt=link.request(PATH,data=raw,response_callback=response,failed_callback=lambda receipt:fail('Request failed; outcome unknown'),timeout=timeout,max_response_size=LIMIT)
            if not receipt:fail('Service request was not accepted')
        link=None
        try:
            link=RNS.Link(destination,established_callback=established,closed_callback=lambda link:fail('Service link closed; outcome unknown'))
            row['link']=link
            if not done.wait(timeout+5):raise ValueError('Service request timed out; outcome unknown')
            if result.get('error'):raise ValueError(result['error'])
            return result['value']
        finally:
            with self.lock:self.inflight.pop(invocation,None)
            if not subscribed or result.get('error') or not done.is_set():
                row['active']=False
                if link:link.teardown()

    def cancel(self,payload):
        identifier=(payload.get('peer'),payload.get('service'),payload.get('session'))
        with self.lock:
            row=self.clients.pop(identifier,None)
            if row:
                row['active']=False
                if row['link']:row['link'].teardown()
        return dict(version=1,cancelled=True)

    def revoke(self,peer):
        with self.lock:
            for active_peer,row,done,result in self.inflight.values():
                if active_peer==peer:
                    row['active']=False;result['error']='Service cancelled; command outcome may be unknown';done.set()
                    if row['link']:row['link'].teardown()
            for key in list(self.grants):
                if key[0]==peer:self.grants.pop(key)
            for identifier,row in list(self.subscribers.items()):
                if identifier[0]==peer:
                    row['stop'].set();row['transport'].close();row['link'].teardown();self.subscribers.pop(identifier,None)
            for identifier in list(self.clients):
                if identifier[0]==peer:self.cancel(dict(zip(('peer','service','session'),identifier)))
            for key in list(self.completed):
                if key[0]==peer:self.completed.pop(key)

    def close(self):
        self.closed=True
        for peer in set(k[0] for k in self.grants)|set(k[0] for k in self.clients)|{v[0] for v in self.inflight.values()}:self.revoke(peer)
