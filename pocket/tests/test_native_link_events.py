"""Native events may arrive before the outbound link RPC returns."""
import ctypes,queue,sys,tempfile,threading,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum'))
import native_stack as native

class Function:
    def __init__(self,call):self.call=call
    def __call__(self,*args):return self.call(*args)
class API:
    external=False
    def __init__(self):self.functions={};self.engine=None;self.link_ids=0;self.workers=[];self.handles=0
    def __getattr__(self,name):
        if name not in self.functions:self.functions[name]=Function(lambda *args:self.call(name,*args))
        return self.functions[name]
    def call(self,name,*args):
        if name=='pocket_rns_abi':return 2
        if name=='pocket_rns_link':
            self.handles+=1;handle=self.handles
            ctypes.memmove(args[1],b'L'*16,16)
            self.engine.pending.put(dict(event='established',handle=handle,destination=b'd'*16))
            worker=threading.Thread(target=self.engine.drain,daemon=True);self.workers.append(worker);worker.start();worker.join(.1)
            return handle
        if name=='pocket_rns_link_id':
            self.link_ids+=1;ctypes.memmove(args[1],b'L'*16,16);return 16
        return 0

class LinkEventTests(unittest.TestCase):
    def test_established_during_link_creation_is_delivered_once_to_returned_object(self):
        api=API()
        with tempfile.TemporaryDirectory() as tmp:
            engine=native.Engine(None,tmp,lambda _:True,api=api);api.engine=engine
            seen=[]
            try:
                destination=type('Destination',(),dict(handle=1))()
                link=native.Link(destination,established_callback=seen.append)
                engine.drain()
                for worker in api.workers:worker.join(1)
                self.assertEqual(seen,[link])
                self.assertIs(engine.links[link.handle],link)
                self.assertEqual(link.link_id,b'L'*16)
                self.assertEqual(api.link_ids,0,'Outbound link already returns its ID')
            finally:engine.close()

    def test_event_callback_can_create_another_link_without_deadlocking(self):
        api=API()
        with tempfile.TemporaryDirectory() as tmp:
            engine=native.Engine(None,tmp,lambda _:True,api=api);api.engine=engine;seen=[]
            try:
                destination=type('Destination',(),dict(handle=1))()
                def established(link):seen.append(native.Link(destination))
                first=native.Link(destination,established_callback=established)
                worker=threading.Thread(target=engine.drain,daemon=True);worker.start();worker.join(1)
                self.assertFalse(worker.is_alive(),'Event callback blocked creating a link')
                self.assertEqual(len(seen),1)
                self.assertEqual(len(engine.links),2)
                self.assertEqual(api.link_ids,0)
            finally:engine.close()

    def test_external_drain_is_woken_after_registration_without_another_packet(self):
        class ExternalAPI(API):
            external=True
            def __init__(self):
                super().__init__();self.events=threading.Event();self.waited_again=threading.Event();self.waits=0
            def wait_events(self):
                self.waits+=1
                if self.waits>1:self.waited_again.set()
                self.events.wait();self.events.clear()
            def close(self,**kwargs):pass
            def call(self,name,*args):
                result=super().call(name,*args)
                if name=='pocket_rns_link':
                    self.events.set()
                    if not self.waited_again.wait(1):raise RuntimeError('External drain did not attempt the early event')
                return result
        api=ExternalAPI()
        with tempfile.TemporaryDirectory() as tmp:
            engine=native.Engine(None,tmp,lambda _:True,api=api);api.engine=engine;engine.start();done=threading.Event();seen=[]
            try:
                def established(link):seen.append(link);done.set()
                link=native.Link(type('Destination',(),dict(handle=1))(),established_callback=established)
                self.assertTrue(done.wait(1),'Registration did not wake the pending established event')
                self.assertEqual(seen,[link])
            finally:engine.close()

if __name__=='__main__':unittest.main()
