"""Configured microReticulum control and execution connection."""
import os
from pathlib import Path
import re
import select
import time
import threading
from wire import codec,NATIVE_CODEC

MODES=('auto','disabled','external-only')

def endpoint(value):
    if not isinstance(value,str):raise ValueError('Choose the external node connection')
    if value.startswith('unix:///') and len(value[7:].encode())<=100:return value
    match=re.fullmatch(r'rfcomm://((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})/([0-9]{1,2})',value)
    if match and 1<=int(match[2])<=30:return 'rfcomm://'+match[1].upper()+'/'+str(int(match[2]))
    if re.fullmatch(r'/dev/(?:cu\.[A-Za-z0-9_.-]+|tty[A-Za-z0-9_.-]+|pts/[0-9]+)',value):return value
    raise ValueError('Use /dev/serial-device or rfcomm://aa:bb:cc:dd:ee:ff/1')

def pack(value):return codec.packb(value,use_bin_type=True) if NATIVE_CODEC else codec.packb(value)
def unpack(raw):return codec.unpackb(raw,raw=False,strict_map_key=False) if NATIVE_CODEC else codec.unpackb(raw)

class Connection:
    def __init__(self,address):
        self.address=endpoint(address);self.sock=None;self.fd=None;self.original=None;self.rpc=None;self.local=None;self.fragment_size=0;self.guard=threading.Lock()
    def __enter__(self):
        if self.address.startswith('unix://'):
            from node_transport import SocketTransport
            self.local=SocketTransport(Path(self.address[7:]));return self
        if self.address.startswith('rfcomm://'):
            import socket
            if not hasattr(socket,'AF_BLUETOOTH'):raise ValueError('Classic RFCOMM is unavailable on this host; use USB')
            host,channel=self.address[9:].split('/')
            self.sock=socket.socket(socket.AF_BLUETOOTH,socket.SOCK_STREAM,socket.BTPROTO_RFCOMM)
            try:
                self.sock.setsockopt(getattr(socket,'SOL_BLUETOOTH',274),getattr(socket,'BT_SECURITY',4),bytes([2,0]))
                self.sock.settimeout(12);self.sock.connect((host,int(channel)))
            except BaseException:self.sock.close();raise
            self.fd=self.sock.fileno()
        else:
            import fcntl,termios,tty
            self.fd=os.open(self.address,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK)
            try:
                fcntl.flock(self.fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                fcntl.ioctl(self.fd,termios.TIOCEXCL)
                self.original=termios.tcgetattr(self.fd);tty.setraw(self.fd)
                attrs=termios.tcgetattr(self.fd);attrs[4]=attrs[5]=termios.B115200
                termios.tcsetattr(self.fd,termios.TCSANOW,attrs)
            except BaseException:self.__exit__(None,None,None);raise
        return self
    def __exit__(self,*args):
        with self.guard:
            if self.local:self.local.close();self.local=None
            if self.rpc:self.rpc.close();self.rpc=None
            if self.sock:self.sock.close()
            elif self.fd is not None:
                import termios
                try:
                    if self.original:termios.tcsetattr(self.fd,termios.TCSANOW,self.original)
                    termios.tcflush(self.fd,termios.TCIFLUSH)
                    if hasattr(termios,'TIOCNXCL'):__import__('fcntl').ioctl(self.fd,termios.TIOCNXCL)
                finally:os.close(self.fd)
            self.fd=None
    def owner_transport(self):
        with self.guard:
            if self.local:
                from node_transport import SocketTransport
                return SocketTransport(Path(self.address[7:]))
            from node_transport import Port,Transport
            if self.fd is None:raise ConnectionError('Node connection is closed')
            if self.rpc is None:self.rpc=Port(self)
            return Transport(self.rpc)

    def query(self,operation,sequence,payload):
        with self.guard:
            rpc=self.rpc
            if rpc is None:return self.raw_query(operation,sequence,payload)
        return rpc.query(operation,payload)

    def raw_query(self,operation,sequence,payload):
        from native_radio import Frames
        raw=pack([operation,sequence,payload]);frame=b'\xc0\x86'+raw.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc')+b'\xc0'
        deadline=time.monotonic()+4
        while frame:
            remaining=deadline-time.monotonic()
            if remaining<=0 or not select.select([],[self.fd],[],remaining)[1]:raise TimeoutError('Node write timed out')
            n=os.write(self.fd,frame)
            if n<=0:raise ConnectionError('Node disconnected')
            frame=frame[n:]
        decoder=Frames(192,219,limit=32768)
        while time.monotonic()<deadline:
            if not select.select([self.fd],[],[],max(0,deadline-time.monotonic()))[0]:break
            data=os.read(self.fd,4096)
            if not data:raise ConnectionError('Node disconnected')
            for frame in decoder.feed(data):
                if frame[0]!=0x87:continue
                value=unpack(frame[1:])
                if not isinstance(value,list) or len(value)!=3 or value[1]!=sequence:continue
                if value[0]!=operation:raise ValueError('Node rejected the provisioning query')
                return value[2]
        raise TimeoutError('Node did not answer the provisioning query')

def probe(address,connection=Connection):
    if address.startswith('unix://'):
        from node_transport import SocketTransport
        from native_rpc import checked_info
        value=SocketTransport(Path(address[7:])).exchange(dict(version=1,action='node_info'))
        info=checked_info(value,ready=False);reason=None
        try:checked_info(info)
        except ValueError as error:reason=str(error)
        if not info.get('available',True):reason='External executor is in use by another device'
        return dict(state='online',observed_at=time.time(),endpoint=address,firmware='microReticulum',identity=info['identity'],offload_ready=reason is None,offload=info,radio=info.get('radio',{}),reason=reason)
    with connection(address) as client:
        info=client.query(2,1,None)
        if not isinstance(info,dict) or info.get(1)!='microReticulum' or info.get(2)!=2:raise ValueError('Unsupported external node firmware/schema')
        state=client.query(4,2,{1:[1,107,105]})
        offload=info.get(128);reason='Board provisioning is available; link and application endpoint delegation is not exposed by this firmware interface'
        ready=False
        if offload:
            from native_rpc import checked_info
            try:
                checked_info(offload,ready=False)
                if offload['identity']!=state[1][107][1].hex():raise ValueError('Offload identity differs from node identity')
                client.fragment_size=offload['fragment_size'] if offload.get('framing')=='kiss-fragment-v1' else 0
                if client.rpc and client.rpc.fragment_size!=client.fragment_size:raise ValueError('Node framing changed; reconnect required')
                checked_info(offload);ready=offload.get('available',True)
                reason=None if ready else 'External executor is in use by another device'
            except ValueError as error:reason=str(error)
    values=state[1];identity=values[107][1]
    if not isinstance(identity,bytes) or len(identity)!=16:raise ValueError('Invalid external node identity')
    # Schema 2 provisioning supplies configuration/metrics, not a host endpoint API.
    # Do not mistake a standalone transport router for delegated application endpoints.
    return dict(state='online',observed_at=time.time(),endpoint=endpoint(address),firmware=info[1],schema=info[2],identity=identity.hex(),
        standalone=values[1].get(1) is True,remote_management=values[1].get(3) is True,
        radio={name:values.get(105,{}).get(key) for key,name in enumerate(('frequency','bandwidth','spreadingfactor','codingrate','txpower'),1)},offload_ready=ready,offload=offload,reason=reason)

def selection(mode,node):
    if mode not in MODES:raise ValueError('Choose Auto, Disabled or External only')
    if mode=='disabled':return 'local'
    if node.get('offload_ready') and node.get('state')=='online':return 'external'
    if mode=='external-only':raise ValueError(node.get('reason') or node.get('error') or 'External node is unavailable; local fallback is disabled')
    return 'local'


def load(path):
    import stat
    if not os.path.lexists(path):return dict(mode='auto',endpoint='')
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>1024:raise ValueError('Unsafe external node preferences')
    value=unpack(path.read_bytes())
    if not isinstance(value,dict) or not {'mode','endpoint'}<=set(value) or bool(set(value)-{'mode','endpoint','node_identity'}) or value['mode'] not in MODES or not isinstance(value['endpoint'],str):raise ValueError('Invalid external node preferences')
    pin=value.get('node_identity')
    if pin is not None and (not isinstance(pin,str) or len(pin)!=32 or any(c not in '0123456789abcdef' for c in pin)):raise ValueError('Invalid node identity pin')
    if value['endpoint']:value['endpoint']=endpoint(value['endpoint'])
    return value

def save(path,value):
    import tempfile
    fd,name=tempfile.mkstemp(prefix='.node-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(pack(value));stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
