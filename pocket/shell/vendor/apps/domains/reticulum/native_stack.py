"""Native RNS adapter for Pocket's existing bridge; no process-global RNS replacement."""
import ctypes
import hashlib
import io
import queue
import threading
from pathlib import Path
from types import SimpleNamespace
from wire import codec,NATIVE_CODEC

def unpack(data):
    return codec.unpackb(data,raw=False) if NATIVE_CODEC else codec.unpackb(data)

_ENGINE = None
_LIMIT = 32768

def signature_types(callback_type):
    pointer=ctypes.c_void_p;size=ctypes.c_size_t;integer=ctypes.c_int;string=ctypes.c_char_p
    signatures=dict(lxmf_init=[integer,string,pointer],lxmf_public=[integer],lxmf_announce=[],lxmf_remember=[integer],lxmf_send=[integer,pointer,size,integer,integer,pointer],appdata=[pointer,pointer,size],cancel_stamp=[],init=[callback_type,string],poll=[],reset=[],online=[integer],incoming=[pointer,size],
        identity=[pointer,size,integer],key=[integer,integer,pointer,size],
        destination=[integer,integer,string,string,pointer],handler=[integer,string,integer,pointer,size],
        announce=[integer,pointer,size],public=[integer,integer],remove_destination=[integer],link=[integer,pointer],link_id=[integer,pointer],remote=[integer],
        identify=[integer,integer],request=[integer,string,pointer,size,integer,ctypes.c_double],
        reply=[integer,pointer,size,pointer,size],teardown=[integer],resources=[integer,integer],resource=[integer,pointer,size,integer],has_path=[pointer],hops=[pointer])
    return signatures

class Engine:
    def __init__(self, library, storage, outgoing, api=None):
        global _ENGINE
        if _ENGINE is not None:raise ValueError('One native stack per owner process')
        self.lib=api if api is not None else ctypes.CDLL(str(library));self.outgoing=outgoing
        self.lib.pocket_rns_abi.restype=ctypes.c_int
        if self.lib.pocket_rns_abi()!=2:raise ValueError('Unsupported native Reticulum ABI')
        self.pending=queue.SimpleQueue();self.drain_lock=threading.RLock();self.links={};self.destinations={};self.requests={};self.resources={}
        self.server_jobs=queue.Queue(maxsize=4);self.server_slots=threading.BoundedSemaphore(4);self.server_workers=[]
        self.messaging=None;self.identities={};self.observers=[];self.token=0;self.last_error=None;self.stopped=threading.Event()
        self.callback_type=ctypes.CFUNCTYPE(ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t)
        signatures=signature_types(self.callback_type)
        for name,args in signatures.items():
            method=getattr(self.lib,'pocket_rns_'+name);method.argtypes=args;method.restype=ctypes.c_int
        self.lib.pocket_rns_error.restype=ctypes.c_char_p
        self.callback=self.callback_type(self._callback)
        _ENGINE=self
        try:self.call('init',self.callback,str(storage).encode())
        except BaseException:
            try:self.call('reset')
            finally:
                if getattr(self.lib,'external',False):self.lib.close()
                _ENGINE=None
            raise
    def call(self,name,*args):
        result=getattr(self.lib,'pocket_rns_'+name)(*args)
        if result<0:raise ValueError(self.lib.pocket_rns_error().decode(errors='replace'))
        return result
    def next(self):self.token+=1;return self.token
    def identity(self,handle):
        if not handle:return None
        if handle not in self.identities:self.identities[handle]=Identity(_handle=handle)
        return self.identities[handle]
    def link(self,handle):
        if handle not in self.links:
            link=Link.__new__(Link);link._init(handle);self.links[handle]=link
        return self.links[handle]
    def _callback(self,pointer,n,output,capacity):
        try:
            if n>65536:raise ValueError('Native event exceeds limit')
            event=unpack(ctypes.string_at(pointer,n));kind=event['event'];answer=b''
            if kind=='outgoing':answer=bytes([bool(self.outgoing(event['data']))])
            elif kind=='resource_advertised':
                link=self.links.get(event['handle']);ad=SimpleNamespace(get_data_size=lambda:event['size'])
                answer=bytes([bool(link and link.resource_callback and link.resource_callback(ad))])
            else:self.pending.put(event)
            if not isinstance(answer,bytes) or len(answer)>capacity:raise ValueError('Invalid bridge callback response')
            if answer:ctypes.memmove(output,answer,len(answer))
            return len(answer)
        except Exception as error:
            self.last_error=str(error);return 0
    def answer(self,event):
        if not self.server_slots.acquire(blocking=False):
            from wire import encode
            response=encode(dict(version=1,error='Service busy; command was not executed'))
            self.call('reply',event['handle'],event['request'],len(event['request']),response,len(response));return
        if not self.server_workers:
            for index in range(4):
                worker=threading.Thread(target=self._serve_requests,name='native-service-response',daemon=True)
                self.server_workers.append(worker);worker.start()
        self.server_jobs.put_nowait(event)
    def _serve_requests(self):
        from wire import encode
        while not self.stopped.is_set():
            event=self.server_jobs.get()
            if event is None:return
            try:
                link=self.link(event['handle']);remote=self.identity(event['remote'])
                destination=next((d for d in self.destinations.values() if link in d.links),None)
                handler=destination.handlers.get(event['path'].decode()) if destination else None
                if handler is None:raise ValueError('No native request handler for '+event['path'].decode())
                response=handler(event['path'].decode(),event['data'],event['request'],event['link'],remote,event['at'])
                if response and not self.stopped.is_set():self.call('reply',event['handle'],event['request'],len(event['request']),response,len(response))
            except Exception as error:
                self.last_error=str(error)
                if not self.stopped.is_set():
                    response=encode(dict(version=1,error=str(error)[:240]))
                    try:self.call('reply',event['handle'],event['request'],len(event['request']),response,len(response))
                    except ValueError:pass
            finally:self.server_slots.release()
    def drain(self):
        if not self.drain_lock.acquire(blocking=False):return
        try:
            while True:
                try:event=self.pending.get_nowait()
                except queue.Empty:return
                kind=event['event'];handle=event['handle']
                try:
                    if kind=='lxmf':
                        if self.messaging:self.messaging.event(event)
                    elif kind=='request':
                        self.answer(event)
                    elif kind=='established':
                        link=self.link(handle)
                        for destination in self.destinations.values():
                            if destination.hash==event['destination'] and destination.direction==Destination.IN:
                                if link not in destination.links:destination.links.append(link)
                                if destination.established:destination.established(link)
                        if link.established:link.established(link)
                    elif kind=='announce':
                        identity=self.identity(handle)
                        for observer in tuple(self.observers):observer.received_announce(event['destination'],identity,event['data'])
                    elif kind=='closed':
                        link=self.links.pop(handle,None)
                        if link and link.closed:link.closed(link)
                        for d in self.destinations.values():d.links[:]=[l for l in d.links if l is not link]
                    elif kind in ('response','failed'):
                        callbacks=self.requests.pop(handle,None)
                        if callbacks:
                            callback=callbacks[0 if kind=='response' else 1]
                            if callback:callback(SimpleNamespace(response=event.get('data')))
                    elif kind=='resource':
                        link=self.link(handle)
                        if link.resource_concluded:link.resource_concluded(SimpleNamespace(status=event['status'],data=io.BytesIO(event['data'])))
                    elif kind=='delivered':
                        callback=self.resources.pop(handle,None)
                        if callback:callback(SimpleNamespace(status=event['status']))
                except Exception as error:self.last_error=str(error)
        finally:self.drain_lock.release()
    def receive(self,data):
        consumed=self.call('incoming',data,len(data));self.drain();return bool(consumed)
    def run(self):
        try:
            while not self.stopped.is_set():
                if getattr(self.lib,'external',False):self.lib.wait_events()
                else:self.call('poll');self.stopped.wait(.1)
                if self.stopped.is_set():break
                self.drain()
        except Exception as error:
            self.last_error=str(error)
            if not self.stopped.is_set() and callable(getattr(self,'failure',None)):self.failure(error)
    def start(self):
        self.thread=threading.Thread(target=self.run,name='native-reticulum',daemon=True);self.thread.start()
    def cancel_stamp(self):self.call('cancel_stamp')
    def close(self):
        global _ENGINE
        released=False
        try:
            try:self.cancel_stamp()
            except (OSError,ValueError,ConnectionError):
                if not getattr(self.lib,'external',False):raise
            self.stopped.set()
            if getattr(self.lib,'external',False):self.lib.events.set()
            for _ in self.server_workers:
                try:self.server_jobs.put_nowait(None)
                except queue.Full:break
            if getattr(self,'thread',None) and self.thread is not threading.current_thread():self.thread.join(timeout=3)
            self.call('reset');released=True
        finally:
            if getattr(self.lib,'external',False):self.lib.close(released=released)
            if _ENGINE is self:_ENGINE=None
            Transport.interfaces=[];Transport.destinations=[]

class Identity:
    def __init__(self,create_keys=True,_handle=None):
        self.handle=_handle or (_ENGINE.call('identity',None,0,1) if create_keys else None)
    def load_public_key(self,key):
        self.handle=_ENGINE.call('identity',key,len(key),0);self._public=bytes(key)
    def _key(self,private):
        output=ctypes.create_string_buffer(64);n=_ENGINE.call('key',self.handle,private,output,len(output));return output.raw[:n]
    def get_public_key(self):
        if not hasattr(self,'_public'):self._public=self._key(0)
        return self._public
    def get_private_key(self):return self._key(1)
    @property
    def hash(self):return hashlib.sha256(self.get_public_key()).digest()[:16]
    @staticmethod
    def recall_app_data(destination):
        output=ctypes.create_string_buffer(1024);n=_ENGINE.call('appdata',destination,output,len(output));return output.raw[:n] if n else None
    @classmethod
    def from_file(cls,path):
        key=Path(path).read_bytes()
        if len(key)!=64:raise ValueError('Invalid existing private identity; refusing replacement')
        return cls(_handle=_ENGINE.call('identity',key,len(key),1))

class Destination:
    IN=0x11;OUT=0x12;SINGLE=0;ALLOW_NONE=0;ALLOW_ALL=1;ALLOW_LIST=2
    def __init__(self,identity,direction,kind,app,*aspects):
        if kind!=self.SINGLE:raise ValueError('Native bridge requires a single destination')
        expected=self.hash_from_name_and_identity('.'.join((app,)+aspects),identity)
        existing=next((d for d in _ENGINE.destinations.values() if d.direction==direction and d.hash==expected),None)
        if existing is not None:
            self.__dict__=existing.__dict__;return
        output=ctypes.create_string_buffer(16)
        self.handle=_ENGINE.call('destination',identity.handle,direction,app.encode(),'.'.join(aspects).encode(),output)
        self.hash=output.raw;self.direction=direction;self.identity=identity;self.links=[];self.handlers={};self.established=None
        _ENGINE.destinations[self.handle]=self
        Transport.destinations.append(self)
    @staticmethod
    def hash_from_name_and_identity(name,identity):
        return hashlib.sha256(hashlib.sha256(name.encode()).digest()[:10]+identity.hash).digest()[:16]
    def register_request_handler(self,path,response_generator,allow=0,allowed_list=(),auto_compress=False):
        if auto_compress:raise ValueError('Native bridge does not compress requests')
        allowed=b''.join(allowed_list);_ENGINE.call('handler',self.handle,path.encode(),allow,allowed,len(allowed_list));self.handlers[path]=response_generator
    def deregister_request_handler(self,path):
        _ENGINE.call('handler',self.handle,path.encode(),0,b'',0);self.handlers.pop(path,None)
    def set_link_established_callback(self,callback):self.established=callback
    def set_max_request_size(self,size):
        if size>_LIMIT:raise ValueError('Native service limit exceeded')
    def set_public_discovery(self,enabled):_ENGINE.call('public',self.handle,int(enabled))
    def announce(self,app_data=None,*args,**kwargs):
        self.set_public_discovery(True)
        data=app_data or b'';_ENGINE.call('announce',self.handle,data,len(data))

class Link:
    ACCEPT_NONE=0;ACCEPT_APP=1;ACCEPT_ALL=2
    def _init(self,handle,link_id=None):
        self.handle=handle;self.established=self.closed=self.resource_callback=self.resource_concluded=None
        if link_id is None:
            output=ctypes.create_string_buffer(16);_ENGINE.call('link_id',handle,output);link_id=output.raw
        self.link_id=link_id
    def __init__(self,destination,established_callback=None,closed_callback=None):
        # Events can arrive before a remote link RPC returns. Publish the object
        # and callbacks together before the existing event drain can see them.
        with _ENGINE.drain_lock:
            output=ctypes.create_string_buffer(16);handle=_ENGINE.call('link',destination.handle,output)
            self._init(handle,output.raw);self.established=established_callback;self.closed=closed_callback;_ENGINE.links[handle]=self
        if getattr(_ENGINE.lib,'external',False):_ENGINE.lib.events.set()
    def get_remote_identity(self):return _ENGINE.identity(_ENGINE.call('remote',self.handle))
    def identify(self,identity):_ENGINE.call('identify',self.handle,identity.handle)
    def teardown(self):_ENGINE.call('teardown',self.handle)
    def set_link_closed_callback(self,callback):self.closed=callback
    def set_resource_strategy(self,strategy):_ENGINE.call('resources',self.handle,strategy)
    def set_resource_callback(self,callback):self.resource_callback=callback
    def set_resource_concluded_callback(self,callback):self.resource_concluded=callback
    def request(self,path,data=b'',response_callback=None,failed_callback=None,timeout=25,max_response_size=_LIMIT):
        if len(data)>_LIMIT or max_response_size>_LIMIT:raise ValueError('Native service limit exceeded')
        token=_ENGINE.next();_ENGINE.requests[token]=(response_callback,failed_callback)
        try:
            if not _ENGINE.call('request',self.handle,path.encode(),data,len(data),token,float(timeout)):
                _ENGINE.requests.pop(token,None);return None
        except BaseException:_ENGINE.requests.pop(token,None);raise
        return token

class Resource:
    COMPLETE=6
    def __init__(self,data,link,callback=None,auto_compress=False):
        if auto_compress or len(data)>_LIMIT:raise ValueError('Native resource limit exceeded')
        token=_ENGINE.next();_ENGINE.resources[token]=callback
        try:_ENGINE.call('resource',link.handle,data,len(data),token)
        except BaseException:_ENGINE.resources.pop(token,None);raise

class Transport:
    interfaces=[]
    destinations=[]
    path_table={}
    @staticmethod
    def has_path(destination):return bool(_ENGINE.call('has_path',destination))
    @staticmethod
    def deregister_destination(destination):
        for path in destination.handlers:_ENGINE.call('handler',destination.handle,path.encode(),0,b'',0)
        _ENGINE.call('remove_destination',destination.handle)
        _ENGINE.destinations.pop(destination.handle,None)
        Transport.destinations[:]=[d for d in Transport.destinations if d.handle!=destination.handle]

    @staticmethod
    def register_announce_handler(handler):_ENGINE.observers.append(handler)
    @staticmethod
    def deregister_announce_handler(handler):
        if handler in _ENGINE.observers:_ENGINE.observers.remove(handler)
    @staticmethod
    def hops_to(destination):return _ENGINE.call('hops',destination)
    @staticmethod
    def next_hop_interface(destination):return Transport.interfaces[0] if Transport.interfaces else None

Reticulum=SimpleNamespace(transport_enabled=lambda:False)
