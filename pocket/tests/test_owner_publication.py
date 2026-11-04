"""Publication reuse and availability are checked over real local owner sockets."""
import importlib.util
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'shell/vendor/apps/domains/reticulum'))
from owner import exchange
from wire import encode,read,decode
class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);self.path=root/'owner.sock'
        ready,write=os.pipe()
        self.process=subprocess.Popen([sys.executable,'-B',str(ROOT/'tests/fixtures/owner_publication_fixture.py'),
            '--socket',str(self.path),'--state',str(root/'state'),'--ready-fd',str(write)],pass_fds=(write,))
        os.close(write)
        self.addCleanup(self.stop)
        try:self.assertEqual(os.read(ready,1),b'R')
        finally:os.close(ready)
    def stop(self):
        if self.process.poll() is None:self.process.terminate()
        self.process.wait(3)
    def stream(self,scope=None):
        client=socket.socket(socket.AF_UNIX);client.settimeout(2);client.connect(str(self.path));self.addCleanup(client.close)
        request=dict(version=1,action='subscribe')
        if scope:request['scope']=scope
        client.sendall(encode(request));stream=client.makefile('rb');self.addCleanup(stream.close)
        return client,stream,read(stream)
    def request(self,action,**extra):return exchange(self.path,dict(version=1,action=action,**extra))
    def test_one_bounded_frame_for_all_subscribers_and_no_availability_fanout(self):
        streams=[self.stream() for _ in range(3)]
        availability=self.stream('availability')
        self.assertEqual(availability[2],dict(version=1,owner_online=True,capabilities=[],scope='availability'))
        self.assertEqual(self.request('counts')['builds'],3)
        self.request('bump')
        updates=[read(stream) for _,stream,_ in streams]
        self.assertEqual(updates,[updates[0]]*3)
        self.assertEqual(updates[0]['build'],4)
        self.assertEqual(self.request('counts')['builds'],4)
        self.assertEqual(select.select([availability[0]],[],[],.05)[0],[])
        self.stop()
        with self.assertRaises(ConnectionError):read(availability[1])
    def test_async_completion_only_publishes_if_revision_changed(self):
        client,stream,_=self.stream()
        self.request('service_call',payload={})
        self.request('wake')
        self.assertEqual(select.select([client],[],[],.05)[0],[])
        self.assertEqual(self.request('counts')['builds'],1)
        self.request('service_call',payload=dict(change=True))
        self.assertEqual(read(stream)['revision'],1)
        self.assertEqual(self.request('counts')['builds'],2)
    def test_invalid_scope_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unknown subscription scope'):self.stream('unknown')

class MeshFrameTests(unittest.TestCase):
    def test_meshcore_bounded_frame_is_encoded_once_and_keeps_trimming(self):
        spec=importlib.util.spec_from_file_location('mesh_publication',ROOT/'shell/vendor/apps/domains/meshcore/owner.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        owner=module.MeshOwner.__new__(module.MeshOwner)
        owner.peers=[];owner.peer_offset=0;owner.pins=[];owner.phase='online';owner.online=True
        owner.station='fixture';owner.bridge={};owner.port='/dev/unused';owner.baudrate=115200
        owner.trusted_peripheral=True;owner.revision=1;owner.local_identity='identity';owner.channels=[];owner.last_job=None;owner.error=''
        owner.messages=[dict(text='message')]
        with patch.object(module,'encode',wraps=module.encode) as framed:
            self.assertEqual(decode(owner.snapshot_frame())['messages'],owner.messages)
            self.assertEqual(framed.call_count,1)
        owner.messages=[dict(text='x'*2000) for _ in range(32)]
        raw=owner.snapshot_frame();state=decode(raw)
        self.assertLess(len(state['messages']),32)
        self.assertEqual(len(owner.messages),32)
        self.assertLessEqual(len(raw),32768)
if __name__=='__main__':unittest.main()
