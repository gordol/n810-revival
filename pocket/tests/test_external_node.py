"""Actual serial framing, capability gating and persisted offload preferences."""
import os,pty,sys,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
DOMAIN=Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum'
sys.path.insert(0,str(DOMAIN))
import external_node as node
from native_radio import Frames
from session_owner import SessionOwner
from wire import encode

class ExternalNodeTests(unittest.TestCase):
    def test_provisioning_is_not_endpoint_offload_and_sequence_is_checked(self):
        master,slave=pty.openpty();address=os.ttyname(slave);os.close(slave)
        def remote():
            decoder=Frames(192,219)
            while True:
                try:data=os.read(master,4096)
                except OSError:time.sleep(.01);continue
                for frame in decoder.feed(data):
                    request=node.unpack(frame[1:]);operation,seq,payload=request
                    result={1:'microReticulum',2:2} if operation==2 else {1:{1:{1:True,3:False},107:{1:b'\xc0\xdb'+b'x'*14},104:{6:912345000}}}
                    def reply(sequence):
                        raw=node.pack([operation,sequence,result]);wire=b'\xc0\x87'+raw.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc')+b'\xc0'
                        for b in wire:os.write(master,bytes([b]))
                    reply(seq+90);reply(seq)
                    if operation==4:return
        worker=threading.Thread(target=remote,daemon=True);worker.start()
        try:
            state=node.probe(address);self.assertTrue(state['standalone']);self.assertFalse(state['offload_ready'])
            self.assertEqual(state['identity'],(b'\xc0\xdb'+b'x'*14).hex());encode(dict(version=1,external_node=state))
            self.assertEqual(node.selection('auto',state),'local')
            self.assertEqual(node.selection('disabled',state),'local')
            with self.assertRaisesRegex(ValueError,'delegation'):node.selection('external-only',state)
        finally:os.close(master);worker.join(1)
    def test_radio_form_modes_and_board_editor_use_framework_actions(self):
        from types import SimpleNamespace
        sys.path.insert(0,str(DOMAIN.parents[3]))
        from manager import Manager
        calls=[]
        class Service:
            def request(self,action,payload):calls.append((action,payload));return 'test'
        form=Manager(app_context=SimpleNamespace(services={'reticulum':Service()}))
        form.state=dict(version=1,radio_state='idle',capabilities=['configure_node','refresh_node'],external_node=dict(mode='auto',state='online',selected='none',endpoint='',identity='ab'*16))
        form.lines()
        for key in ('a','o','x'):form.key(key)
        self.assertEqual([payload['mode'] for _,payload in calls],['auto','disabled','external-only'])
        form.key('b');self.assertTrue(form.modal())
        form.naming['value']='rfcomm://02:00:00:00:00:03/1';form.key('\r')
        self.assertEqual(calls[-1],('configure_node',dict(endpoint='rfcomm://02:00:00:00:00:03/1')))
        self.assertFalse(form.modal())

    def test_mode_persistence_and_invalid_connections(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'preferences';value=dict(mode='external-only',endpoint='rfcomm://02:00:00:00:00:03/1')
            node.save(path,value);self.assertEqual(node.load(path),value)
            path.chmod(0o644)
            with self.assertRaises(ValueError):node.load(path)
        for address in ('https://example.org','rfcomm://02:00:00:00:00:03/0','/tmp/not-a-device'):
            with self.assertRaises(ValueError):node.endpoint(address)
    def test_existing_usb_radio_port_can_be_assigned_to_executor_without_local_driver(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner=SessionOwner(tmp,'test','radio','usb','/dev/ttyFAKE',2,2)
            gate=threading.Event()
            def probe(address,**kwargs):gate.wait(2);return dict(state='online',offload_ready=False,reason='Executor unavailable')
            profile=dict(id='test',label='Test',frequency=912345000,bandwidth=500000,txpower=2,spreadingfactor=7,codingrate=5)
            owner.store.commit({'test':profile},'test')
            try:
                with patch.object(node,'probe',side_effect=probe),patch.object(node,'Connection'):
                    owner.dispatch(dict(version=1,action='configure_node',payload=dict(mode='auto',endpoint='/dev/ttyFAKE')))
                    with patch('session_owner.subprocess.Popen') as spawn:
                        owner._start(dict(version=1,action='connect',request_id='test'),owner.generation)
                        spawn.assert_not_called();owner.drain()
                        self.assertEqual(owner.phase,'error');self.assertIn('separate local radio',owner.error)
            finally:gate.set();owner.close()

    def test_owner_refresh_is_async_and_external_only_does_not_start_local_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            owner=SessionOwner(tmp,'test','radio','usb','/dev/null',2,2)
            gate=threading.Event()
            def probe(endpoint,**kwargs):gate.wait(2);return dict(state='online',offload_ready=False,reason='Endpoint delegation is unavailable',observed_at=time.time())
            try:
                with patch.object(node,'probe',side_effect=probe),patch.object(node,'Connection'):
                    began=time.monotonic();owner.dispatch(dict(version=1,action='configure_node',payload=dict(mode='external-only',endpoint='/dev/ttyFAKE')))
                    self.assertLess(time.monotonic()-began,.2);gate.set()
                    deadline=time.monotonic()+3
                    while owner.node_state['state']!='online':
                        owner.drain();self.assertLess(time.monotonic(),deadline);time.sleep(.01)
                with patch('session_owner.subprocess.Popen') as spawn:
                    owner._start(dict(version=1,action='connect',request_id='test'),owner.generation)
                    spawn.assert_not_called();owner.drain()
                    self.assertEqual(owner.phase,'error');self.assertIn('delegation',owner.error)
                encode(owner.snapshot())
            finally:gate.set();owner.close()

if __name__=='__main__':unittest.main()
