"""Bounded explicit window activation for applications hosted by this desktop."""
import os,selectors
from runtime_codec import frame,frame_size,unpack,HEADER
import _socket as socket
from pathlib import Path

MAX_REPLY_BYTES=8192
MAX_WRITE_BYTES=8192


def encode_reply(result):
    try:
        data=frame(result,MAX_REPLY_BYTES-HEADER)
        if len(data)<=MAX_REPLY_BYTES:return data
    except (TypeError,ValueError,OverflowError):pass
    return frame(dict(ok=False,error='Desktop reply unavailable or too large. Command outcome may be unknown; query status before retrying.'))


class Client:
    def __init__(self,owner,connection):
        self.owner=owner;self.fd=connection;self.pending=bytearray();self.output=None
        connection.setblocking(False);owner.clients.add(self)
        owner.selector.register(connection,selectors.EVENT_READ,self)
    def close(self):
        if self not in self.owner.clients:return
        self.owner.clients.remove(self)
        try:self.owner.selector.unregister(self.fd)
        except KeyError:pass
        self.fd.close()
    def ready(self,mask):
        try:
            if self.output is None:
                data=self.fd.recv(257+HEADER-len(self.pending))
                if not data:self.close();return
                self.pending.extend(data)
                if len(self.pending)>256+HEADER:self.close();return
                size=frame_size(self.pending,256)
                if size is None or len(self.pending)<size:return
                if len(self.pending)!=size:self.close();return
                try:
                    request=unpack(self.pending[HEADER:],256)
                    result=self.owner.request(request)
                except (ValueError,KeyError,TypeError,RuntimeError,OSError) as error:result=dict(ok=False,error=str(error)[:160])
                self.output=encode_reply(result)
                self.write_once()
                if self in self.owner.clients:self.owner.selector.modify(self.fd,selectors.EVENT_WRITE,self)
            elif mask&selectors.EVENT_WRITE:self.write_once()
        except (BlockingIOError,InterruptedError):pass
        except (OSError,ValueError):self.close()

    def write_once(self):
        # One bounded nonblocking attempt per event; never drain a slow peer.
        try:count=self.fd.send(self.output[:MAX_WRITE_BYTES])
        except (BlockingIOError,InterruptedError):return
        if count==0:self.close();return
        self.output=self.output[count:]
        if not self.output:self.close()


class Control:
    def __init__(self,path,selector,activate,command=None):
        self.path=Path(path);self.selector=selector;self.activate=activate;self.command=command;self.clients=set()
        if self.path.exists():raise ValueError('desktop activation socket is already owned')
        self.fd=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            self.fd.bind(str(self.path));self.path.chmod(0o600);self.fd.listen(8);self.fd.setblocking(False)
            selector.register(self.fd,selectors.EVENT_READ,self)
        except BaseException:self.fd.close();raise
    def request(self,request):
        if not isinstance(request,dict):raise ValueError('Expected an object')
        if 'command' in request:
            if self.command is None:raise ValueError('App commands are unavailable')
            return self.command(request)
        name=request['activate']
        if not isinstance(name,str) or not 1<=len(name)<=40:raise ValueError('invalid target')
        self.activate(name);return dict(ok=True)

    def ready(self,mask):
        try:
            fd,_=self.fd._accept()
            connection=socket.socket(fileno=fd)
        except BlockingIOError:return
        if len(self.clients)>=8:connection.close()
        else:
            # A queued request can run before the next model/render pass.
            # recv and write_once are bounded and nonblocking; a partial or
            # slow request remains registered for ordinary selector readiness.
            Client(self,connection).ready(selectors.EVENT_READ)
    def close(self):
        for client in tuple(self.clients):client.close()
        try:self.selector.unregister(self.fd)
        except KeyError:pass
        self.fd.close();self.path.unlink(missing_ok=True)
