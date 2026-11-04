"""Isolated typed CPU pixel stage; no shared renderer registration or defaults.

Input colors/lights are computed by the existing canonical vertex lighting.
Water uses the ordinary-sum reference; unsupported inputs retain Python.  Full doubles remain mutable
for the unchanged sky/moon overlay; RGB integer packing happens afterwards.
"""
from array import array
import ctypes as ct
import math

D=ct.POINTER(ct.c_double);F=ct.POINTER(ct.c_float);I=ct.POINTER(ct.c_uint32)
B=ct.POINTER(ct.c_uint8)

def _ordinary_sum_supported():return sum((1e16,1.0,-1e16))==0.0


def load(path,mode=0):
    if type(mode) is not int or mode not in (0,1,2):raise ValueError('native pixel mode')
    lib=ct.CDLL(str(path))
    lib.cw_pixels_abi.argtypes=[];lib.cw_pixels_abi.restype=ct.c_uint32
    if lib.cw_pixels_abi()!=3:raise ValueError('pixel ABI')
    lib.cw_pixels_vfp.argtypes=[];lib.cw_pixels_vfp.restype=ct.c_int
    if mode==2 and not lib.cw_pixels_vfp():raise ValueError('VFP unavailable')
    lib._pixel_mode=mode
    lib.cw_pixels_shade.argtypes=[I,F,F,I,D,D,ct.c_size_t,ct.c_size_t,ct.c_size_t,ct.c_size_t,
                                 ct.c_uint32,ct.c_uint32,ct.c_double,D,D,ct.c_int,B,D,D,D,D,ct.c_double,D,ct.c_int]
    lib.cw_pixels_shade.restype=ct.c_int
    lib.cw_pixels_pack.argtypes=[D,I,ct.c_size_t,ct.c_size_t,ct.c_size_t,ct.c_int];lib.cw_pixels_pack.restype=ct.c_int
    return lib


def ptr(a,kind):return (kind._type_*len(a)).from_buffer(a)


class Pixels:
    def __init__(self,lib,values,state=None):self.lib=lib;self.values=values;self.state=state
    def __len__(self):return len(self.values)//3
    def __getitem__(self,index):
        if type(index) is not int:raise TypeError('integer pixel index')
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        return tuple(self.values[index*3:index*3+3])
    def __setitem__(self,index,color):
        if type(index) is not int:raise TypeError('integer pixel index')
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        values=tuple(color)
        if len(values)!=3:raise ValueError('RGB pixel required')
        self.values[index*3:index*3+3]=array('d',values)
    def packed_rgb(self):
        from build_trace import checkpoint
        packed=array('I',[0])*len(self)
        source,destination=ptr(self.values,D),ptr(packed,I)
        for start in range(0,len(self),4096):
            checkpoint()
            count=min(4096,len(self)-start)
            status=self.lib.cw_pixels_pack(source,destination,len(self),start,count,self.lib._pixel_mode)
            if status<0:
                if self.state is not None:self.state['pixel_pack_fallbacks']+=1
                return [(max(0,min(255,int(r)))<<16)|(max(0,min(255,int(g)))<<8)|max(0,min(255,int(b))) for r,g,b in self]
            if self.state is not None:
                self.state['pixel_pack_batches']+=1;self.state['pixel_packed_samples']+=count
        checkpoint()
        return packed


def shade(lib,coverage,colors,lights,env,season,camera=None,state=None):
    mesh,normals,materials,samples,depths,haze,pw,ph,albedos,water=coverage
    if type(pw) is not int or type(ph) is not int or pw<1 or ph<1:raise ValueError('pixel bounds')
    if type(season) is not str or type(env.sunlight) not in (int,float):raise ValueError('plain environment required')
    nv=len(mesh.vertices);ns=pw*ph
    if nv>65536 or ns>470400:
        raise ValueError('pixel bounds')
    if type(water) is not tuple or len(water)!=ns:raise ValueError('water metadata shape')
    has_water=any(value is not None for value in water)
    if has_water and not _ordinary_sum_supported():raise ValueError('water requires ordinary Python sum')
    if has_water and camera is None:raise ValueError('water needs camera')
    if type(colors) not in (list,tuple) or type(lights) not in (list,tuple) or len(colors)!=nv or len(lights)!=nv:
        raise ValueError('vertex RGB shape')
    inputs=[(samples.ids,'I',4,ns*3),(samples.weights,'f',4,ns*2),(haze,'f',4,ns),(albedos.values,'I',4,ns)]
    for value,kind,size,length in inputs:
        if type(value) is not array or value.typecode!=kind or value.itemsize!=size or len(value)!=length:
            raise ValueError('pixel typed buffer shape')
    # Only a few hundred vertex triplets are packed for a Room frame; all
    # per-sample interpolation and RGB packing stays inside the C calls.
    from build_trace import checkpoint
    from geometry import Vec,Camera
    if has_water and type(camera) is not Camera:raise ValueError('canonical camera required')
    def vector(value):
        if type(value) not in (tuple,Vec) or len(value)!=3 or any(type(v) not in (int,float) for v in value):
            raise ValueError('plain XYZ triplet required')
        return value
    mask=array('B',[0])*ns;points=array('d',[0.0])*(ns*3)
    water_counts=[0]*((ns+4095)//4096)
    if has_water:
        for i,point in enumerate(water):
            if i%256==0:checkpoint()
            if point is not None:
                mask[i]=1;points[i*3:i*3+3]=array('d',vector(point))
                if samples.ids[i*3]!=0xffffffff:water_counts[i//4096]+=1
    camera=array('d',vector(camera.origin) if has_water else (0,0,0))
    sun=array('d',vector(env.sun) if has_water else (0,0,0))
    moon=array('d',vector(env.moon) if has_water else (0,0,0))
    moonlight=env.moonlight if has_water else 0.
    if type(moonlight) not in (int,float):raise ValueError('plain moonlight required')
    def pack(rows):
        values=array('d')
        for i,row in enumerate(rows):
            if i%256==0:checkpoint()
            if row is None:values.extend((math.nan,math.nan,math.nan))
            elif type(row) is tuple and len(row)==3 and all(type(v) in (int,float) for v in row):values.extend(row)
            else:raise ValueError('vertex RGB triplet')
        return values
    cs=pack(colors);ls=pack(lights)
    if cs.itemsize!=8 or len(cs)!=nv*3 or len(ls)!=nv*3:raise ValueError('vertex RGB shape')
    if type(env.sky) is not tuple or type(env.haze) is not tuple or any(type(v) not in (int,float) for v in env.sky+env.haze):raise ValueError('plain RGB environment required')
    sky=array('d',env.sky);fog=array('d',env.haze)
    if len(sky)!=3 or len(fog)!=3:raise ValueError('environment RGB shape')
    output=array('d',[0.0])*(ns*3)
    arguments=(ptr(samples.ids,I),ptr(samples.weights,F),ptr(haze,F),ptr(albedos.values,I),ptr(cs,D),ptr(ls,D))
    ep=(ptr(sky,D),ptr(fog,D));op=ptr(output,D)
    wp=(ptr(mask,B),ptr(points,D),ptr(camera,D),ptr(sun,D),ptr(moon,D),moonlight)
    for start in range(0,ns,4096):
        checkpoint()
        status=lib.cw_pixels_shade(*arguments,nv,ns,start,min(4096,ns-start),pw,ph,env.sunlight,*ep,
                                  {'winter':1,'autumn':2,'spring':3}.get(season,0),*wp,op,lib._pixel_mode)
        if status<0:raise ValueError('native pixel input domain')
        if state is not None:
            state['pixel_batches']+=1;state['pixel_samples']+=min(4096,ns-start)
            state['pixel_water_samples']+=water_counts[start//4096]
            state['pixel_backend']='native-vfp' if status==2 else 'native-soft'
    checkpoint()
    return Pixels(lib,output,state)
