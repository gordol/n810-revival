"""Optional nonblocking Linux single-stylus input. Never imported without opt-in."""
import fcntl
import json
import math
import os
import struct
from touch import Stylus
from touch_diagnostics import TouchDiagnostics
from pointer_events import TouchReport, PointerEvent, evdev_stamp, coalesce_motion

EV_SYN,EV_KEY,EV_ABS=0,1,3
SYN_REPORT,SYN_DROPPED=0,3
ABS_X,ABS_Y,BTN_TOUCH=0,1,330
CANCEL=('touch_cancel',)


def ioctl_read(fd,number,size):
    value=bytearray(size)
    fcntl.ioctl(fd,(2<<30)|(size<<16)|(ord('E')<<8)|number,value,True)
    return value


def inspect_device(fd):
    name=bytes(ioctl_read(fd,0x06,256)).split(b'\0',1)[0].decode('utf-8','replace')
    identity=list(struct.unpack('=4H',ioctl_read(fd,0x02,8)))
    try:physical=bytes(ioctl_read(fd,0x07,256)).split(b'\0',1)[0].decode('utf-8','replace')
    except OSError:physical=''
    axes=[struct.unpack('=6i',ioctl_read(fd,0x40+axis,24)) for axis in (ABS_X,ABS_Y)]
    keys=ioctl_read(fd,0x18,96)
    capabilities=ioctl_read(fd,0x21,96)
    if not capabilities[BTN_TOUCH//8]&(1<<(BTN_TOUCH%8)):
        raise ValueError('device has no single-stylus BTN_TOUCH')
    for axis in axes:
        if axis[2]<=axis[1]:raise ValueError('invalid absolute axis range')
    device=dict(name=name,id=identity,physical=physical,x_range=list(axes[0][1:3]),y_range=list(axes[1][1:3]))
    return device,(axes[0][0],axes[1][0],bool(keys[BTN_TOUCH//8]&(1<<(BTN_TOUCH%8))))


class EventCodec:
    def __init__(self,word_bytes=None):
        self.format=struct.Struct('@llHHi' if word_bytes is None else '=iiHHi' if word_bytes==4 else '=qqHHi' if word_bytes==8 else '')
        if self.format.size not in (16,24):raise ValueError('unsupported input_event ABI')
    def pack(self,kind,code,value):return self.format.pack(0,0,kind,code,value)


class EventReader:
    """One owned fd, bounded read. SYN loss cancels and waits for a fresh contact."""
    def __init__(self,path=None,*,fd=None,query=inspect_device,codec=None,per_record_diagnostics=False,native=None):
        self.fd=None;self.pump=None;self.native=native;self.native_reads=0;self.native_overflows=0;self.query=query;self.codec=codec or EventCodec();self.buffer=b''
        self.dropping=False;self.drop_count=0;self._diagnostics=TouchDiagnostics(per_record=per_record_diagnostics);self.clock_id=f'evdev-default-{id(self)}'
        try:
            self.fd=os.open(os.fspath(path),os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC) if fd is None else os.dup(fd)
            os.set_blocking(self.fd,False)
            self.device,state=query(self.fd);self.x,self.y,self.pressed=state
            self.armed=not self.pressed
            if native is not None:self.pump=native.input_start(self.fd,self.codec.format.size)
        except BaseException:
            self.close();raise
    def fileno(self):
        if self.fd is None:raise ValueError('touch fd is closed')
        return self.native.input_fileno(self.pump) if self.pump is not None else self.fd
    def close(self):
        if self.pump is not None:
            self.native.input_close(self.pump);self.pump=None
        if self.fd is not None:
            fd,self.fd=self.fd,None
            try:os.close(fd)
            except OSError:pass
    def diagnostics(self,mapper_down=None):
        value=self._diagnostics.snapshot(self,mapper_down)
        value.update(reader="native-buffered" if self.pump is not None else "python",native_reads=self.native_reads,native_overflows=self.native_overflows)
        return value
    def suppress_until_release(self):
        if self.pump is not None:
            device,state=self.query(self.fd)
            if device!=self.device:raise OSError('touch identity changed during cancellation')
            self.x,self.y,self.pressed=state
            self.native.input_discard(self.pump)
            self.buffer=b'';self.dropping=False
        self.armed=not self.pressed
    def drain(self):
        if self.fd is None:raise OSError('touch fd is closed')
        self._diagnostics.begin();self._diagnostics.bump('read_calls')
        if self.pump is not None:
            raw,losses,self.native_reads=self.native.input_read(self.pump)
            if losses:
                self.native_overflows+=losses
                raw=self.codec.pack(EV_SYN,SYN_DROPPED,0)+raw
            if not raw:return []
        else:
            try:raw=os.read(self.fd,self.codec.format.size*256)
            except BlockingIOError:return []
            if not raw:raise OSError('touch device disconnected')
        self._diagnostics.bump('bytes',len(raw))
        self.buffer+=raw;result=[];size=self.codec.format.size;position=0
        while len(self.buffer)-position>=size:
            seconds,microseconds,kind,code,value=self.codec.format.unpack_from(self.buffer,position);position+=size
            self._diagnostics.record(seconds,microseconds,kind,code,value)
            if kind==EV_SYN and code==SYN_DROPPED:
                self._diagnostics.bump('syn_dropped');self._diagnostics.bump('cancel_events')
                result.append(CANCEL);self.dropping=True;self.drop_count+=1;continue
            if self.dropping:
                if kind==EV_SYN and code==SYN_REPORT:
                    device,state=self.query(self.fd)
                    if device!=self.device:raise OSError('touch identity changed during resync')
                    self.x,self.y,self.pressed=state;self.armed=not self.pressed;self.dropping=False
                    self._diagnostics.bump('resyncs')
                    if self.pump is not None:
                        self.native.input_discard(self.pump)
                        self.armed=False
                    self._diagnostics.bump('discarded_records',(len(self.buffer)-position)//size)
                    # Query sees current kernel state; discard the remaining old batch.
                    position=len(self.buffer);break
                continue
            if kind==EV_ABS:
                if code==ABS_X:self.x=value
                elif code==ABS_Y:self.y=value
            elif kind==EV_KEY and code==BTN_TOUCH:self.pressed=bool(value)
            elif kind==EV_SYN and code==SYN_REPORT:
                if not self.armed:
                    self._diagnostics.bump('suppressed_reports')
                    if not self.pressed:self.armed=True
                    continue
                result.append(TouchReport(self.x,self.y,self.pressed,stamp=evdev_stamp(seconds,microseconds,self.clock_id)))
                self._diagnostics.bump('emitted_reports')
        self.buffer=self.buffer[position:]
        return result


def display(width,height,rotation=0):
    if not isinstance(width,int) or not isinstance(height,int) or width<1 or height<1 or rotation not in (0,90,180,270):
        raise ValueError('invalid physical display geometry')
    return dict(width=width,height=height,rotation=rotation)


def solve(matrix,values):
    a=[list(row)+[value] for row,value in zip(matrix,values)]
    for column in range(3):
        pivot=max(range(column,3),key=lambda row:abs(a[row][column]))
        if abs(a[pivot][column])<1e-10:raise ValueError('calibration points do not span the screen')
        a[column],a[pivot]=a[pivot],a[column]
        divisor=a[column][column];a[column]=[v/divisor for v in a[column]]
        for row in range(3):
            if row!=column:
                amount=a[row][column];a[row]=[v-amount*p for v,p in zip(a[row],a[column])]
    return [a[row][3] for row in range(3)]


class Calibration:
    def __init__(self,profile,device,geometry):
        if not isinstance(profile,dict):raise ValueError('invalid calibration profile')
        if profile.get('version')!=1 or profile.get('device')!=device or profile.get('display')!=geometry:
            raise ValueError('calibration does not match this touch device/display')
        coefficients=profile.get('matrix',[])
        if not isinstance(coefficients,(list,tuple)) or len(coefficients)!=6 or not all(isinstance(v,(int,float)) and math.isfinite(v) and abs(v)<100 for v in coefficients):
            raise ValueError('invalid calibration transform')
        a,b,_,d,e,_=coefficients
        if abs(a*e-b*d)<1e-6:raise ValueError('singular calibration transform')
        for axis in ('x_range','y_range'):
            bounds=device.get(axis,[])
            if len(bounds)!=2 or bounds[1]<=bounds[0]:raise ValueError('invalid device axis range')
        self.profile=profile;self.device=device;self.matrix=tuple(coefficients)
    @classmethod
    def load(cls,path,device,geometry):
        with open(os.path.expanduser(os.fspath(path)),'rb') as stream:raw=stream.read(65537)
        if len(raw)>65536:raise ValueError('calibration profile too large')
        profile=json.loads(raw)
        if not isinstance(profile,dict):raise ValueError('invalid calibration profile')
        return cls(profile,device,geometry)
    def normalized(self,x,y):
        xmin,xmax=self.device['x_range'];ymin,ymax=self.device['y_range']
        x=(x-xmin)/(xmax-xmin);y=(y-ymin)/(ymax-ymin)
        a,b,c,d,e,f=self.matrix
        return a*x+b*y+c,d*x+e*y+f
    def cell(self,x,y,columns,rows):
        if columns<1 or rows<1:raise ValueError('invalid cell geometry')
        u,v=self.normalized(x,y)
        return max(0,min(columns-1,int(u*columns))),max(0,min(rows-1,int(v*rows)))
    @classmethod
    def fit(cls,device,geometry,samples):
        if len(samples)!=5:raise ValueError('five calibration targets are required')
        xmin,xmax=device['x_range'];ymin,ymax=device['y_range']
        if xmax<=xmin or ymax<=ymin:raise ValueError('invalid device axis range')
        points=[((x-xmin)/(xmax-xmin),(y-ymin)/(ymax-ymin),1.) for (x,y),_ in samples]
        normal=[[sum(p[i]*p[j] for p in points) for j in range(3)] for i in range(3)]
        xvalues=[sum(p[i]*target[0] for p,(_,target) in zip(points,samples)) for i in range(3)]
        yvalues=[sum(p[i]*target[1] for p,(_,target) in zip(points,samples)) for i in range(3)]
        profile=dict(version=1,device=device,display=geometry,matrix=solve(normal,xvalues)+solve(normal,yvalues),samples=[dict(raw=list(raw),target=list(target)) for raw,target in samples])
        calibration=cls(profile,device,geometry)
        errors=[]
        for (x,y),(u,v) in samples:
            actual_u,actual_v=calibration.normalized(x,y)
            errors.append(math.hypot((actual_u-u)*geometry['width'],(actual_v-v)*geometry['height']))
        if not all(math.isfinite(v) for v in errors) or max(errors)>max(12,min(geometry['width'],geometry['height'])*.025):
            raise ValueError('calibration missed the targets; please retry')
        profile['error_pixels']=errors
        return calibration


class TouchSource:
    def __init__(self,path,profile,geometry,columns,rows,*,reader_factory=EventReader):
        self.reader=reader_factory(path);self.captured=False
        try:
            self.calibration=Calibration.load(profile,self.reader.device,geometry)
            self.resize(columns,rows)
        except BaseException:self.reader.close();raise
    def fileno(self):return self.reader.fileno()
    def close(self):self.reader.close()
    def resize(self,columns,rows):
        self.mapper=Stylus(self.reader.device['x_range'],self.reader.device['y_range'],columns,rows,project=lambda x,y:self.calibration.cell(x,y,columns,rows))
        self.reader.suppress_until_release()
    def drain(self):
        output=[]
        for report in self.reader.drain():
            if report==CANCEL:
                self.mapper.down=False;output.append(CANCEL);continue
            event=self.mapper.report(*report)
            if event is None:continue
            event=PointerEvent(event,stamp=getattr(report,'stamp',None))
            merged=coalesce_motion(output[-1],event) if output and output[-1]!=CANCEL else None
            if merged is not None:
                observer=getattr(self.reader,'_diagnostics',None)
                if observer is not None:observer.bump('coalesced_moves')
                output[-1]=merged
            else:output.append(event)
        observer=getattr(self.reader,'_diagnostics',None)
        if observer is not None:observer.mapped(output)
        return output
    def cancel(self,host):
        if self.captured:
            host.finish(False);host.pointer_origin=None
        self.captured=False;self.mapper.down=False
    def diagnostics(self):return self.reader.diagnostics(self.mapper.down)
    def dispatch(self,events,host,click):
        for event in events:
            if event==CANCEL:self.cancel(host);continue
            _,button,x,y,released=event;x-=host.origin[0];y-=host.origin[1]
            if button==0 and not released:
                self.captured=0<=x<host.width and 0<=y<host.height
            if not self.captured:continue
            host.pointer(button,x,y,released)
            if button==0 and not released:click(x,y)
            if released:self.captured=False
