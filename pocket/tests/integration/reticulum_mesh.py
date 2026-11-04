"""Real RNS acceptance on private loopback only; no physical interfaces."""
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

DOMAIN=Path(__file__).resolve().parents[2]/'shell/vendor/apps/domains/reticulum'
sys.path.insert(0,str(DOMAIN))
import RNS
from data_bridge import DataBridge,SERVICE


def node(root,role):
    from lxmf_owner import LXMFBackend
    from contacts import card, fingerprint
    identities={name:RNS.Identity.from_file(str(root/(name+'.key'))) for name in ('hub','a','b')}
    state=root/(role+'-state');state.mkdir(mode=0o700)
    identity=identities[role];identity.to_file(str(state/'identity'));os.chmod(state/'identity',0o600)
    owner=LXMFBackend(state,role,root/role,'loopback','loopback')
    for name,peer in identities.items():
        if name!=role:
            identifier=owner.book.import_contact(json.dumps(card(peer.get_public_key(),name)))
            owner.book.verify(identifier,fingerprint(peer.get_public_key()))
    owner._connect()
    owner.snapshot()
    bridge=owner.data_bridge
    print(json.dumps(dict(ready=True)),flush=True)
    try:
        for line in sys.stdin:
            command=json.loads(line);action=command['action']
            try:
                if action=='snapshot':
                    owner.drain();result=owner.snapshot()['data_bridge']
                elif action=='path':result=RNS.Transport.has_path(RNS.Destination.hash_from_name_and_identity(SERVICE,identities[command['peer']]))
                elif action=='find':
                    RNS.Transport.request_path(RNS.Destination.hash_from_name_and_identity(SERVICE,identities[command['peer']]))
                    result=True
                elif action=='interfaces':result=[dict(name=str(i),online=getattr(i,'online',False)) for i in RNS.Transport.interfaces]
                elif action=='close':break
                else:
                    peer=identities[command['peer']]
                    payload=dict(peer=peer.hash.hex(),expected_public_key=peer.get_public_key().hex(),service=SERVICE,capabilities=['status'])
                    if action=='revoke':
                        owner.dispatch(dict(version=1,request_id='fixture-revoke',action='revoke_peer',payload=dict(peer=peer.hash.hex())))
                    else:
                        if action=='disconnect':payload=dict(peer=peer.hash.hex())
                        owner.dispatch(dict(version=1,request_id='fixture-'+action,action='data_bridge_'+{'share':'connect','read':'request','disconnect':'disconnect'}[action],payload=payload))
                    result=bridge.snapshot()
                print(json.dumps(dict(ok=True,result=result)),flush=True)
            except Exception as error:print(json.dumps(dict(ok=False,error=str(error))),flush=True)
    finally:owner.close()


def main():
    with tempfile.TemporaryDirectory(prefix='pocket-mesh-',dir='/tmp') as tmp:
        root=Path(tmp)
        probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
        for role in ('hub','a','b'):
            RNS.Identity().to_file(str(root/(role+'.key')))
            (root/role).mkdir()
            interface=('type = TCPServerInterface\nlisten_ip = 127.0.0.1\nlisten_port = '+str(port) if role=='hub' else
                       'type = TCPClientInterface\ntarget_host = 127.0.0.1\ntarget_port = '+str(port))
            (root/role/'config').write_text('[reticulum]\nenable_transport = '+('Yes' if role=='hub' else 'No')+'\nshare_instance = No\ndiscover_interfaces = No\nenable_remote_management = No\n[logging]\nloglevel = 0\n[interfaces]\n [[Loopback]]\n enabled = Yes\n '+interface.replace('\n','\n ')+'\n')
        children={}
        def reply(child,timeout=15):
            if not select.select([child.stdout],[],[],timeout)[0]:raise TimeoutError('No node reply')
            line=child.stdout.readline()
            if not line:raise RuntimeError('Node exited: '+str(child.poll()))
            return json.loads(line)
        def call(role,action,peer=None):
            child=children[role];child.stdin.write(json.dumps(dict(action=action,peer=peer))+'\n');child.stdin.flush()
            return reply(child)
        def wait(predicate,label,seconds=20):
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                if predicate():return
                time.sleep(.05)
            raise AssertionError(label+' '+str({r:call(r,'interfaces') for r in children})+' '+str({r:{p:call(r,'path',p) for p in children if r!=p} for r in children}))
        def received(role,peer):
            identity=RNS.Identity.from_file(str(root/(peer+'.key'))).hash.hex()
            return next((r.get('response') for r in call(role,'snapshot')['result']['requests'] if r['peer']==identity),None)
        try:
            for role in ('hub','a','b'):
                children[role]=subprocess.Popen([sys.executable,__file__,str(root),role],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
                assert reply(children[role])['ready']
            assert all(call(role,'snapshot')['result']==dict(state='off',grants=[],requests=[]) for role in children)
            # Two independent grants at the hub; a also shares with b through the relay.
            assert call('hub','share','a')['ok'];assert call('hub','share','b')['ok']
            assert call('a','share','b')['ok']
            for client,peer in (('a','hub'),('b','hub'),('b','a')): call(client,'find',peer)
            wait(lambda:call('b','path','a')['result'] and call('a','path','hub')['result'] and call('b','path','hub')['result'],'signed paths not discovered')
            for client,peer in (('a','hub'),('b','hub'),('b','a')):assert call(client,'read',peer)['ok']
            wait(lambda:all(received(client,peer) for client,peer in (('a','hub'),('b','hub'),('b','a'))),'authenticated status absent')
            assert not call('b','snapshot')['result']['grants'],'requesting unexpectedly enabled sharing'
            assert call('hub','revoke','a')['ok']
            assert call('a','read','hub')['ok']
            assert call('b','read','hub')['ok']
            wait(lambda:received('b','hub'),'revocation disrupted other grant')
            # Give the denied request time to fail; it must never return data.
            wait(lambda:not call('a','snapshot')['result']['requests'][0]['pending'],'denied request did not expire',25)
            assert not received('a','hub'),'revoked peer received data'
            print(json.dumps(dict(passed=True,rns=RNS.__version__,instances=3,transport='TCP loopback',relayed_status=True,
                                 independent_owners=True,revocation=True,request_does_not_share=True,rf=False)))
        finally:
            for child in children.values():
                if child.poll() is None:
                    child.stdin.write('{"action":"close"}\n');child.stdin.flush()
            for child in children.values():
                try:child.wait(timeout=8)
                except subprocess.TimeoutExpired:child.kill();child.wait()
                if child.returncode:print(child.stderr.read(),file=sys.stderr)

if __name__=='__main__':
    if len(sys.argv)>1:node(Path(sys.argv[1]),sys.argv[2])
    else:main()
