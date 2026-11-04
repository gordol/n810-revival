"""Independent hub lifetime, lazy LoRa and per-service failure containment."""
import os,select,socket,sys,time,unittest
from collections import deque
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/meshcore'))
from hub_session import HubSession
from hub_owner import HubOwner,canonical_port
from hub_transport import Frame,PhysicalLinkError
from rnode_adapter import kiss,KissDecoder

class FakeLink:
    def __init__(self,port,*,ble_ready=True,reject_radio=False):
        self.serial,self.writer=socket.socketpair();self.inbox=deque();self.sent=[];self.ident=0
        self.ble_ready=ble_ready;self.reject_radio=reject_radio;self.closed=False
    def hello(self):return bytes([1,1,15])
    def inject(self,frame):self.inbox.append(frame);self.writer.send(b'x')
    def send(self,service,op,data=b''):
        self.ident+=1;ident=self.ident;self.sent.append((service,op,data))
        status=2 if service==3 and op==1 and self.reject_radio else 0
        value=bytes([1,self.ble_ready,self.ble_ready,0,247,0,1,0]) if service==0 and op==2 else b''
        self.inject(Frame(service,op|128,ident,bytes([status])+value))
        if service==0 and op==4 and self.ble_ready:self.inject(Frame(0,0x93,0,b'ready'))
        return ident
    def read(self):
        if not self.serial.recv(4096):raise OSError('physical link closed')
    def close(self):
        self.closed=True;self.serial.close();self.writer.close()

class WorkerTests(unittest.TestCase):
    def worker(self,**options):
        events=[];links=[]
        def factory(port):
            link=FakeLink(port,**options);links.append(link);return link
        worker=HubSession('rfcomm://AA:BB:CC:DD:EE:FF/1',events.append,link_factory=factory)
        self.addCleanup(worker.close)
        return worker,events,links
    def wait(self,check):
        until=time.monotonic()+2
        while time.monotonic()<until:
            result=check()
            if result:return result
            time.sleep(.01)
        self.fail('worker state not reached')
    def ready(self,events,token):
        return self.wait(lambda:next((e for e in reversed(events) if e.get('token')==token and e.get('state')=='ready'),None))
    def client(self,path):
        fd=os.open(path,os.O_RDWR|os.O_NONBLOCK|os.O_NOCTTY);self.addCleanup(os.close,fd);return fd
    def configure(self,fd):
        for command,value in ((1,912345000),(2,500000),(3,2),(4,7),(5,5)):
            os.write(fd,kiss(command,value.to_bytes(4 if command<3 else 1,'big')))
        os.write(fd,kiss(6,b'\1'))
    def response(self,fd,command,data):
        decoder=KissDecoder();until=time.monotonic()+2
        while time.monotonic()<until:
            if select.select([fd],[],[],.1)[0]:
                if (command,data) in decoder.feed(os.read(fd,4096)):return
        self.fail('local RNode response missing')
    def test_idle_owner_opens_no_physical_connection(self):
        worker,events,links=self.worker();time.sleep(.02);self.assertEqual(links,[])
    def test_ble_absent_does_not_block_explicit_lora(self):
        worker,events,links=self.worker(ble_ready=False)
        worker.command('attach',token='mesh',service=1,options=dict(ble='11:22:33:44:55:66',address_type=1))
        worker.command('attach',token='radio',service=3,options={})
        radio=self.ready(events,'radio');self.assertEqual(len(links),1)
        self.assertFalse(any(s==3 for s,_,_ in links[0].sent))
        fd=self.client(radio['port']);self.configure(fd);self.response(fd,6,b'\1')
        self.assertTrue(any(s==3 and op==3 for s,op,_ in links[0].sent))
        self.assertFalse(any(e.get('token')=='mesh' and e.get('state')=='ready' for e in events))
    def test_mesh_disconnect_and_error_leave_radio_and_link_alive(self):
        worker,events,links=self.worker()
        worker.command('attach',token='mesh',service=1,options=dict(ble='11:22:33:44:55:66',address_type=1))
        worker.command('attach',token='radio',service=3,options={})
        self.ready(events,'mesh');radio=self.ready(events,'radio');fd=self.client(radio['port'])
        links[0].inject(Frame(0,0x92,0,b'BLE disconnected'))
        self.wait(lambda:any(e.get('token')=='mesh' and e.get('state')=='error' for e in events))
        self.assertFalse(links[0].closed)
        os.write(fd,kiss(8,b'\x73'));self.response(fd,8,b'\x46')
        worker.command('detach',token='mesh');time.sleep(.02)
        self.assertFalse(links[0].closed)
    def test_explicit_mesh_detach_does_not_close_lora(self):
        worker,events,links=self.worker()
        worker.command('attach',token='mesh',service=1,options=dict(ble='11:22:33:44:55:66',address_type=1))
        worker.command('attach',token='radio',service=3,options={})
        self.ready(events,'mesh');radio=self.ready(events,'radio');fd=self.client(radio['port'])
        worker.command('detach',token='mesh')
        self.wait(lambda:any(e.get('token')=='mesh' and e.get('state')=='detached' for e in events))
        os.write(fd,kiss(8,b'\x73'));self.response(fd,8,b'\x46');self.assertFalse(links[0].closed)
    def test_lora_claim_failure_only_detaches_lora(self):
        worker,events,links=self.worker(reject_radio=True)
        worker.command('attach',token='mesh',service=1,options=dict(ble='11:22:33:44:55:66',address_type=1))
        worker.command('attach',token='radio',service=3,options={})
        self.ready(events,'mesh');radio=self.ready(events,'radio');fd=self.client(radio['port']);self.configure(fd)
        self.wait(lambda:any(e.get('token')=='radio' and e.get('state')=='error' for e in events))
        self.assertIn(1,worker.services);self.assertFalse(links[0].closed)

    def test_physical_write_failure_invalidates_every_service(self):
        worker,events,links=self.worker()
        worker.command('attach',token='mesh',service=1,options=dict(ble='11:22:33:44:55:66',address_type=1))
        worker.command('attach',token='radio',service=3,options={})
        self.ready(events,'mesh');radio=self.ready(events,'radio');fd=self.client(radio['port'])
        def broken(*args,**kwargs):raise PhysicalLinkError('Cable removed')
        links[0].send=broken
        self.configure(fd)
        self.wait(lambda:links[0].closed)
        for token in ('mesh','radio'):
            self.assertTrue(any(e.get('token')==token and e.get('state')=='error' for e in events))
        self.assertEqual(worker.services,{})

class Actor:
    def __init__(self,port,publish):self.commands=[];self.closed=False;self.publish=publish
    def command(self,action,**data):self.commands.append((action,data))
    def close(self):self.closed=True
    def abort(self):self.closed=True
class OwnerTests(unittest.TestCase):
    def owner(self):
        owner=HubOwner('/unused','test','rfcomm://aa:bb:cc:dd:ee:ff/01',session_factory=Actor)
        self.addCleanup(owner.close);return owner
    def test_owner_is_idle_and_has_no_contact_book(self):
        owner=self.owner();self.assertEqual(owner.snapshot()['connection_state'],'idle')
        self.assertEqual(owner.worker.commands,[]);self.assertFalse(hasattr(owner,'book'))
        self.assertEqual(canonical_port('rfcomm://aa:bb:cc:dd:ee:ff/01'),'rfcomm://AA:BB:CC:DD:EE:FF/1')
    def test_control_stream_detach_only_releases_its_service(self):
        owner=self.owner();mesh=object();radio=object()
        a=owner.attach_client(mesh,dict(version=1,action='attach',payload=dict(service=1,ble='11:22:33:44:55:66',address_type=1)))
        b=owner.attach_client(radio,dict(version=1,action='attach',payload=dict(service=3)))
        owner.detach_client(mesh);self.assertIn(b['token'],owner.attachments);self.assertNotIn(a['token'],owner.attachments)
        self.assertEqual(owner.worker.commands[-1],('detach',dict(token=a['token'])))
        self.assertFalse(owner.worker.closed)
        owner.post(dict(kind='attachment',token=a['token'],port='/dev/pts/99',state='ready'));owner.drain()
        self.assertNotIn(a['token'],owner.attachments)
    def test_rejects_duplicate_consumer_and_invalid_service(self):
        owner=self.owner();owner.attach_client(object(),dict(version=1,action='attach',payload=dict(service=3)))
        with self.assertRaises(ValueError):owner.attach_client(object(),dict(version=1,action='attach',payload=dict(service=3)))
        for payload in ({'service':True},{'service':4},{'service':3,'port':'/tmp/evil'},{'service':1,'ble':'wrong','address_type':1}):
            with self.assertRaises(ValueError):owner.options(payload)
if __name__=='__main__':unittest.main()
