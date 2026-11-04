"""Isolated node executor for stock-RNS offload acceptance; not installed firmware."""
import ctypes,os,queue,sys,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shell/vendor/apps/domains/reticulum'))
from owner import Owner,serve
from wire import encode
from native_rpc import INPUTS,OUTPUTS,VARIABLE,STRINGS,OPERATIONS,capacity
from native_stack import signature_types
from native_radio import configuration,TCPPackets
from external_node import pack,unpack

class Executor(Owner):
    concurrent_actions={'native_call'}
    def __init__(self,state,station,library,config):
        super().__init__(state,station)
        self.lib=ctypes.CDLL(str(library));self.callback_type=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t)
        for name,args in signature_types(self.callback_type).items():
            f=getattr(self.lib,'pocket_rns_'+name);f.argtypes=args;f.restype=ctypes.c_int
        self.lib.pocket_rns_error.restype=ctypes.c_char_p
        assert self.lib.pocket_rns_abi()==2
        self.dispatcher=None
        if os.environ.get('POCKET_TEST_CPP_DISPATCH'):
            self.cpp=ctypes.CDLL(os.environ['POCKET_TEST_CPP_DISPATCH']);self.dispatcher=self.cpp.pocket_rpc_dispatch
            self.dispatcher.argtypes=[ctypes.c_char_p,ctypes.c_void_p,ctypes.c_size_t,self.callback_type,ctypes.c_char_p,ctypes.c_void_p,ctypes.c_size_t];self.dispatcher.restype=ctypes.c_int
        self.callback=self.callback_type(self.event);self.native_events=queue.Queue(maxsize=32);self.callbacks={}
        self.session=None;self.deadline=0;self.initialized=False;self.radio=None;self.config=config
        self.stopped=threading.Event();self.state_dir=Path(state);self.poller=threading.Thread(target=self.run,daemon=True);self.poller.start()
    def info(self):return dict(version=1,online=True,protocol=1,abi=2,identity='1234567890abcdef'*2,features=['links','endpoints','resources','lxmf'],lease_seconds=3)
    def snapshot(self):return dict(version=1,session=self.session,ready=True)
    def snapshot_frame(self):
        raw=encode(self.snapshot())
        while True:
            try:event=self.native_events.get_nowait()
            except queue.Empty:break
            framed=encode(event)
            if len(raw)+len(framed)>32768:
                self.native_events.put_nowait(event);self.post({'kick':True});break
            raw+=framed
        return raw
    def event(self,pointer,n,output,capacity):
        from external_node import unpack
        raw=ctypes.string_at(pointer,n);event=unpack(raw)
        if event['event']=='outgoing':
            valid=self.session and time.monotonic()<self.deadline and self.radio is not None
            ctypes.memmove(output,bytes([bool(valid and self.radio.send(event['data']))]),1);return 1
        token=None;signal=None
        if event['event']=='resource_advertised':
            token=os.urandom(8).hex();signal=threading.Event();self.callbacks[token]=[signal,None]
        self.native_events.put_nowait(dict(version=1,session=self.session,native_event=raw,callback=token));self.post({'event':True})
        if token:
            try:
                if not signal.wait(4):return 0
                data=self.callbacks[token][1]
                if data is None or len(data)>capacity:return 0
                if data:ctypes.memmove(output,data,len(data))
                return len(data)
            finally:self.callbacks.pop(token,None)
        return 0
    def drain(self):
        while True:
            try:self.events.get_nowait();self.revision+=1
            except queue.Empty:break
    def dispatch(self,request):
        action=request['action']
        if action=='node_info':return self.info()
        if action=='native_open':
            if self.session and time.monotonic()<self.deadline:raise ValueError('Node already leased')
            if request['identity']!=self.info()['identity'] or request['abi']!=2:raise ValueError('Wrong node/ABI')
            self.session=request['session'];self.deadline=time.monotonic()+3
            return self.info()
        if request.get('session')!=self.session or time.monotonic()>=self.deadline:raise ValueError('Node lease expired')
        if action=='native_cancel':return dict(version=1,result=self.lib.pocket_rns_cancel_stamp(),outputs=[])
        if action=='native_renew':self.deadline=time.monotonic()+3;return dict(version=1)
        if action=='native_callback':
            self.callbacks[request['token']][1]=request['data'];self.callbacks[request['token']][0].set();return dict(version=1)
        if action!='native_call':raise ValueError('Unsupported node action')
        op=request['operation'];args=list(request['arguments']);buffers=[]
        if op not in OPERATIONS:raise ValueError('Unknown native operation')
        if self.dispatcher:
            raw=pack(args);output=ctypes.create_string_buffer(65536)
            n=self.dispatcher(op.encode(),raw,len(raw),self.callback,str(self.state_dir/'native').encode(),output,len(output))
            if n<0:raise ValueError('Native dispatcher output exceeds limit')
            reply=unpack(output.raw[:n]);result=reply['result'];outputs=reply['outputs']
            if result<0:return reply
        else:
            for index,length in INPUTS.get(op,()):
                if not isinstance(args[index],bytes) or len(args[index])!=capacity(args,length):raise ValueError('Invalid native input')
            for index,length in OUTPUTS.get(op,()):
                buffer=ctypes.create_string_buffer(capacity(args,length));args[index]=buffer;buffers.append(buffer)
            if op=='init':args=[self.callback,str(self.state_dir/'native').encode()]
            result=getattr(self.lib,'pocket_rns_'+op)(*args)
            if result<0:return dict(version=1,result=result,native_error=self.lib.pocket_rns_error().decode())
        if op=='init':
            self.initialized=True
            if self.radio is None:
                def incoming(data):
                    if self.session and time.monotonic()<self.deadline:self.lib.pocket_rns_incoming(data,len(data))
                self.radio=TCPPackets(configuration(self.config/'config'),incoming,lambda state:None)
        if op=='reset':self.initialized=False;self.session=None
        if not self.dispatcher:
            outputs=[]
            for (index,length),buffer in zip(OUTPUTS.get(op,()),buffers):outputs.append(buffer.raw[:result] if op in VARIABLE else buffer.raw)
        return dict(version=1,result=result,outputs=outputs)
    def run(self):
        while not self.stopped.wait(.1):
            if self.initialized:
                if time.monotonic()>=self.deadline:
                    self.lib.pocket_rns_cancel_stamp()
                    for signal,_ in list(self.callbacks.values()):signal.set()
                    self.lib.pocket_rns_reset();self.initialized=False;self.session=None
                else:self.lib.pocket_rns_poll()
    def close(self):
        self.stopped.set();self.lib.pocket_rns_cancel_stamp()
        for signal,_ in list(self.callbacks.values()):signal.set()
        if self.radio:self.radio.close()
        self.poller.join(5)
        if self.initialized:self.lib.pocket_rns_reset()

if __name__=='__main__':
    import signal
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(SystemExit(0)))
    path,state,library,config=sys.argv[1:]
    serve(path,state,'node',lambda s,n:Executor(s,n,library,Path(config)))
