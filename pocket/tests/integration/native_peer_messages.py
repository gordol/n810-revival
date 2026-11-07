# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Two real microReticulum/microLXMF owners; TCP only, no RF or user state."""
import json,os,select,socket,subprocess,sys,tempfile,time,shlex
from pathlib import Path
DOMAIN=Path(__file__).resolve().parents[2]/'shell/vendor/apps/domains/reticulum'
sys.path.insert(0,str(DOMAIN))

def node(root,role):
    from native_owner import NativeBackend
    owner=NativeBackend(root/(role+'-state'),role,root/role,'direct-peer','tcp')
    try:
        owner.dispatch(dict(version=1,request_id='connect',action='connect',payload=dict(station=role,radio='direct-peer')))
        print(json.dumps(dict(ok=True)),flush=True)
        for line in sys.stdin:
            command=json.loads(line)
            if command['action']=='close':break
            try:
                owner.drain()
                result=owner.snapshot() if command['action']=='snapshot' else owner.dispatch(dict(version=1,request_id=command.get('id',os.urandom(6).hex()),action=command['action'],payload=command.get('payload',{})))
                print(json.dumps(dict(ok=True,result=result)),flush=True)
            except Exception as error:print(json.dumps(dict(ok=False,error=str(error))),flush=True)
    finally:owner.close()

def main():
    from contacts import fingerprint,public_key
    with tempfile.TemporaryDirectory(prefix='pocket-native-peers-') as tmp:
        root=Path(tmp);remote=os.environ.get('POCKET_PEER_REMOTE');probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
        children={}
        for role in ('listener','client'):
            (root/role).mkdir();(root/(role+'-state')).mkdir(mode=0o700)
            host='192.168.10.1' if remote else '127.0.0.1'
            settings=f'type = TCPServerInterface\nlisten_ip = {host}\nlisten_port = {port}' if role=='listener' else f'type = TCPClientInterface\ntarget_host = {host}\ntarget_port = {port}'
            (root/role/'config').write_text('[interfaces]\n [[Direct peer]]\n'+settings+'\n')
            command=[sys.executable,'-u',__file__,str(root),role]
            if remote and role=='listener':
                remote_root='/tmp/pocket-direct-peer-test/run-'+str(port)
                setup='import pathlib,os; p=pathlib.Path('+repr(remote_root)+'); p.mkdir(mode=0o700,exist_ok=True); (p/"listener").mkdir(exist_ok=True); (p/"listener"/"config").write_text('+repr('[interfaces]\n [[Direct peer]]\n'+settings+'\n')+'); (p/"listener-state").mkdir(mode=0o700,exist_ok=True)'
                subprocess.run(shlex.split(remote)+['runuser','-u','nokia','--','python3','-c',shlex.quote(setup)],check=True)
                command=shlex.split(remote)+['runuser','-u','nokia','--','env','POCKET_RNS_LIBRARY=/usr/local/share/n810-pocket/vendor/native/libpocket_rns.so','python3','-u','/tmp/pocket-direct-peer-test/tests/integration/native_peer_messages.py',remote_root,role]
            children[role]=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        def reply(child,timeout=120):
            if not select.select([child.stdout],[],[],timeout)[0]:raise TimeoutError('Native peer reply timed out')
            line=child.stdout.readline()
            if not line:raise RuntimeError(child.stderr.read())
            return json.loads(line)
        def call(role,action,payload=None,identifier=None):
            p=children[role];p.stdin.write(json.dumps(dict(action=action,payload=payload or {},id=identifier or os.urandom(6).hex()))+'\n');p.stdin.flush()
            result=reply(p)
            if not result['ok']:raise RuntimeError(result['error'])
            return result['result']
        def wait(predicate,seconds=90):
            until=time.monotonic()+seconds
            while not predicate():
                if time.monotonic()>until:raise TimeoutError('Peer delivery did not complete')
                time.sleep(.1)
        try:
            for child in children.values():assert reply(child)['ok']
            wait(lambda:all(call(role,'snapshot')['radios'][0]['interface_online'] for role in children))
            cards={role:call(role,'snapshot')['public_card'] for role in children}
            assert cards['listener']['identity']!=cards['client']['identity']
            for role in children:call(role,'message_discovery',dict(enabled=True))
            wait(lambda:all(any(h.get('identity')==cards[other]['identity'] and h.get('service')=='lxmf.delivery' for h in call(role,'snapshot')['heard']) for role,other in (('listener','client'),('client','listener'))))
            for role,other in (('listener','client'),('client','listener')):
                heard=next(h for h in call(role,'snapshot')['heard'] if h.get('identity')==cards[other]['identity'] and h.get('service')=='lxmf.delivery')
                call(role,'save_heard',dict(destination=heard['destination'],label=other))
                call(role,'verify_peer',dict(peer=cards[other]['identity'],fingerprint=fingerprint(public_key(cards[other]['public_key']))))
            time.sleep(1)
            for role,other in (('listener','client'),('client','listener')):
                message='Native direct peer '+role+' → '+other
                call(role,'send',dict(peer=cards[other]['identity'],text=message),'message-'+role)
                wait(lambda:any(m.get('text')==message and m.get('direction')=='rx' for m in call(other,'snapshot')['messages']))
                wait(lambda:any(m.get('id')=='message-'+role and m.get('state')=='delivered' for m in call(role,'snapshot')['messages']))
            print(json.dumps(dict(passed=True,native=True,peers=2,bidirectional_lxmf=True,discovery_save_verify=True,sender_delivery_evidence=True,remote_nokia=bool(remote),rf=False)))
        finally:
            for p in children.values():
                if p.poll() is None:
                    try:p.stdin.write('{"action":"close"}\n');p.stdin.flush()
                    except BrokenPipeError:pass
            for p in children.values():
                try:p.wait(15)
                except subprocess.TimeoutExpired:p.kill();p.wait()
                if p.returncode:print(p.stderr.read(),file=sys.stderr)
if __name__=='__main__':
    if len(sys.argv)>1:node(Path(sys.argv[1]),sys.argv[2])
    else:main()
