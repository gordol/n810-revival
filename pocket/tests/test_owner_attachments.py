"""Optional attachment hooks over real private Unix streams; no radio or contacts."""
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'shell/vendor/apps/domains/reticulum'))
from wire import encode,read,LIMIT


def fixture():
    from owner import serve
    endpoint,state,ready,events,kind=sys.argv[2:]
    events=int(events)
    class Plain:
        def __init__(self,*args):self.revision=0;self.wake=None
        def snapshot(self):return dict(version=1,owner_online=True,revision=self.revision,capabilities=[])
        def drain(self):pass
        def dispatch(self,request):
            if request['action']=='attach':return dict(version=1,ordinary_dispatch=True)
            if request['action']=='bump':self.revision+=1
            return self.snapshot()
    class Attached(Plain):
        def __init__(self,*args):super().__init__();self.active={};self.ids={}
        def event(self,client,**value):
            if client not in self.ids:self.ids[client]=len(self.ids)+1
            os.write(events,(json.dumps(dict(client=self.ids[client],**value))+'\n').encode())
        def attach_client(self,client,request):
            mode=request.get('payload',{}).get('mode','ok')
            self.active[client]=mode;self.event(client,action='attach',mode=mode)
            if mode=='raise':raise RuntimeError('partial attachment failed')
            if mode=='unencodable':return dict(version=1,value=object())
            if mode=='oversize':return dict(version=1,value='x'*LIMIT)
            if mode=='error':return dict(version=1,error='declined')
            if mode=='invalid':return dict(version=2)
            if mode=='large':
                client.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,1024)
                return dict(version=1,body='x'*30000)
            self.revision+=1
            return dict(version=1,attached=True)
        def detach_client(self,client):
            mode=self.active.pop(client,None)
            self.event(client,action='detach',was_attached=mode is not None,mode=mode)
            if mode=='detach_error':raise RuntimeError('fixture detach error after release')
    signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
    serve(endpoint,state,'fixture',Plain if kind=='plain' else Attached,ready_fd=int(ready))


class AttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.sockets=[];self.process=None;self.events=None;self.pending=b''
        self.path=Path(self.temp.name)/'owner.sock'
    def tearDown(self):
        for stream in self.sockets:stream.close()
        if self.process is not None:
            if self.process.poll() is None:self.process.terminate()
            self.process.wait(3)
        if self.events is not None:os.close(self.events)
        self.temp.cleanup()
    def start(self,kind='attached'):
        ready,write=os.pipe();self.events,event_write=os.pipe()
        self.process=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--fixture',str(self.path),
            str(Path(self.temp.name)/'state'),str(write),str(event_write),kind],pass_fds=(write,event_write),stderr=subprocess.DEVNULL)
        os.close(write);os.close(event_write)
        try:self.assertTrue(select.select([ready],[],[],3)[0]);self.assertEqual(os.read(ready,1),b'R')
        finally:os.close(ready)
    def connect(self,action='attach',payload=None):
        client=socket.socket(socket.AF_UNIX);client.settimeout(2);self.sockets.append(client);client.connect(str(self.path))
        client.sendall(encode(dict(version=1,action=action,payload=payload or {})))
        stream=client.makefile('rb');self.sockets.append(stream)
        return client,stream
    def event(self):
        while b'\n' not in self.pending:
            self.assertTrue(select.select([self.events],[],[],2)[0],'missing attachment event')
            data=os.read(self.events,4096)
            if not data:return None
            self.pending+=data
        line,self.pending=self.pending.split(b'\n',1)
        return json.loads(line)
    def assert_no_extra_event(self):
        self.assertEqual(self.pending,b'')
        self.assertEqual(select.select([self.events],[],[],.05)[0],[])
    def test_attach_reply_retains_socket_and_eof_detaches_exactly_once(self):
        self.start();client,stream=self.connect()
        self.assertTrue(read(stream)['attached']);attached=self.event();self.assertEqual(attached['action'],'attach')
        self.assertEqual(select.select([client],[],[],.05)[0],[])
        stream.close();client.close()
        detached=self.event();self.assertEqual(detached['client'],attached['client']);self.assertTrue(detached['was_attached'])
        self.assert_no_extra_event()
    def test_snapshot_closes_and_subscription_never_attaches(self):
        self.start();client,stream=self.connect('snapshot')
        self.assertTrue(read(stream)['owner_online']);self.assertEqual(client.recv(1),b'')
        self.assertEqual(self.event()['action'],'detach')
        sub,substream=self.connect('subscribe');self.assertTrue(read(substream)['owner_online'])
        self.assert_no_extra_event();substream.close();sub.close()
        detached=self.event();self.assertEqual(detached['action'],'detach');self.assertFalse(detached['was_attached'])
        self.assert_no_extra_event()
    def test_attachment_receives_no_observational_broadcasts(self):
        self.start();client,stream=self.connect();read(stream);self.event()
        _,observer=self.connect('subscribe');read(observer)
        command,reply=self.connect('bump');self.assertEqual(read(reply)['revision'],2)
        self.assertEqual(command.recv(1),b'');self.assertFalse(self.event()['was_attached'])
        self.assertEqual(read(observer)['revision'],2)
        self.assertEqual(select.select([client],[],[],.05)[0],[])
    def test_partial_attach_failure_and_bad_reply_always_close_and_release(self):
        self.start()
        for mode in ('raise','unencodable','oversize','error','invalid'):
            with self.subTest(mode=mode):
                client,stream=self.connect(payload=dict(mode=mode))
                with self.assertRaisesRegex(ValueError,'Attachment failed'):read(stream)
                self.assertEqual(client.recv(1),b'')
                attached=self.event();detached=self.event()
                self.assertEqual(attached['action'],'attach');self.assertEqual(detached['action'],'detach')
                self.assertEqual(attached['client'],detached['client']);self.assertTrue(detached['was_attached'])
                self.assert_no_extra_event()
    def test_malformed_input_and_data_after_attach_cleanup(self):
        self.start();client=socket.socket(socket.AF_UNIX);client.settimeout(2);self.sockets.append(client);client.connect(str(self.path))
        client.sendall(b'garbage');self.assertEqual(client.recv(1),b'')
        self.assertFalse(self.event()['was_attached'])
        client,stream=self.connect();read(stream);attached=self.event()
        client.sendall(b'extra');self.assertEqual(client.recv(1),b'')
        detached=self.event();self.assertEqual(attached['client'],detached['client']);self.assertTrue(detached['was_attached'])
        self.assert_no_extra_event()
    def test_non_dict_and_invalid_request_versions_never_attach_or_stop_owner(self):
        self.start()
        for request in ([],1,dict(version=2,action='attach'),dict(version=True,action='attach'),dict(action='attach')):
            with self.subTest(request=request):
                client=socket.socket(socket.AF_UNIX);client.settimeout(2);self.sockets.append(client);client.connect(str(self.path))
                client.sendall(encode(request))
                stream=client.makefile('rb');self.sockets.append(stream)
                with self.assertRaisesRegex(ValueError,'Invalid service version'):read(stream)
                self.assertEqual(client.recv(1),b'')
                detached=self.event();self.assertEqual(detached['action'],'detach');self.assertFalse(detached['was_attached'])
                self.assertIsNone(self.process.poll());self.assert_no_extra_event()
        client,stream=self.connect('snapshot');self.assertTrue(read(stream)['owner_online']);self.assertEqual(client.recv(1),b'')
        self.assertFalse(self.event()['was_attached'])
    def test_final_cleanup_detaches_each_attached_and_observational_client_once(self):
        self.start();identities=[]
        for _ in range(2):
            _,stream=self.connect();read(stream);identities.append(self.event()['client'])
        _,stream=self.connect('subscribe');read(stream)
        self.process.terminate();self.process.wait(3)
        detached=[self.event() for _ in range(3)]
        self.assertEqual(len({event['client'] for event in detached}),3)
        self.assertEqual(sorted(event['client'] for event in detached if event['was_attached']),identities)
        self.assertIsNone(self.event())
    def test_detach_hook_exception_does_not_break_other_clients(self):
        self.start();client,stream=self.connect(payload=dict(mode='detach_error'));read(stream);attached=self.event()
        stream.close();client.close();self.assertEqual(self.event()['client'],attached['client'])
        client,stream=self.connect('snapshot');self.assertTrue(read(stream)['owner_online']);self.assertEqual(client.recv(1),b'')
        self.assertFalse(self.event()['was_attached']);self.assertIsNone(self.process.poll())
    def test_eof_during_large_reply_releases_attachment(self):
        self.start();client,stream=self.connect(payload=dict(mode='large'))
        attached=self.event();self.assertEqual(len(client.recv(16)),16)
        stream.close();client.close()
        detached=self.event();self.assertEqual(attached['client'],detached['client']);self.assertTrue(detached['was_attached'])
        self.assert_no_extra_event()
        client,stream=self.connect('snapshot');self.assertTrue(read(stream)['owner_online'])
    def test_eight_client_bound_and_slot_reuse_are_preserved(self):
        self.start();connections=[]
        for _ in range(8):
            client,stream=self.connect();read(stream);self.event();connections.append((client,stream))
        rejected=socket.socket(socket.AF_UNIX);rejected.settimeout(2);self.sockets.append(rejected)
        rejected.connect(str(self.path));self.assertEqual(rejected.recv(1),b'');self.assert_no_extra_event()
        client,stream=connections.pop();stream.close();client.close();self.assertTrue(self.event()['was_attached'])
        client,stream=self.connect();self.assertTrue(read(stream)['attached']);self.assertEqual(self.event()['action'],'attach')
    def test_owner_without_hooks_keeps_ordinary_dispatch_and_close(self):
        self.start('plain');client,stream=self.connect()
        self.assertTrue(read(stream)['ordinary_dispatch']);self.assertEqual(client.recv(1),b'')


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--fixture':fixture()
    else:unittest.main()
