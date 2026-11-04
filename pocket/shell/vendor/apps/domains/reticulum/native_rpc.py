"""ABI-2 native operations over the existing bounded owner protocol.

Only the node executor owns RNS/crypto. Application policy and services remain in
Pocket's existing NativeBackend. No command is automatically replayed.
"""
import ctypes
import os
import threading
import time

FEATURES=frozenset(('links','endpoints','resources','lxmf'))
# Buffer locations are explicit: wire peers never exchange native addresses.
INPUTS=dict(identity=((0,1),),incoming=((0,1),),handler=((3,(4,16)),),announce=((1,2),),
    link=((1,-16),),request=((2,3),),reply=((1,2),(3,4)),resource=((1,2),),
    has_path=((0,-16),),hops=((0,-16),),appdata=((0,-16),),lxmf_send=((1,2),))
OUTPUTS=dict(key=((2,3),),destination=((4,-16),),link_id=((1,-16),),
    lxmf_init=((2,-16),),lxmf_send=((5,-32768),),appdata=((1,2),))
VARIABLE=frozenset(('key','lxmf_send','appdata'))
STRINGS=dict(init=(1,),destination=(2,3),handler=(1,),request=(1,),lxmf_init=(1,))
OPERATIONS=frozenset(('init','reset','online','incoming','identity','key','destination','handler','announce','public',
    'remove_destination','link','link_id','remote','identify','request','reply','teardown','resources','resource',
    'has_path','hops','lxmf_init','lxmf_public','lxmf_announce','lxmf_remember','lxmf_send','appdata','cancel_stamp'))

def capacity(args,spec):
    result=args[spec[0]]*spec[1] if isinstance(spec,tuple) else -spec if spec<0 else args[spec]
    if type(result) is not int or not 0<=result<=32768:raise ValueError('Invalid native buffer capacity')
    return result

def checked_info(value,ready=True):
    if not isinstance(value,dict) or type(value.get('protocol')) is not int or value['protocol']!=1 or type(value.get('abi')) is not int or value['abi']!=2:
        raise ValueError('Node does not provide the ABI-2 executor protocol')
    features=value.get('features')
    if not isinstance(features,(list,tuple)) or len(features)>16 or any(not isinstance(f,str) or not 1<=len(f)<=64 for f in features):raise ValueError('Invalid node capabilities')
    if type(value.get('online')) is not bool:raise ValueError('Invalid node interface state')
    if 'available' in value and type(value['available']) is not bool:raise ValueError('Invalid node availability')
    if value.get('framing') not in (None,'ps02','kiss-fragment-v1'):raise ValueError('Unsupported node framing')
    if value.get('clock') not in (None,'unix-ms-v1'):raise ValueError('Unsupported node clock protocol')
    if value.get('framing')=='kiss-fragment-v1' and (type(value.get('fragment_size')) is not int or not 256<=value['fragment_size']<=2048):raise ValueError('Invalid node fragment size')
    identity=value.get('identity')
    if not isinstance(identity,str) or len(identity)!=32 or any(c not in '0123456789abcdef' for c in identity):raise ValueError('Invalid node identity')
    lease=value.get('lease_seconds')
    if type(lease) not in (int,float) or not 1<=lease<=5:raise ValueError('Node requires a bounded endpoint lease')
    if ready:
        if not FEATURES<=set(features):raise ValueError('Node does not provide link, endpoint, resource and LXMF offload')
        if not value['online']:raise ValueError('External node Reticulum interface is not ready')
    return value

class Method:
    def __init__(self,api,name):self.api,self.name=api,name
    def __call__(self,*args):return self.api.invoke(self.name,args)

class Library:
    """ctypes-compatible facade; only buffer bytes and typed values cross the link."""
    external=True
    def __init__(self,transport,info):
        self.transport=transport;self.info=checked_info(info);self.session=os.urandom(16).hex()
        self.callback=None;self.error=b'';self.stopped=threading.Event();self.ready=threading.Event();self.events=threading.Event()
        self.deadline=time.monotonic();self.failure=None
        self.reader=None;self.renewer=None
    def __getattr__(self,name):
        if name.startswith('pocket_rns_'):return Method(self,name[11:])
        raise AttributeError(name)
    def exchange(self,action,**data):
        value=self.transport.exchange(dict(version=1,action=action,session=self.session,**data))
        if value.get('error'):raise ConnectionError(value['error'])
        return value
    def invoke(self,name,args):
        if name=='abi':return 2
        if name=='error':return self.error
        if name=='poll':return 0
        if name not in OPERATIONS:raise ValueError('Unsupported node operation')
        if name=='init':
            self.callback=args[0]
            opening=dict(identity=self.info['identity'],abi=2)
            if self.info.get('clock')=='unix-ms-v1':
                opening['unix_ms']=int(time.time()*1000)
                if not 0<opening['unix_ms']<1<<63:raise ValueError('Host Unix milliseconds are outside the node protocol range')
            response=self.exchange('native_open',**opening)
            if response.get('identity')!=self.info['identity']:raise ValueError('External node identity changed')
            self.deadline=time.monotonic()+self.info['lease_seconds']
            self.renewer=threading.Thread(target=self._renew,name='external-native-lease',daemon=True);self.renewer.start()
            self.reader=threading.Thread(target=self._subscribe,name='external-native-events',daemon=True);self.reader.start()
            if not self.ready.wait(5):raise ConnectionError('External event stream was not ready')
            if self.failure:raise ConnectionError(self.failure)
            wire=[None,self.session.encode()]
        else:wire=list(args)
        for index,length in INPUTS.get(name,()):
            count=capacity(args,length);wire[index]=ctypes.string_at(args[index],count) if count else b''
        for index,length in OUTPUTS.get(name,()):wire[index]=None
        for index in STRINGS.get(name,()):
            if name!='init':wire[index]=bytes(args[index])
        try:
            result=self.exchange('native_cancel') if name=='cancel_stamp' else self.exchange('native_call',operation=name,arguments=wire)
            code=result['result']
            if type(code) is not int:raise ValueError('Invalid native result')
            if code<0:self.error=str(result.get('native_error','External native operation failed')).encode();return code
            outputs=result.get('outputs',[])
            expected=OUTPUTS.get(name,())
            if len(outputs)!=len(expected):raise ValueError('Invalid native output count')
            for (index,length),raw in zip(expected,outputs):
                count=code if name in VARIABLE else capacity(args,length)
                if not isinstance(raw,bytes) or len(raw)!=count or count>capacity(args,length):raise ValueError('Invalid native output length')
                if count:ctypes.memmove(args[index],raw,count)
            if name=='reset':self.close(released=True)
            return code
        except (OSError,ValueError,ConnectionError) as error:
            self.failure=str(error);self.events.set();raise
    def _subscribe(self):
        try:self.transport.subscribe(self._event,self.stopped,session=self.session)
        except Exception as error:self.failure=str(error);self.ready.set();self.events.set()
    def _event(self,value):
        if self.stopped.is_set():return
        if value.get('session')!=self.session:raise ValueError('Wrong external session')
        if value.get('ready'):self.ready.set();return
        raw=value.get('native_event')
        if not isinstance(raw,bytes) or len(raw)>65536:raise ValueError('Invalid external event')
        source=ctypes.create_string_buffer(raw);output=ctypes.create_string_buffer(32768)
        count=self.callback(source,len(raw),output,len(output))
        if type(count) is not int or not 0<=count<=32768:raise ValueError('Invalid external callback')
        token=value.get('callback')
        if token is not None:self.exchange('native_callback',token=token,data=output.raw[:count])
        self.events.set()
    def _renew(self):
        while not self.stopped.wait(self.info['lease_seconds']/3):
            try:
                self.exchange('native_renew');self.deadline=time.monotonic()+self.info['lease_seconds']
            except Exception as error:
                if not self.stopped.is_set():self.failure=str(error);self.transport.close();self.events.set()
                return
    def wait_events(self):
        if self.failure:
            self.transport.close();raise ConnectionError(self.failure)
        self.events.wait();self.events.clear()
        if self.failure:
            self.transport.close();raise ConnectionError(self.failure)
    def close(self,released=False):
        self.stopped.set();self.transport.close();self.events.set()
        if self.renewer and self.renewer is not threading.current_thread():self.renewer.join(3)
        # If reset wasn't acknowledged, the old endpoint lease must expire
        # before the host is allowed to start its local replacement.
        if not released:
            remaining=max(self.deadline-time.monotonic(),self.info['lease_seconds'])
            if remaining>0:time.sleep(remaining)
