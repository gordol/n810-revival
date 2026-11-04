"""One framed USB/SPP connection for provisioning and native-owner RPC."""
import os
import queue
import select
import threading
import time
import struct
from wire import encode,decode,LIMIT

class Fragments:
    """Bounded kiss-fragment-v1 assemblies; incomplete commands never dispatch."""
    def __init__(self,size):self.size=size;self.pending={}
    def feed(self,raw):
        now=time.monotonic()
        self.pending={key:value for key,value in self.pending.items() if now-value[2]<=10}
        if len(raw)<9 or len(raw)>8+self.size:raise ValueError('Invalid node fragment size')
        key,offset,total=struct.unpack('!IHH',raw[:8]);chunk=raw[8:]
        if not key or not 1<=total<=LIMIT or offset+len(chunk)>total:raise ValueError('Invalid node fragment range')
        if offset==0:
            if key in self.pending or len(self.pending)>=8:raise ValueError('Node fragment assembly limit or duplicate')
            self.pending[key]=(total,bytearray(),now)
        if key not in self.pending:raise ValueError('Node fragment has no initial chunk')
        expected,data,_=self.pending[key]
        if total!=expected or offset!=len(data):raise ValueError('Out-of-order node fragment')
        data.extend(chunk)
        if len(data)==total:
            del self.pending[key];return bytes(data)
        self.pending[key]=(total,data,now)
        return None

class Port:
    def __init__(self,connection):
        self.connection=connection;self.fd=connection.fd;self.pending={};self.lock=threading.Lock()
        self.fragment_size=getattr(connection,'fragment_size',0);self.fragments=Fragments(self.fragment_size)
        self.write_condition=threading.Condition();self.writing=False;self.urgent=0
        self.sequence=100;self.stopped=threading.Event();self.error=None
        self.wake_read,self.wake_write=os.pipe()
        self.thread=threading.Thread(target=self.run,name='node-wire',daemon=True);self.thread.start()
    def send(self,command,raw,priority=False,cancelled=lambda:False):
        if len(raw)>(LIMIT if command==0x88 else LIMIT+256):raise ValueError('Node frame exceeds limit')
        if command==0x88 and self.fragment_size and len(raw)>self.fragment_size:
            with self.lock:
                self.sequence+=1;key=self.sequence
                if key>0x7fffffff:raise ValueError('Node sequence exhausted; reconnect')
            for offset in range(0,len(raw),self.fragment_size):
                chunk=struct.pack('!IHH',key,offset,len(raw))+raw[offset:offset+self.fragment_size]
                self.write_frame(0x89,chunk,priority,cancelled)
        else:self.write_frame(command,raw,priority,cancelled)
    def write_frame(self,command,raw,priority,cancelled):
        frame=b'\xc0'+bytes([command])+raw.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc')+b'\xc0'
        with self.write_condition:
            if priority:self.urgent+=1
            try:
                while self.writing or (self.urgent and not priority):
                    if self.error or cancelled():raise ConnectionError(self.error or 'Node request cancelled; outcome may be unknown')
                    self.write_condition.wait()
                if self.error or cancelled():raise ConnectionError(self.error or 'Node request cancelled; outcome may be unknown')
                self.writing=True
            finally:
                if priority:self.urgent-=1
                self.write_condition.notify_all()
        deadline=time.monotonic()+4
        try:
            while frame:
                if self.error:raise ConnectionError(self.error)
                remaining=deadline-time.monotonic()
                if remaining<=0 or not select.select([],[self.fd],[],remaining)[1]:raise TimeoutError('Node write timed out')
                try:n=os.write(self.fd,frame)
                except BlockingIOError:continue
                if n<=0:raise ConnectionError('Node disconnected')
                frame=frame[n:]
        finally:
            with self.write_condition:self.writing=False;self.write_condition.notify_all()
    def allocate(self):
        with self.lock:
            if self.error:raise ConnectionError(self.error)
            if len(self.pending)>=8:raise ValueError('External node busy; request was not sent')
            self.sequence+=1;key=self.sequence;messages=queue.Queue(maxsize=32);self.pending[key]=messages
            return key,messages
    def remove(self,key):
        with self.lock:return self.pending.pop(key,None)
    def receive(self,messages,timeout):
        try:value=messages.get(timeout=timeout)
        except queue.Empty:raise TimeoutError('External request timed out; outcome may be unknown') from None
        if isinstance(value,Exception):raise value
        return value
    def query(self,operation,payload):
        from external_node import pack
        key,messages=self.allocate()
        try:
            self.send(0x86,pack([operation,key,payload]),priority=True);value=self.receive(messages,4)
            if value[0]!=operation:raise ValueError('Node rejected the provisioning query')
            return value[2]
        finally:self.remove(key)
    def fail(self,error):
        self.error=str(error)
        with self.write_condition:self.write_condition.notify_all()
        with self.lock:
            for messages in self.pending.values():
                try:messages.put_nowait(ConnectionError(self.error))
                except queue.Full:pass
    def run(self):
        from native_radio import Frames
        from external_node import unpack
        decoder=Frames(192,219,limit=LIMIT+256)
        try:
            while not self.stopped.is_set():
                ready=select.select([self.fd,self.wake_read],[],[])[0]
                if self.wake_read in ready:break
                try:data=os.read(self.fd,4096)
                except BlockingIOError:continue
                if not data:raise ConnectionError('External node disconnected')
                for frame in decoder.feed(data):
                    if frame[0]==0x87:
                        value=unpack(frame[1:])
                        if not isinstance(value,list) or len(value)!=3:raise ValueError('Malformed provisioning reply')
                        key=value[1]
                    elif frame[0] in (0x88,0x89):
                        raw=frame[1:]
                        if frame[0]==0x89:
                            if not self.fragment_size:raise ValueError('Unnegotiated node fragmentation')
                            raw=self.fragments.feed(raw)
                            if raw is None:continue
                        value=decode(raw);key=value.get('channel')
                        if key==0 and isinstance(value.get('error'),str):
                            raise ConnectionError('External protocol error: '+value['error'][:240])
                    else:continue
                    if type(key) is not int:raise ValueError('Invalid node channel')
                    with self.lock:
                        messages=self.pending.get(key)
                        if messages is not None:messages.put_nowait(value)
        except Exception as error:self.fail(error)
        finally:
            self.fail(self.error or 'Node connection closed')
            os.close(self.wake_read);os.close(self.wake_write)
    def close(self):
        self.stopped.set()
        try:os.write(self.wake_write,b'x')
        except OSError:pass
        self.thread.join(3)
        if self.thread.is_alive():raise RuntimeError('Node wire did not stop')

class Transport:
    def __init__(self,port):
        self.port=port;self.channels={};self.lock=threading.Lock();self.closed=False
    def allocate(self):
        with self.lock:
            if self.closed:raise ConnectionError('Node transport closed')
            key,messages=self.port.allocate();self.channels[key]=messages
            return key,messages
    def remove(self,key):
        with self.lock:self.channels.pop(key,None)
        self.port.remove(key)
    def exchange(self,request):
        from service_transport import request_timeout
        key,messages=self.allocate()
        try:
            self.port.send(0x88,encode(dict(request,channel=key)),priority=request['action'] in ('native_renew','native_cancel','native_callback'),cancelled=lambda:self.closed)
            timeout=2 if request['action'] in ('native_cancel','native_renew') else request_timeout(request)+10
            return self.port.receive(messages,timeout)
        finally:self.remove(key)
    def subscribe(self,publish,stopped,session):
        key,messages=self.allocate()
        try:
            self.port.send(0x88,encode(dict(version=1,action='subscribe',session=session,channel=key)),priority=True,cancelled=lambda:self.closed)
            while not stopped.is_set():publish(self.port.receive(messages,None))
        finally:self.remove(key)
    def close(self):
        with self.lock:
            self.closed=True
            for key,messages in self.channels.items():
                self.port.remove(key)
                try:messages.put_nowait(ConnectionError('External transport closed; outcome may be unknown'))
                except queue.Full:pass
        with self.port.write_condition:self.port.write_condition.notify_all()

class SocketTransport:
    """Private local IPC, including existing SSH forwarding; no raw remote TCP."""
    def __init__(self,path):
        from service_transport import SocketTransport as Local
        import stat
        info=path.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('Node socket must be private and user-owned')
        self.path=path;self.local=Local(str(path));self.clients=set();self.lock=threading.Lock();self.closed=False
    def connect(self):
        client=self.local.connect()
        with self.lock:
            if self.closed:client.close();raise ConnectionError('Node transport closed')
            self.clients.add(client)
        return client
    def exchange(self,request):
        from wire import read_socket
        client=self.connect()
        try:
            client.settimeout(2 if request['action'] in ('native_cancel','native_renew') else 25)
            client.sendall(encode(request));return read_socket(client)
        finally:
            with self.lock:self.clients.discard(client)
            client.close()
    def subscribe(self,publish,stopped,session):
        from wire import read_socket
        client=self.connect()
        try:
            client.sendall(encode(dict(version=1,action='subscribe',session=session)));client.settimeout(None)
            while not stopped.is_set():publish(read_socket(client))
        finally:
            with self.lock:self.clients.discard(client)
            client.close()
    def close(self):
        import _socket as socket
        with self.lock:
            self.closed=True
            for client in self.clients:
                try:client.shutdown(socket.SHUT_RDWR)
                except OSError:pass
