"""Incremental UV-PRO KISS/vendor receive parsing; never transmits."""
import collections
import importlib.util
from pathlib import Path
import time
spec = importlib.util.spec_from_file_location('packet_monitor', Path(__file__).with_name('n810-packet-monitor.py'))
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)
COMMANDS = {1:'GET_DEV_ID',4:'GET_DEV_INFO',6:'REGISTER_NOTIFICATION',9:'EVENT_NOTIFICATION',10:'READ_SETTINGS',11:'WRITE_SETTINGS',12:'STORE_SETTINGS',13:'READ_RF_CH',14:'WRITE_RF_CH',20:'GET_HT_STATUS',22:'GET_VOLUME',23:'SET_VOLUME',29:'READ_ADVANCED_SETTINGS',30:'WRITE_ADVANCED_SETTINGS',31:'HT_SEND_DATA',33:'READ_BSS_SETTINGS',34:'WRITE_BSS_SETTINGS',51:'SET_PHONE_STATUS',57:'RX_DATA',58:'WRITE_REGION_CH',59:'WRITE_REGION_NAME',60:'SET_REGION',63:'READ_ADVANCED_SETTINGS2',64:'WRITE_ADVANCED_SETTINGS2',70:'SET_TIME',73:'READ_REGION_NAME',76:'GET_POSITION'}
LIMIT=65536

class Observer:
    def __init__(self, packet=lambda text: None, command=lambda text: None,
                 frame=lambda frame,origin,wire:None, clock=time.monotonic):
        self.packet,self.command,self.frame,self.clock=packet,command,frame,clock
        self.buffer=bytearray();self.fragments=[];self.wire=[];self.fragment_time=0
        self.recent=collections.deque(maxlen=256)

    def emit(self,frame,origin,wire):
        now=self.clock()
        while self.recent and now-self.recent[0][2]>2:self.recent.popleft()
        # Match one opposite-format copy; preserve repeated receptions in one format.
        if frame and frame[0]==0:
            for old in self.recent:
                if old[0]==frame and old[1]!=origin:
                    self.recent.remove(old);return
            self.recent.append((frame,origin,now))
        self.frame(frame,origin,wire)
        text=monitor.describe(frame)
        if text and not text.startswith(('Malformed ', 'Short ')):self.packet(text)

    def vendor(self,frame):
        group=int.from_bytes(frame[4:6],'big');word=int.from_bytes(frame[6:8],'big')
        reply,command=bool(word&0x8000),word&0x7fff
        payload=frame[8:8+frame[3]]
        name=COMMANDS.get(command,str(command)) if group==2 else str(command)
        self.command('group=%d %s%s payload=%s'%(group,name,' reply' if reply else '',payload.hex()))
        if group!=2 or reply:return
        if command==9 and payload[:1]==b'\2':payload=payload[1:]
        elif command!=57:return
        if not payload:return
        flag=payload[0];part=flag&63;now=self.clock()
        if part==0 or now-self.fragment_time>5:self.fragments=[];self.wire=[]
        if part!=len(self.fragments):self.fragments=[];self.wire=[];return
        if flag&64 and len(payload)<2:self.fragments=[];self.wire=[];return
        self.fragments.append(payload[1:-1] if flag&64 else payload[1:]);self.wire.append(frame)
        self.fragment_time=now
        if flag&128:
            packet=b'\0'+b''.join(self.fragments);wire=self.wire
            self.fragments=[];self.wire=[]
            text=monitor.describe(packet)
            if text and not text.startswith(('Malformed ', 'Short ')):
                self.emit(packet,'vendor_reassembled',wire)

    def kiss(self,encoded):
        result=bytearray();escaped=False
        for byte in encoded:
            if escaped:
                if byte not in (220,221):return
                result.append(192 if byte==220 else 219);escaped=False
            elif byte==219:escaped=True
            else:result.append(byte)
        if escaped or not result or len(result)>LIMIT:return
        self.emit(bytes(result),'kiss',[])

    def feed(self,data):
        self.buffer.extend(data)
        while self.buffer:
            b=self.buffer
            if b[0]==192:
                if len(b)<2:return
                if b[1]==192:del b[0];continue
                # An orphan KISS command can precede a complete vendor notification.
                # FF 01 cannot begin a shifted AX.25 destination address.
                if b[1]==0:
                    if len(b)<4 and b[2:3]==b'\xff':return
                    if b[2:4]==b'\xff\1':del b[:2];continue
                if b[1]==255:del b[0];continue
                end=b.find(192,1)
                if end<0:
                    if len(b)>2*LIMIT+1: b.clear()
                    return
                encoded=bytes(b[1:end]);del b[:end]  # Keep shared closing/opening delimiter.
                if len(encoded)<=2*LIMIT:self.kiss(encoded)
            elif b[0]==255:
                if len(b)<2:return
                if b[1]!=1:del b[0];continue
                if len(b)<8:return
                if b[2]&~1:del b[0];continue
                size=8+b[3]+(b[2]&1)
                if len(b)<size:return
                frame=bytes(b[:size]);del b[:size];self.vendor(frame)
            else:del b[0]
