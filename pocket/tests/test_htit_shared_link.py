"""The running hub helper routes MeshCore and RNode over one physical link."""
import os,select,socket,sys,threading,time,unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/meshcore'))
import hub_transport as hub
from rnode_adapter import kiss,KissDecoder
class Link:
    def __init__(self,reject=False):
        self.serial,self.writer=socket.socketpair();self.inbox=deque();self.sent=[];self.ident=0;self.reject=reject
    def request(self,op,data=b'',timeout=3):
        return bytes([1,1,1,0,247,0,1,0]) if op==2 else b''
    def send(self,service,op,data=b''):
        self.ident+=1;self.sent.append((service,op,data));ident=self.ident
        status=2 if self.reject and service==3 and op==1 else 0
        self.inbox.append(hub.Frame(service,op|128,ident,bytes([status])))
        if service==1:self.inbox.append(hub.Frame(1,0x90,0,b'reply'))
        if service==3 and op==4:self.inbox.append(hub.Frame(3,0x90,0,b'\xce\xff\x14'+data))
        self.writer.send(b'x');return ident
    def read(self):
        if not self.serial.recv(4096):raise EOFError('test finished')
class Tests(unittest.TestCase):
    def run_bridge(self,reject=False):
        link=Link(reject);ends={};ready=threading.Event();errors=[]
        original=hub.Endpoint
        def endpoint(name):
            e=original(name);ends[name]=e
            if 'MESHCORE_PORT' in ends and 'RNODE_PORT' in ends:ready.set()
            return e
        def run():
            try:hub.bridge(link,SimpleNamespace(ble=b'123456',address_type=1,peer=None,rnode=True,parent_watch=False))
            except EOFError:pass
            except BaseException as e:errors.append(e)
        patches=[patch.object(hub,'Endpoint',endpoint),patch.object(hub,'wait_ready',lambda *a:None)]
        for p in patches:p.start()
        thread=threading.Thread(target=run);thread.start();self.assertTrue(ready.wait(2))
        self.addCleanup(lambda:[p.stop() for p in patches])
        def cleanup():
            link.writer.close();thread.join(2);link.serial.close();self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.addCleanup(cleanup)
        return link,ends
    def wait(self,predicate):
        end=time.monotonic()+2
        while time.monotonic()<end:
            if predicate():return
            time.sleep(.01)
        self.fail('condition not met')
    def configure(self,fd):
        for c,v in ((1,912345000),(2,500000),(3,2),(4,7),(5,5)):
            os.write(fd,kiss(c,v.to_bytes(4 if c<3 else 1,'big')))
        os.write(fd,kiss(6,b'\1'))
    def test_meshcore_and_lora_share_link_and_route_acks(self):
        link,ends=self.run_bridge();time.sleep(.05);self.assertEqual(link.sent,[])
        self.configure(ends['RNODE_PORT'].slave)
        self.wait(lambda:any(s==3 and op==3 for s,op,_ in link.sent));time.sleep(.05)
        os.write(ends['RNODE_PORT'].slave,kiss(0,b'packet'))
        os.write(ends['MESHCORE_PORT'].slave,b'<\x01\x00\x16')
        self.wait(lambda:(3,4,b'packet') in link.sent and (1,1,b'\x16') in link.sent)
        self.assertTrue(select.select([ends['MESHCORE_PORT'].slave],[],[],1)[0])
        self.assertEqual(os.read(ends['MESHCORE_PORT'].slave,100),b'>\x05\x00reply')
    def test_lora_claim_failure_does_not_kill_meshcore(self):
        link,ends=self.run_bridge(reject=True);self.configure(ends['RNODE_PORT'].slave)
        self.wait(lambda:(3,6,b'') in link.sent)
        os.write(ends['MESHCORE_PORT'].slave,b'<\x01\x00\x16')
        self.wait(lambda:(1,1,b'\x16') in link.sent)
        self.assertTrue(select.select([ends['MESHCORE_PORT'].slave],[],[],1)[0])
        self.assertEqual(os.read(ends['MESHCORE_PORT'].slave,100),b'>\x05\x00reply')
if __name__=='__main__':unittest.main()
