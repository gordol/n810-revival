"""Commands and pushed subscriptions over real RNS links and existing Unix owners."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

DOMAIN=Path(__file__).resolve().parents[2]/'shell/vendor/apps/domains/reticulum'
sys.path.insert(0,str(DOMAIN))
from owner import Owner,serve,exchange
from service_transport import ReticulumTransport,SocketTransport


def node(root,role):
    executor=None
    import RNS
    from lxmf_owner import LXMFBackend
    if os.environ.get('POCKET_RNS_TRACE') and role!='notes':
        original_transmit=RNS.Transport.transmit
        trace_count=[0]
        def trace_transmit(interface,raw):
            if trace_count[0]<128:
                trace_count[0]+=1
                packet=RNS.Packet(None,raw);packet.unpack()
                print('stock',role,'TX',packet.packet_type,packet.context,packet.destination_hash.hex(),'via='+str(packet.transport_id.hex() if packet.transport_id else None),'hops='+str(packet.hops),str(interface),file=sys.stderr,flush=True)
            return original_transmit(interface,raw)
        RNS.Transport.transmit=trace_transmit
    if os.environ.get('POCKET_TEST_DROP_RESOURCE_PART') and role=='hub':
        transmit=RNS.Transport.transmit;parts=[0]
        def drop_part(interface,raw):
            packet=RNS.Packet(None,raw);packet.unpack()
            if packet.context==RNS.Packet.RESOURCE:
                parts[0]+=1
                if parts[0]==2:
                    (root/'dropped-resource-part.json').write_text(json.dumps(dict(part=parts[0],bytes=len(raw))))
                    return
            return transmit(interface,raw)
        RNS.Transport.transmit=drop_part
    from contacts import card,fingerprint
    def factory(state,station):
        nonlocal executor
        if role=='notes':
            class Notes(Owner):
                value='initial-'+'x'*5000
                def snapshot(self):return dict(version=1,owner_online=True,revision=self.revision,capabilities=['put'],value=self.value)
                def dispatch(self,request):
                    if request.get('action')=='put':
                        self.value=request['payload']['value'];self.revision+=1
                        return dict(version=1,written=True,revision=self.revision)
                    if request.get('action')=='snapshot':return self.snapshot()
                    raise ValueError('Unsupported operation')
            return Notes(state,station)
        identity=RNS.Identity.from_file(str(root/(role+'.key')))
        identity.to_file(str(Path(state)/'identity'));os.chmod(Path(state)/'identity',0o600)
        backend=LXMFBackend
        if role==os.environ.get('POCKET_TEST_NATIVE_ROLE'):
            from native_owner import NativeBackend
            backend=NativeBackend
        extra={}
        if role==os.environ.get('POCKET_TEST_EXTERNAL_ROLE'):
            from native_owner import installed_library
            from node_transport import SocketTransport as NodeTransport
            endpoint=os.environ.get('POCKET_TEST_EXTERNAL_ENDPOINT')
            if endpoint:
                from external_node import Connection,probe
                from contextlib import nullcontext
                connection=Connection(endpoint);connection.__enter__()
                try:
                    info=probe(endpoint,connection=lambda _:nullcontext(connection))['offload']
                    extra['remote']=dict(transport=connection.owner_transport(),info=info)
                except BaseException:connection.__exit__(None,None,None);raise
                executor=connection
            else:
                node_socket=root/(role+'-node.sock');node_state=root/(role+'-node');node_state.mkdir(mode=0o700)
                executor=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parents[1]/'fixtures/native_executor.py'),str(node_socket),str(node_state),str(installed_library()),str(root/role)],stderr=open(root/(role+'-executor.log'),'wb'))
                deadline=time.monotonic()+15
                while not node_socket.exists():
                    if executor.poll() is not None or time.monotonic()>deadline:raise RuntimeError('External executor failed')
                    time.sleep(.01)
                transport=NodeTransport(node_socket);info=transport.exchange(dict(version=1,action='node_info'))
                extra['remote']=dict(transport=transport,info=info)
        owner=backend(state,station,root/role,'loopback','loopback',**extra)
        for name in ('hub','a','b'):
            if name!=role:
                peer=RNS.Identity.from_file(str(root/(name+'.key')))
                identifier=owner.book.import_contact(json.dumps(card(peer.get_public_key(),name)))
                owner.book.verify(identifier,fingerprint(peer.get_public_key()))
        owner._connect()
        rns_api=owner.RNS
        original=owner.dispatch
        def dispatch(request):
            if request.get('action')=='test_stamp_requirement':
                owner.router.set_inbound_stamp_cost(owner.delivery.hash,3);owner.router.announce(owner.delivery.hash)
                return dict(version=1,cost=3)
            if request.get('action')=='test_peer_stamp_cost':
                return dict(version=1,cost=owner.router.stamp_cost(bytes.fromhex(request['payload']['destination'])))
            if request.get('action')=='test_large_lxmf':
                owner._send(dict(version=1,action='send',request_id='large-rx',payload=dict(peer=request['payload']['peer'],text='Compressed resource '+('z'*6000))))
                return dict(version=1,queued=True)
            if request.get('action')=='test_paths':
                return dict(version=1,native_error=getattr(owner.stack,'last_error',None),native_loop=bool(getattr(owner.stack,'thread',None) and owner.stack.thread.is_alive()),native_radio=bool(getattr(getattr(owner,'native_radio',None),'online',False)),path_details={p.hex():dict(hops=v[2],via=v[1].hex() if v[1] else None,interface=str(v[5])) for p,v in rns_api.Transport.path_table.items()},transport_identity=getattr(getattr(rns_api.Transport,'identity',None),'hexhash',None),paths=[rns_api.Destination.hash_from_name_and_identity('pocket.data.v1',RNS.Identity.from_file(str(root/(name+'.key')))).hex() for name in ('hub','a','b') if rns_api.Transport.has_path(rns_api.Destination.hash_from_name_and_identity('pocket.data.v1',RNS.Identity.from_file(str(root/(name+'.key')))))],destinations=[d.hash.hex() for d in rns_api.Transport.destinations],
                            grants=list(owner.data_bridge.grants),transport=rns_api.Reticulum.transport_enabled(),
                            clients=owner.data_bridge.services.snapshot(),subscriptions=[dict(sending=r['sending'],latest=len(r['latest'] or b''),stopped=r['stop'].is_set()) for r in owner.data_bridge.services.subscribers.values()])
            return original(request)
        owner.dispatch=dispatch
        return owner
    def stop(signum,frame):raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    try:serve(root/(role+'.sock'),root/(role+'-state'),role,factory)
    finally:
        if executor is not None:
            if isinstance(executor,subprocess.Popen):executor.terminate();executor.wait(10)
            else:executor.__exit__(None,None,None)


def main(carrier="tcp"):
    import RNS
    import threading
    with tempfile.TemporaryDirectory(prefix='p-svc-',dir='/tmp') as temporary:
        root=Path(temporary);children=[];transports=[];providers=[]
        probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
        from carriers import configuration
        wires=[];wire_stop=threading.Event();wire_data=bytearray()
        profiles={r:[] for r in ('hub','a','b')}
        if carrier=='tcp':
            profiles['hub']=[dict(type='tcp-server',host='127.0.0.1',port=port)]
            for role in ('a','b'):profiles[role]=[dict(type='tcp-client',host='127.0.0.1',port=port)]
        else:
            import pty,selectors
            for role in ('a','b'):
                ends=[]
                for side in ('hub',role):
                    master,slave=pty.openpty();wires.extend((master,slave));ends.append(master)
                    profile=dict(type=carrier,port=os.ttyname(slave),speed=115200)
                    if carrier=='ax25':profile.update(callsign='N0CALL',ssid={'hub':0,'a':1,'b':2}[side])
                    profiles[side].append(profile)
                def wire(pair=ends):
                    with selectors.DefaultSelector() as selector:
                        for source,target in (pair,pair[::-1]):selector.register(source,selectors.EVENT_READ,target)
                        while not wire_stop.is_set():
                            for key,_ in selector.select(.1):
                                raw=os.read(key.fd,8192)
                                if len(wire_data)<2000000:wire_data.extend(raw)
                                offset=0
                                while offset<len(raw):offset+=os.write(key.data,raw[offset:])
                threading.Thread(target=wire,daemon=True).start()
        identities={r:RNS.Identity() for r in ('hub','a','b')}
        for role in ('notes','hub','a','b'):
            (root/(role+'-state')).mkdir(mode=0o700)
            if role=='notes':continue
            identities[role].to_file(str(root/(role+'.key')));(root/role).mkdir()
            text=configuration(profiles[role],relay=role=='hub')
            if role=='hub' and os.environ.get('POCKET_TEST_HARDWARE_INTERFACE'):
                text+=Path(os.environ['POCKET_TEST_HARDWARE_INTERFACE']).read_text()
            (root/role/'config').write_text(text)
        config=root/'hub-state/service-exports.json';config.write_text(json.dumps(dict(notes=dict(socket=str(root/'notes.sock'),operations=['put']))));config.chmod(0o600)
        def wait(predicate,label,seconds=25):
            deadline=time.monotonic()+seconds;last=None;first_errors=[]
            while time.monotonic()<deadline:
                try:
                    if predicate():return
                except (OSError,ValueError) as error:
                    last=str(error)
                    if last not in first_errors and len(first_errors)<4:first_errors.append(last)
                time.sleep(.05)
            raise AssertionError(label + ": " + str(first_errors)+" latest="+str(last) + " " + str({r:call(r,'test_paths') for r in ('hub','a','b') if (root/(r+'.sock')).exists()}))
        def call(role,action,payload=None):return exchange(root/(role+'.sock'),dict(version=1,request_id=os.urandom(8).hex(),action=action,payload=payload or {}))
        def share(role,peer,service,operations):
            identity=identities[peer]
            return call(role,'service_share',dict(peer=identity.hash.hex(),expected_public_key=identity.get_public_key().hex(),service=service,operations=operations))
        def remote(role,peer,service):
            transport=ReticulumTransport(root/(role+'.sock'),identities[peer].hash.hex(),service);transports.append(transport);return transport
        def read(transport):return transport.exchange(dict(version=1,action='snapshot'))
        try:
            for role in ('notes','hub','a','b'):
                child=subprocess.Popen([sys.executable,__file__,str(root),role],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);children.append(child)
                wait(lambda:call(role,'snapshot').get('owner_online'),role+' owner unavailable')
            for role in ('a','b'):
                wait(lambda role=role:call(role,'snapshot')['radios'][0]['interface_online'],'loopback interface unavailable')
            share('hub','a','notes',['snapshot','subscribe','put'])
            share('hub','b','notes',['snapshot','subscribe'])
            share('a','b','reticulum',['snapshot','subscribe','rename_peer'])
            call('hub','service_discovery',dict(enabled=True))
            call('a','service_discovery',dict(enabled=True))
            selected=RNS.Destination.hash_from_name_and_identity('pocket.data.v1',identities['a']).hex()
            wait(lambda:selected in call('b','test_paths')['paths'],'signed route to selected service unavailable')
            a=remote('a','hub','notes');b=remote('b','hub','notes');relayed=remote('b','a','reticulum')
            wait(lambda:read(a).get('value','').startswith('initial-'),'RNS service path unavailable')
            wait(lambda:read(b).get('value','').startswith('initial-'),'second selected owner unavailable')
            wait(lambda:read(relayed).get('owner_online'),'relayed owner unavailable')
            catalog=remote('b','hub','$catalog')
            assert read(catalog)['services']==[dict(id='notes',operations=['snapshot','subscribe'])]
            received=[];stop=threading.Event();errors=[]
            def subscribe():
                try:b.subscribe(received.append,stop)
                except (OSError,ValueError) as error:
                    if not stop.is_set():errors.append(str(error))
            worker=threading.Thread(target=subscribe,daemon=True);worker.start()
            wait(lambda:received,'subscription initial state missing')
            body='command-'+'z'*6000
            result=a.exchange(dict(version=1,request_id='one-write',action='put',payload=dict(value=body)))
            assert result['written']
            try:wait(lambda:any(row.get('value')==body for row in received),'pushed update absent')
            except AssertionError as error:raise AssertionError(str(error)+' consumer errors='+str(errors)+' revisions='+str([r.get('revision') for r in received])) from error
            assert SocketTransport(str(root/'notes.sock')).exchange(dict(version=1,action='snapshot'))['value']==body
            try:b.exchange(dict(version=1,action='put',payload=dict(value='unauthorized')))
            except ValueError:pass
            else:raise AssertionError('Read grant allowed command')
            result=relayed.exchange(dict(version=1,request_id='rename',action='rename_peer',payload=dict(peer=identities['hub'].hash.hex(),label='Renamed over mesh')))
            assert result['job']['state']=='complete'
            assert any(p.get('label')=='Renamed over mesh' for p in call('a','snapshot')['peers'])
            from provider import Provider
            app=Provider(root/'b.sock',transport=remote('b','a','reticulum'));providers.append(app)
            wait(lambda:app.snapshot().get('owner_online') and 'rename_peer' in app.snapshot().get('capabilities',()),'app provider did not attach')
            app.request('rename_peer',dict(peer=identities['hub'].hash.hex(),label='Changed through app provider'))
            wait(lambda:any(p.get('label')=='Changed through app provider' for p in app.snapshot().get('peers',())),'app provider missed command event')
            assert len(call('b','snapshot')['data_bridge']['services'])==2,'independent services were replaced'
            call('hub','data_bridge_disconnect',dict(peer=identities['b'].hash.hex()))
            wait(lambda:errors,'revocation did not terminate subscription')
            assert read(a)['value']==body,'revocation disrupted another peer'
            stop.set();b.close();worker.join(4)
            assert not worker.is_alive()
            for role in ('a','b'):
                wait(lambda role=role:bool(call(role,'snapshot').get('lxmf_destination')),role+' messaging unavailable',seconds=40)
                call(role,'message_discovery',dict(enabled=True))
            # Exercise actual official LXMF delivery, not only owner-service calls.
            call('a','send',dict(peer=identities['b'].hash.hex(),text='LXMF conversation hello'))
            wait(lambda:any(m.get('text')=='LXMF conversation hello' and m.get('direction')=='rx' and m.get('signature_valid') for m in call('b','snapshot')['messages']),'LXMF incoming message missing',seconds=50)
            wait(lambda:any(m.get('text')=='LXMF conversation hello' and m.get('state')=='delivered' for m in call('a','snapshot')['messages']),'LXMF receipt missing',seconds=50)
            call('b','send',dict(peer=identities['a'].hash.hex(),text='LXMF conversation reply'))
            wait(lambda:any(m.get('text')=='LXMF conversation reply' and m.get('direction')=='rx' for m in call('a','snapshot')['messages']),'LXMF reply missing',seconds=50)
            if os.environ.get('POCKET_TEST_NATIVE_ROLE')=='a':
                call('b','test_large_lxmf',dict(peer=identities['a'].hash.hex()))
                wait(lambda:any(m.get('direction')=='rx' and m.get('text','').startswith('Compressed resource ') for m in call('a','snapshot')['messages']),'compressed LXMF resource missing',seconds=50)
                call('b','test_stamp_requirement')
                destination=RNS.Destination.hash_from_name_and_identity('lxmf.delivery',identities['b']).hex()
                wait(lambda:call('a','test_peer_stamp_cost',dict(destination=destination))['cost']==3,'signed recipient stamp cost missing')
                call('a','send',dict(peer=identities['b'].hash.hex(),text='Stamped hello'))
                wait(lambda:any(m.get('text')=='Stamped hello' and m.get('direction')=='rx' for m in call('b','snapshot')['messages']),'stamped LXMF message missing',seconds=50)
                wait(lambda:any(m.get('text')=='Stamped hello' and m.get('state')=='delivered' for m in call('a','snapshot')['messages']),'stamped LXMF receipt missing',seconds=50)
            import LXMF
            RNS.loglevel=RNS.LOG_ERROR
            for identity in identities.values():
                destination=RNS.Destination.hash_from_name_and_identity('lxmf.delivery',identity)
                RNS.Identity.remember(None,destination,identity.get_public_key())
            for role in ('a','b'):
                saved=list((root/(role+'-state')/'messages').iterdir())
                assert saved,role+' has no saved LXMF messages'
                for path in saved:
                    if path.name.startswith('.'):continue
                    with path.open('rb') as stream:message=LXMF.LXMessage.unpack_from_file(stream)
                    assert message and message.signature_validated,(role,path.name)
                    if message.content_as_string()=='Stamped hello':assert message.validate_stamp(3)
            if carrier!='tcp':assert body.encode() not in wire_data and b'Changed through app provider' not in wire_data
            dropped=None
            if os.environ.get('POCKET_TEST_DROP_RESOURCE_PART'):
                dropped=json.loads((root/'dropped-resource-part.json').read_text())
                assert dropped['part']==2 and dropped['bytes']>0,'Resource loss was not exercised'
            print(json.dumps(dict(carrier=carrier,lxmf_chat=True,passed=True,real_rns=True,instances=3,unix_owner=True,relayed_command=True,
                                 payload_bytes=len(body),push_subscription=True,app_provider=True,concurrent_services=2,read_only_enforced=True,
                                 independent_revocation=True,dropped_resource_part=dropped,rf=False)))
        finally:
            for provider in providers:provider.close()
            for transport in transports:transport.close()
            for child in children:
                if child.poll() is None:child.terminate()
            for child in children:
                try:child.wait(12)
                except subprocess.TimeoutExpired:child.kill();child.wait()
                if child.returncode not in (0,-15) or os.environ.get('POCKET_RNS_TRACE'):print(child.stderr.read().decode(),file=sys.stderr)
            wire_stop.set()
            for descriptor in wires:os.close(descriptor)

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--carrier':main(sys.argv[2])
    elif len(sys.argv)>1:node(Path(sys.argv[1]),sys.argv[2])
    else:main()
