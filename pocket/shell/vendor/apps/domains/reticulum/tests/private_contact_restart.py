"""Real owner restart acceptance in offline loopback sandbox, never radio hardware."""
import json,os,select,socket,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import RNS
from contacts import card,fingerprint
from data_bridge import SERVICE
from lxmf_owner import LXMFBackend
from owner import Owner,serve,exchange


def device_fixture(root):
    import signal
    class Device(Owner):
        def __init__(self,state,station):
            super().__init__(state,station);self.tick=1
        def snapshot(self):
            return dict(version=1,owner_online=True,capabilities=[],revision=self.tick,
                        telemetry=dict(system=dict(source='synthetic-device',observed_at=123)),
                        receive=dict(records=[dict(text='synthetic packet',source='fixture')],count=self.tick))
        def dispatch(self,request):
            if request.get('action')=='fixture_publish':
                self.tick+=1;self.post(dict(action='fixture_update'));return self.snapshot()
            if request.get('action')=='snapshot':return self.snapshot()
            raise ValueError('Read-only fixture')
    signal.signal(signal.SIGTERM,lambda *args:sys.exit(0))
    serve(root/'device-runtime/owner.sock',root/'device-state','fixture-device',Device)


def node(root,role):
    if role=='fixture':return device_fixture(root)
    ids={name:RNS.Identity.from_file(str(root/(name+'.key'))) for name in ('server','client')}
    other='client' if role=='server' else 'server'
    state=root/(role+'-state');state.mkdir(mode=0o700,exist_ok=True)
    if not (state/'identity').exists():
        ids[role].to_file(str(state/'identity'));(state/'identity').chmod(0o600)
    counts=dict(announces=0,implicit_path_requests=0)
    original_send=RNS.Packet.send
    def send(packet,*args,**kwargs):
        if packet.packet_type==RNS.Packet.ANNOUNCE:counts['announces']+=1
        return original_send(packet,*args,**kwargs)
    RNS.Packet.send=send
    original_probe=RNS.Transport.request_path
    def no_probe(*args,**kwargs):
        counts['implicit_path_requests']+=1
        raise AssertionError('Private contact must not request a public path')
    RNS.Transport.request_path=no_probe
    owner=LXMFBackend(state,role,root/role,'fixture-loopback','loopback')
    peer=ids[other];identifier=owner.book.import_contact(json.dumps(card(peer.get_public_key(),other)))
    if owner.book.contacts[identifier]['state']=='unverified':owner.book.verify(identifier,fingerprint(peer.get_public_key()))
    fixture=None
    if role=='server':
        fixture=subprocess.Popen([sys.executable,'-B',__file__,str(root),'fixture'],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        end=time.monotonic()+5
        while not (root/'device-runtime/owner.sock').is_socket():
            if fixture.poll() is not None or time.monotonic()>end:raise RuntimeError('device fixture unavailable')
            time.sleep(.05)
        owner.data_bridge.services.register('device',root/'device-runtime/owner.sock',())
    owner._connect();owner.snapshot()
    print(json.dumps(dict(ready=True,identity=owner.identity.hash.hex(),verified=owner.book.contacts[identifier]['state'],grants=owner.data_bridge.snapshot()['grants'])),flush=True)
    try:
        for line in sys.stdin:
            command=json.loads(line);action=command['action']
            try:
                if action=='snapshot':
                    owner.drain();result=dict(bridge=owner.snapshot()['data_bridge'],counts=counts,verified=owner.book.contacts[identifier]['state'])
                elif action=='device_change':result=exchange(root/'device-runtime/owner.sock',dict(version=1,action='fixture_publish'))
                elif action=='service_share':
                    result=owner.dispatch(dict(version=1,request_id='private-service-share',action='service_share',payload=dict(peer=identifier,expected_public_key=peer.get_public_key().hex(),service='device',operations=['snapshot','subscribe'])))
                elif action in ('service_read','service_subscribe','service_forbidden'):
                    op={'service_read':'snapshot','service_subscribe':'subscribe','service_forbidden':'send'}[action]
                    result=owner.dispatch(dict(version=1,request_id='private-service-call',action='service_call',payload=dict(peer=identifier,service='device',session='0123456789abcdef',timeout=5,request=dict(version=1,action=op))))
                elif action=='service_get':result=owner.data_bridge.services.get(dict(peer=identifier,service='device',session='0123456789abcdef'))
                elif action=='path':result=RNS.Transport.has_path(RNS.Destination.hash_from_name_and_identity(SERVICE,peer))
                elif action=='probe':
                    original_probe(RNS.Destination.hash_from_name_and_identity(SERVICE,peer));result=True
                elif action=='close':break
                else:
                    payload=dict(peer=identifier,expected_public_key=peer.get_public_key().hex(),service=SERVICE,capabilities=['status'])
                    operation={'share':'data_bridge_connect','read':'data_bridge_request','revoke':'revoke_peer'}[action]
                    if action=='revoke':payload=dict(peer=identifier)
                    owner.dispatch(dict(version=1,request_id='private-'+action,action=operation,payload=payload));result=True
                print(json.dumps(dict(ok=True,result=result)),flush=True)
            except Exception as error:print(json.dumps(dict(ok=False,error=str(error))),flush=True)
    finally:
        owner.close()
        if fixture is not None:
            fixture.terminate();fixture.wait(timeout=5)



def main():
    with tempfile.TemporaryDirectory(prefix='private-contact-',dir='/tmp') as temp:
        root=Path(temp);probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
        for role in ('server','client'):
            RNS.Identity().to_file(str(root/(role+'.key')));(root/role).mkdir()
            interface=('type = TCPServerInterface\nlisten_ip = 127.0.0.1\nlisten_port = '+str(port) if role=='server' else 'type = TCPClientInterface\ntarget_host = 127.0.0.1\ntarget_port = '+str(port))
            (root/role/'config').write_text('[reticulum]\nenable_transport = No\nshare_instance = No\ndiscover_interfaces = No\n[logging]\nloglevel = 0\n[interfaces]\n [[Private loopback]]\n enabled = Yes\n '+interface.replace('\n','\n ')+'\n')
        children={};identities={};proof=[]
        def receive(child,seconds=12):
            if not select.select([child.stdout],[],[],seconds)[0]:raise TimeoutError('owner reply')
            line=child.stdout.readline()
            if not line:raise RuntimeError(child.stderr.read())
            return json.loads(line)
        def call(role,action):
            child=children[role];child.stdin.write(json.dumps(dict(action=action))+'\n');child.stdin.flush();return receive(child)
        def stop():
            for role,child in children.items():
                if child.poll() is None:
                    child.stdin.write('{"action":"close"}\n');child.stdin.flush()
            for child in children.values():
                try:child.wait(timeout=8)
                except subprocess.TimeoutExpired:child.kill();child.wait()
                if child.returncode:raise RuntimeError(child.stderr.read())
            children.clear()
        try:
            for cycle in range(2):
                for role in ('server','client'):
                    child=subprocess.Popen([sys.executable,'-B',__file__,str(root),role],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1);children[role]=child
                    ready=receive(child)
                    assert ready['ready'] and ready['verified']=='verified' and ready['grants']==[],ready
                    if cycle:assert ready['identity']==identities[role]
                    identities[role]=ready['identity']
                assert call('server','share')['ok']
                assert not call('client','path')['result']
                assert call('client','probe')['ok'];time.sleep(.4)
                assert not call('client','path')['result'],'private service answered path probe'
                assert call('client','read')['ok']
                end=time.monotonic()+12;response=None
                while time.monotonic()<end:
                    state=call('client','snapshot')['result'];rows=state['bridge']['requests']
                    if rows and rows[0].get('response'):
                        response=rows[0]['response'];break
                    time.sleep(.05)
                assert response,state
                assert rows[0]['rendezvous']=='direct_contact'
                assert not state['bridge']['grants'],'read implicitly shared access'
                assert not state['bridge']['public_discovery']
                assert call('server','service_share')['ok']
                read=call('client','service_read');assert read['ok'] and read['result']['receive']['count']==1,read
                assert read['result']['telemetry']['system']['source']=='synthetic-device'
                denied_op=call('client','service_forbidden');assert not denied_op['ok'] and 'not granted' in denied_op['error'],denied_op
                subscribed=call('client','service_subscribe');assert subscribed['ok'] and subscribed['result']['receive']['count']==1,subscribed
                assert call('server','device_change')['ok']
                end=time.monotonic()+10;update=None
                while time.monotonic()<end:
                    update=call('client','service_get')
                    if update['ok'] and update['result']['receive']['count']==2:break
                    time.sleep(.05)
                assert update['ok'] and update['result']['receive']['count']==2,update
                if cycle:
                    assert call('server','revoke')['ok']
                    time.sleep(.3)
                    assert not call('client','service_get')['ok'],'revoked subscription remained usable'
                    assert call('client','read')['ok']
                    time.sleep(.6)
                    denied=call('client','snapshot')['result']['bridge']['requests'][0]
                    assert denied.get('response') is None
                for role in children:
                    check=call(role,'snapshot')['result'];assert check['counts']==dict(announces=0,implicit_path_requests=0),check
                proof.append(dict(cycle=cycle+1,private_status=True,cold_route=True,announces=0,path_probe_reply=False,service_call=True,service_subscription_update=True,ungranted_operation_denied=True))
                stop()
            # Verification/revocation state persists independently of owner activation.
            from contacts import ContactBook
            book=ContactBook(root/'server-state')
            assert book.contacts[identities['client']]['state']=='revoked'
            print(json.dumps(dict(passed=True,rns=RNS.__version__,cycles=proof,identity_preserved=True,
                  verified_contacts_preserved=True,grants_not_persisted=True,revocation_preserved=True,
                  public_announces=0,implicit_path_requests=0,rf=False)))
        finally:stop()

if __name__=='__main__':
    if len(sys.argv)>1:node(Path(sys.argv[1]),sys.argv[2])
    else:main()
