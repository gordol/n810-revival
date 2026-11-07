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
                readable,writable,_=select.select([self.fd,self.wake_read],[self.fd] if self.tail else [],[])
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
    def __init__(self,fd,receive,publish,limit=65536):
        super().__init__(fd,receive,publish,Frames(0x7e,0x7d,0x20,limit=limit))
        self.online=True;self.start();self.publish(dict(phase='ready',error=None,readbacks={}))
    def frame(self,data):self.rxb+=len(data);self.receive(data)
    def send(self,data):
        if not self.online:return False
        self.write(hdlc(data),len(data));return True
    def written(self,tag):self.txb+=tag or 0

def open_serial(config):
    import termios
    speed=int(config.get('speed',115200))
    baud=getattr(termios,'B'+str(speed),None)
    if baud is None:raise ValueError('Unsupported serial speed: '+str(speed))
    if int(config.get('databits',8))!=8 or str(config.get('parity','none')).lower() not in ('none','n') or int(config.get('stopbits',1))!=1:
        raise ValueError('Native serial carriers require 8 data bits, no parity and 1 stop bit')
    fd=os.open(config['port'],os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
    try:
        attrs=termios.tcgetattr(fd);attrs[0]=attrs[1]=attrs[3]=0
        attrs[2]=termios.CS8|termios.CREAD|termios.CLOCAL
        attrs[4]=attrs[5]=baud
        attrs[6][termios.VMIN]=1;attrs[6][termios.VTIME]=0
        termios.tcsetattr(fd,termios.TCSANOW,attrs)
    except BaseException:
        os.close(fd);raise
    return fd


class SerialPackets(PacketStream):
    """Stock RNS SerialInterface framing over an explicitly selected local port."""
    def __init__(self,config,receive,publish):
        fd=open_serial(config)
        super().__init__(fd,receive,publish,limit=564)
        self.name='Direct serial peer'

    def send(self,data):
        if len(data)>564:raise ValueError('Serial packet exceeds the stock RNS 564-byte limit')
        return super().send(data)


class KISSPackets(Stream):
    """Port-zero raw KISS packets; configuration writes precede readiness."""
    def __init__(self,config,receive,publish):
        if str(config.get('flow_control','False')).lower() in ('true','yes','1'):
            raise ValueError('Native raw KISS flow control is not supported')
        if config.get('id_interval') or config.get('id_callsign'):
            raise ValueError('Native raw KISS identification beacons are not supported')
        commands=[]
        for number,key,default,scale in ((1,'preamble',350,10),(4,'txtail',20,10),(2,'persistence',64,1),(3,'slottime',20,10)):
            value=int(config.get(key,default))
            if not 0<=value<=255*scale:raise ValueError('Invalid KISS '+key)
            commands.append(bytes([number,value//scale]))
        fd=open_serial(config)
        super().__init__(fd,receive,publish,Frames(KISS.FEND,KISS.FESC,limit=565))
        self.name='Raw KISS peer'
        for index,command in enumerate(commands):
            self.write(bytes([KISS.FEND])+KISS.escape(command)+bytes([KISS.FEND]),'ready' if index==len(commands)-1 else None)
        self.start()

    def frame(self,data):
        if data and data[0]==0 and len(data)>1:
            self.rxb+=len(data)-1;self.receive(data[1:])

    def send(self,data):
        if not self.online:return False
        if len(data)>564:raise ValueError('KISS packet exceeds the stock RNS 564-byte limit')
        self.write(bytes([KISS.FEND,0])+KISS.escape(data)+bytes([KISS.FEND]),len(data))
        return True

    def written(self,tag):
        if tag=='ready':
            self.online=True;self.publish(dict(phase='ready',error=None,readbacks={}))
        elif tag is not None:self.txb+=tag


class TCPPackets:
    """One explicitly configured direct peer; reconnect without replaying packets."""
    MAX_PACKET=32768
    def __init__(self,config,receive,publish):
        import ipaddress
        import _socket as socket
        self.server=config.get('type')=='TCPServerInterface'
        self.host=str(config.get('listen_ip' if self.server else 'target_host',''))
        address=ipaddress.ip_address(self.host)
        self.port=int(config.get('listen_port' if self.server else 'target_port',0))
        if not 1<=self.port<=65535:raise ValueError('TCP port must be between 1 and 65535')
        self.family=socket.AF_INET6 if address.version==6 else socket.AF_INET
        self.receive,self.publish=receive,publish
        self.name='Direct peer '+('listener' if self.server else 'client')
        self.online=False;self.phase='listening' if self.server else 'connecting';self.rxb=self.txb=0
        self.pending=queue.Queue(maxsize=32);self.stopped=threading.Event()
        self.wake_read,self.wake_write=os.pipe();os.set_blocking(self.wake_read,False);os.set_blocking(self.wake_write,False)
        self.wake_lock=threading.Lock();self.listener=None
        try:
            if self.server:
                self.listener=socket.socket(self.family,socket.SOCK_STREAM)
                self.listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                self.listener.bind((self.host,self.port));self.listener.listen(1);self.listener.setblocking(False)
            self.thread=threading.Thread(target=self.run,name='native-peer-tcp',daemon=True);self.thread.start()
        except BaseException:
            if self.listener:self.listener.close()
            os.close(self.wake_read);os.close(self.wake_write);raise
    def status(self,phase,error=None):
        self.phase=phase;self.online=phase=='ready'
        self.publish(dict(phase=phase,error=error,readbacks=dict(host=self.host,port=self.port,mode='listen' if self.server else 'connect')))
    def send(self,data):
        if not self.online or self.stopped.is_set():return False
        if not 1<=len(data)<=self.MAX_PACKET:raise ValueError('Direct peer packet exceeds limit')
        try:self.pending.put_nowait(hdlc(bytes(data)))
        except queue.Full:return False
        self.wake()
        return True
    def wake(self):
        with self.wake_lock:
            if self.wake_write is not None:
                try:os.write(self.wake_write,b'x')
                except (BlockingIOError,OSError):pass
    def clear_pending(self):
        while True:
            try:self.pending.get_nowait()
            except queue.Empty:return
    def run(self):
        import errno,time
        import _socket as socket
        peer=None;connecting=False;tail=b'';retry=0.;delay=.25;parser=Frames(0x7e,0x7d,0x20,limit=self.MAX_PACKET)
        try:
            self.status(self.phase)
            while not self.stopped.is_set():
                now=time.monotonic()
                if not self.server and peer is None and now>=retry:
                    peer=socket.socket(self.family,socket.SOCK_STREAM);peer.setblocking(False)
                    result=peer.connect_ex((self.host,self.port))
                    if result not in (0,errno.EINPROGRESS,errno.EWOULDBLOCK,errno.EALREADY):
                        peer.close();peer=None;retry=now+delay;delay=min(5,delay*2);self.status('reconnecting',os.strerror(result))
                    else:
                        connecting=result!=0;deadline=now+15
                        if not connecting:self.status('ready');delay=.25
                if peer is not None and self.online and not tail:
                    try:tail=self.pending.get_nowait()
                    except queue.Empty:pass
                readers=[self.wake_read]+([self.listener] if self.listener else [])+([peer] if peer is not None else [])
                writers=[peer] if peer is not None and (connecting or tail) else []
                timeout=max(0,retry-now) if peer is None and not self.server else max(0,deadline-now) if connecting else None
                readable,writable,_=select.select(readers,writers,[],timeout)
                if self.wake_read in readable:
                    try:os.read(self.wake_read,4096)
                    except BlockingIOError:pass
                if self.stopped.is_set():break
                if self.listener in readable:
                    descriptor,_=self.listener._accept();incoming=socket.socket(fileno=descriptor);incoming.setblocking(False)
                    if peer is not None:incoming.close()
                    else:peer=incoming;parser=Frames(0x7e,0x7d,0x20,limit=self.MAX_PACKET);self.status('ready')
                if peer is None:continue
                try:
                    if connecting:
                        if peer in writable:
                            error=peer.getsockopt(socket.SOL_SOCKET,socket.SO_ERROR)
                            if error:raise OSError(error,os.strerror(error))
                            connecting=False;delay=.25;self.status('ready')
                        elif time.monotonic()>=deadline:raise TimeoutError('Peer connection timed out')
                        else:continue
                    if peer in readable:
                        data=peer.recv(8192)
                        if not data:raise ConnectionError('Peer disconnected')
                        for frame in parser.feed(data):self.rxb+=len(frame);self.receive(frame)
                    if peer in writable and tail:
                        count=peer.send(tail)
                        if count==0:raise ConnectionError('Peer disconnected')
                        self.txb+=count;tail=tail[count:]
                except BlockingIOError:pass
                except (OSError,ValueError) as error:
                    peer.close();peer=None;connecting=False;tail=b'';self.clear_pending()
                    parser=Frames(0x7e,0x7d,0x20,limit=self.MAX_PACKET)
                    retry=time.monotonic()+delay;delay=min(5,delay*2)
                    self.status('listening' if self.server else 'reconnecting',str(error))
        except Exception as error:
            if not self.stopped.is_set():self.status('failed',str(error))
        finally:
            self.online=False;self.clear_pending()
            if peer is not None:peer.close()
            if self.listener:self.listener.close()
            with self.wake_lock:
                os.close(self.wake_read);os.close(self.wake_write)
                self.wake_read=self.wake_write=None
    def close(self):
        self.stopped.set()
        self.wake()
        if self.thread is not threading.current_thread():self.thread.join(3)
        if self.thread.is_alive():raise RuntimeError('Direct peer transport did not close')


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
