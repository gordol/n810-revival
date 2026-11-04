"""Sandbox-only direct RNS Link probe with no announces or path requests."""
import json,os,select,socket,subprocess,sys,tempfile,time
from pathlib import Path
import RNS


def node(root,role):
    RNS.Reticulum(str(root/role))
    identity=RNS.Identity.from_file(str(root/(role+'.key')))
    if role=='server':
        d=RNS.Destination(identity,RNS.Destination.IN,RNS.Destination.SINGLE,'pocket','data','v1')
        d.announce=lambda *a,**k:None
        d.register_request_handler('/test',response_generator=lambda *a:b'private',allow=RNS.Destination.ALLOW_ALL)
        print('ready',flush=True);time.sleep(15)
    else:
        peer=RNS.Identity.from_file(str(root/'server.key'))
        public=RNS.Identity(create_keys=False);public.load_public_key(peer.get_public_key())
        d=RNS.Destination(public,RNS.Destination.OUT,RNS.Destination.SINGLE,'pocket','data','v1')
        assert not RNS.Transport.has_path(d.hash)
        link=RNS.Link(d)
        end=time.monotonic()+7
        while link.status!=RNS.Link.ACTIVE and time.monotonic()<end:time.sleep(.05)
        print(json.dumps(dict(active=link.status==RNS.Link.ACTIVE,path=RNS.Transport.has_path(d.hash))),flush=True)
        link.teardown()
        assert link.status==RNS.Link.CLOSED

if __name__=='__main__':
    if len(sys.argv)>1:node(Path(sys.argv[1]),sys.argv[2])
    else:
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
            for role in ('server','client'):
                RNS.Identity().to_file(str(root/(role+'.key')));(root/role).mkdir()
                interface=('type = TCPServerInterface\nlisten_ip = 127.0.0.1\nlisten_port = '+str(port) if role=='server' else 'type = TCPClientInterface\ntarget_host = 127.0.0.1\ntarget_port = '+str(port))
                (root/role/'config').write_text('[reticulum]\nenable_transport = No\nshare_instance = No\n[logging]\nloglevel = 0\n[interfaces]\n [[Private loopback]]\n enabled = Yes\n '+interface.replace('\n','\n ')+'\n')
            server=subprocess.Popen([sys.executable,'-B',__file__,str(root),'server'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                assert select.select([server.stdout],[],[],6)[0]
                assert server.stdout.readline().strip()=='ready',server.stderr.read()
                client=subprocess.run([sys.executable,'-B',__file__,str(root),'client'],capture_output=True,text=True,timeout=12)
                print(client.stdout);print(client.stderr);assert client.returncode==0
            finally:server.terminate();server.wait(timeout=5)
