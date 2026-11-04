"""Existing LXMF owner callbacks backed by the pinned microLXMF router."""
import ctypes
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from wire import codec,NATIVE_CODEC

def pack(value):return codec.packb(value)
def unpack(data):return codec.unpackb(data,raw=False,strict_map_key=False) if NATIVE_CODEC else codec.unpackb(data)
import native_stack as RNS


def display_name_from_app_data(data):
    value=unpack(data)
    return value[0].decode('utf-8',errors='replace') if isinstance(value,list) and value and isinstance(value[0],bytes) else None
pn_name_from_app_data=display_name_from_app_data

class LXMessage:
    DIRECT=2;SOURCE_UNKNOWN=1;SIGNATURE_INVALID=2
    def __init__(self,destination,source,content='',title='',desired_method=DIRECT):
        if desired_method!=self.DIRECT:raise ValueError('The owner sends direct messages')
        self.destination=destination;self.source=source;self.content=content.encode() if isinstance(content,str) else bytes(content)
        self.hash=None;self.delivered=None;self.failed=None;self.packed=None;self.state=1
    def register_delivery_callback(self,callback):self.delivered=callback
    def register_failed_callback(self,callback):self.failed=callback
    def content_as_string(self):return self.content.decode('utf-8',errors='replace')
    def get_source(self):return self.source
    def write_to_directory(self,directory):
        if not self.hash or not self.packed:return None
        raw=pack(dict(state=self.state,lxmf_bytes=self.packed,transport_encrypted=True,transport_encryption='AES-256',method=2))
        fd,temporary=tempfile.mkstemp(prefix='.lxmf-',dir=directory)
        target=Path(directory)/self.hash.hex()
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,target)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
        return str(target)

class Router:
    def __init__(self,owner):
        self.owner=owner;self.engine=owner.stack;self.pending={};self.engine.messaging=self
        output=ctypes.create_string_buffer(16)
        self.engine.call('lxmf_init',owner.identity.handle,owner.station.encode(),output)
        self.delivery=SimpleNamespace(hash=output.raw,announce=self.announce)
    def announce(self,*args,**kwargs):
        if self.owner.message_discovery:self.engine.call('lxmf_public',1);self.engine.call('lxmf_announce')
    def remember(self,identity):self.engine.call('lxmf_remember',identity.handle)
    def stamp_cost(self,destination):
        data=RNS.Identity.recall_app_data(destination)
        if not data:return 0
        value=unpack(data)
        cost=value[1] if isinstance(value,list) and len(value)>1 else None
        if cost is None:return 0
        if type(cost) is not int or not 0<=cost<=255:raise ValueError('Invalid LXMF stamp request')
        return cost
    def handle_outbound(self,message):
        token=self.engine.next();self.pending[token]=message
        output=ctypes.create_string_buffer(32768)
        try:n=self.engine.call('lxmf_send',message.destination.handle,message.content,len(message.content),token,self.stamp_cost(message.destination.hash),output)
        except BaseException:
            self.pending.pop(token,None)
            if message.failed:message.failed(message)
            raise
        message.hash=output.raw[:32];message.packed=output.raw[32:n]
    def event(self,event):
        if event['incoming']:
            message=LXMessage.__new__(LXMessage)
            message.hash=event['hash'];message.content=event['content'];message.source_hash=event['source']
            message.signature_validated=event['signature'];message.unverified_reason=event['reason'];message.timestamp=event['timestamp']
            message.source=SimpleNamespace(identity=self.engine.identity(event['remote']))
            message.packed=event['packed'];message.state=event['state']
            self.owner._received(message)
        else:
            message=self.pending.pop(event['handle'],None)
            if message is None:return
            message.hash=event['hash']
            if event['packed']:message.packed=event['packed']
            message.state=event['state']
            callback=message.delivered if event['state']==8 else message.failed
            if callback:callback(message)
    def exit_handler(self):self.pending.clear()
