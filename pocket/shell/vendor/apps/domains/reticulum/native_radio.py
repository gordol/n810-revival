"""Descriptor-driven packet adapters; the existing Connection owns RNode readiness."""
import os
import queue
import select
import threading
from connection import Connection
from rnode_protocol import KISS

class Frames:
    def __init__(self,delimiter,escape,mask=None,limit=65536):
        self.delimiter=delimiter;self.escape=escape;self.mask=mask;self.limit=limit
        self.buffer=bytearray();self.escaped=False;self.active=False
    def feed(self,data):
        for value in data:
            if value==self.delimiter:
                if self.active and self.buffer:yield bytes(self.buffer)
                self.active=True;self.buffer.clear();self.escaped=False
            elif self.active:
                if self.escaped:
                    value=value^self.mask if self.mask is not None else {KISS.TFEND:KISS.FEND,KISS.TFESC:KISS.FESC}.get(value,value)
                    self.escaped=False
                elif value==self.escape:self.escaped=True;continue
                if len(self.buffer)>=self.limit:raise ValueError('Packet framing limit exceeded')
                self.buffer.append(value)

def hdlc(data):return b'\x7e'+data.replace(b'\x7d',b'\x7d\x5d').replace(b'\x7e',b'\x7d\x5e')+b'\x7e'

def configuration(path):
    interfaces=[];current=None
    for line in open(path):
        line=line.strip()
        if line.startswith('[[') and line.endswith(']]'):
            current={};interfaces.append(current)
        elif current is not None and '=' in line:
            key,value=line.split('=',1);current[key.strip()]=value.strip()
    if len(interfaces)!=1:raise ValueError('Native radio owner requires one explicitly selected interface')
    return interfaces[0]

class Stream:
    def __init__(self,fd,receive,publish,codec):
        self.fd=fd;self.receive=receive;self.publish=publish;self.codec=codec
        self.online=False;self.rxb=self.txb=0;self.name='Pocket native transport'
        self.pending=queue.Queue(maxsize=128);self.tail=b'';self.current=None
        self.stopped=threading.Event()
        self.wake_read,self.wake_write=os.pipe();os.set_blocking(self.wake_read,False);os.set_blocking(self.wake_write,False)
    def write(self,data,tag=None):
        if self.stopped.is_set():raise OSError('Native radio transport is closed')
        self.pending.put_nowait((bytes(data),tag))
        try:os.write(self.wake_write,b'x')
        except BlockingIOError:pass
    def start(self):
        self.thread=threading.Thread(target=self.run,name='native-radio-io',daemon=True);self.thread.start()
    def run(self):
        try:
            while not self.stopped.is_set():
                if not self.tail:
                    try:self.tail,self.current=self.pending.get_nowait()
                    except queue.Empty:pass
                readable,writable,_=select.select([self.fd,self.wake_read],[self.fd] if self.tail else [],[],1)
                if self.wake_read in readable:
                    try:os.read(self.wake_read,4096)
                    except BlockingIOError:pass
                if self.fd in writable:
                    try:n=os.write(self.fd,self.tail)
                    except BlockingIOError:n=0
                    self.tail=self.tail[n:]
                    if not self.tail:self.written(self.current);self.current=None
                if self.fd in readable:
                    try:data=os.read(self.fd,4096)
                    except BlockingIOError:continue
                    if not data:raise OSError('Radio stream closed')
                    for frame in self.codec.feed(data):self.frame(frame)
        except Exception as error:
            if not self.stopped.is_set():self.publish(dict(phase='failed',error=str(error),readbacks={}))
        finally:
            self.online=False;self.stopped.set()
            for fd in (self.fd,self.wake_read,self.wake_write):
                try:os.close(fd)
                except OSError:pass
    def written(self,tag):pass
    def close(self):
        self.stopped.set()
        try:os.write(self.wake_write,b'x')
        except OSError:pass
        if getattr(self,'thread',None) and self.thread is not threading.current_thread():self.thread.join(timeout=3)

class PacketStream(Stream):
    def __init__(self,fd,receive,publish):
        super().__init__(fd,receive,publish,Frames(0x7e,0x7d,0x20))
        self.online=True;self.start();self.publish(dict(phase='ready',error=None,readbacks={}))
    def frame(self,data):self.rxb+=len(data);self.receive(data)
    def send(self,data):
        if not self.online:return False
        self.write(hdlc(data),len(data));return True
    def written(self,tag):self.txb+=tag or 0

class TCPPackets(PacketStream):
    def __init__(self,config,receive,publish):
        import _socket as socket
        if config.get('target_host') not in ('127.0.0.1','::1'):raise ValueError('Native test TCP is restricted to numeric loopback')
        raw=socket.socket(socket.AF_INET6 if config['target_host']=='::1' else socket.AF_INET,socket.SOCK_STREAM)
        raw.settimeout(3);raw.connect((config['target_host'],int(config['target_port'])));fd=raw.detach();os.set_blocking(fd,False)
        super().__init__(fd,receive,publish)

class RNode(Stream):
    FIELDS={1:'frequency',2:'bandwidth',3:'txpower',4:'sf',5:'cr',6:'state'}
    def __init__(self,config,receive,publish):
        import termios
        fd=os.open(config['port'],os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
        try:
            attrs=termios.tcgetattr(fd);attrs[0]=attrs[1]=attrs[3]=0
            attrs[2]=termios.CS8|termios.CREAD|termios.CLOCAL;attrs[4]=attrs[5]=termios.B115200
            attrs[6][termios.VMIN]=0;attrs[6][termios.VTIME]=0;termios.tcsetattr(fd,termios.TCSANOW,attrs)
        except BaseException:os.close(fd);raise
        super().__init__(fd,receive,publish,Frames(KISS.FEND,KISS.FESC,limit=1025))
        self.detected=False;self.firmware=None;self.platform=None;self.eligible=set();self.tx_ready=True;self.flow=config.get('flow_control','False').lower() in ('yes','true','1');self.packet_queue=queue.Queue(maxsize=128);self.tx_lock=threading.Lock()
        values=dict(frequency=int(config['frequency']),bandwidth=int(config['bandwidth']),txpower=int(config['txpower']),sf=int(config['spreadingfactor']),cr=int(config['codingrate']),state=1)
        self.connection=Connection(values,self.detect,self.configure,lambda generation:self.close(),self.status)
        self.start();self.connection.start()
    def command(self,number,value,tag=None):self.write(bytes([KISS.FEND,number])+KISS.escape(value)+bytes([KISS.FEND]),tag)
    def detect(self,generation):
        for number,value in ((8,0x73),(0x50,0),(0x48,0),(0x49,0)):self.command(number,bytes([value]))
    def configure(self,generation,values):
        self.eligible.clear()
        for number,field in self.FIELDS.items():self.command(number,values[field].to_bytes(4 if number in (1,2) else 1,'big',signed=field=='txpower'),field)
    def status(self,phase,error):
        self.online=phase=='ready';self.publish(dict(phase=phase,error=error,readbacks=dict(self.connection.replies)))
    def written(self,tag):
        if tag in Connection.fields:self.eligible.add(tag)
        elif isinstance(tag,int):self.txb+=tag
    def frame(self,frame):
        command,data=frame[0],frame[1:]
        if command==0:
            if self.online:self.rxb+=len(data);self.receive(data)
        elif command==8:self.detected=data==b'\x46'
        elif command==0x50 and len(data)==2:
            self.firmware=tuple(data)
            if self.firmware<(1,52):raise ValueError('Unsupported RNode firmware version')
        elif command==0x48 and len(data)==1:self.platform=data[0]
        elif command in self.FIELDS and len(data)==(4 if command in (1,2) else 1):
            field=self.FIELDS[command]
            if field in self.eligible:self.connection.readback(self.connection.generation,field,int.from_bytes(data,'big',signed=field=='txpower'))
        elif command==0x90:raise OSError('RNode reported error '+data.hex())
        elif command==0x0f:
            with self.tx_lock:self.tx_ready=True
            self.flush_packet()
        if self.connection.phase=='detecting' and self.detected and self.firmware and self.platform is not None:self.connection.detected(self.connection.generation)
    def send(self,data):
        if not self.online:return False
        if len(data)>508:raise ValueError('RNode packet exceeds MTU')
        self.packet_queue.put_nowait(bytes(data));self.flush_packet();return True
    def flush_packet(self):
        with self.tx_lock:
            if self.flow and not self.tx_ready:return
            while True:
                try:data=self.packet_queue.get_nowait()
                except queue.Empty:return
                self.command(0,data,len(data));self.tx_ready=not self.flow
                if self.flow:return
    def close(self):
        # Best effort, no waiting and no replay of queued payloads.
        if not self.stopped.is_set():
            try:os.write(self.fd,b'\xc0\x06\x00\xc0\x0a\xff\xc0')
            except OSError:pass
        super().close()
