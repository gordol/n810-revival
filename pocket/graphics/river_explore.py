"""Touch navigation and a wildlife camera for the river walk."""
import math
import os
from pathlib import Path
import struct
import tempfile
import zlib


def ground_target(camera,u,v,aspect,height,wet):
    """Intersect a touch ray with the same ground used by the walking camera."""
    x,y,z,yaw,pitch=camera
    side=(2*u-1)*.5543*aspect
    up=(1-2*v)*.5543
    ahead=math.cos(pitch)+up*math.sin(pitch)
    dy=up*math.cos(pitch)-math.sin(pitch)
    dx=side*math.cos(yaw)+ahead*math.sin(yaw)
    dz=ahead*math.cos(yaw)-side*math.sin(yaw)
    # Stop at the bank even when the tapped hillside is across the river.
    last=(x,z)
    bank=None
    for i in range(1,193):
        t=i*.4
        px,pz=x+t*dx,z+t*dz
        if max(abs(px),abs(pz))>1000:return None
        if bank is None and wet(px,pz):bank=last
        if y+t*dy<=height(px,pz):return bank or (px,pz)
        last=(px,pz)
    return None


def sighting(camera,u,v,aspect,subjects,height):
    x,y,z,yaw,pitch=camera
    hits=[]
    for key,px,py,pz,size in subjects:
        dx,dy,dz=px-x,py-y,pz-z
        ahead=dx*math.sin(yaw)+dz*math.cos(yaw)
        depth=ahead*math.cos(pitch)-dy*math.sin(pitch)
        if not .2<depth<45 or size/depth<.007:continue
        side=dx*math.cos(yaw)-dz*math.sin(yaw)
        up=dy*math.cos(pitch)+ahead*math.sin(pitch)
        sx=.5+side/(1.1086*aspect*depth)
        sy=.5-up/(1.1086*depth)
        if not (0<=sx<=1 and 0<=sy<=1):continue
        miss=math.hypot((u-sx)*aspect,v-sy)
        if miss>min(.19,max(.039,.54*size/depth)):continue
        samples=max(2,int(depth))
        if any(height(x+dx*j/samples,z+dz*j/samples)>y+dy*j/samples+.08 for j in range(1,samples)):continue
        hits.append((miss,depth,key))
    return min(hits)[2] if hits else None


def save_photo(key,width,height,pixels):
    """Write an RGB PNG atomically in the player's private data directory."""
    from data_paths import rainier_cache
    folder=rainier_cache()/'photos'
    folder.mkdir(parents=True,exist_ok=True)
    def chunk(kind,payload):
        return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload))
    stride=width*3
    rows=b''.join(b'\0'+pixels[i:i+stride] for i in range(0,stride*height,stride))
    header=struct.pack('>2I5B',width,height,8,2,0,0,0)
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',header)+chunk(b'IDAT',zlib.compress(rows,2))+chunk(b'IEND',b'')
    with tempfile.NamedTemporaryFile(dir=folder,prefix=key+'-',suffix='.tmp',delete=False) as output:
        temp=Path(output.name)
        try:
            output.write(data);output.flush()
            final=temp.with_suffix('.png')
            os.replace(temp,final)
        finally:temp.unlink(missing_ok=True)
    return final


def walk_to(owner,target,dt,*,face_path=True):
    dx,dz=target[0]-owner.x,target[1]-owner.z
    distance=math.hypot(dx,dz)
    if distance<.28:return None
    if face_path:
        heading=math.atan2(dx,dz)
        turn=math.remainder(heading-owner.yaw,math.tau)
        owner.yaw+=max(-2.7*dt,min(2.7*dt,turn))
    step=min(distance,dt*3.2)
    owner.x+=step*dx/distance;owner.z+=step*dz/distance
    return target

# Illustrative wildlife stops on the west bank of this mapped reach, in metres.
DIPPER_ROCK=(7.0,37.)
OTTER_POOL=(4.8,70.)


def bank_sign(height,face):
    from geometry import Vec
    x,z=DIPPER_ROCK
    y=height(x,z)
    def ring(scale,lift):
        return [Vec(x+1.3*scale*math.cos(j*math.tau/10),y+lift,
                    z+.78*scale*math.sin(j*math.tau/10)) for j in range(10)]
    bottom,middle,top=ring(1.,-.06),ring(.87,.32),ring(.44,.48)
    for j,p in enumerate(top):
        k=(j+1)%10
        for lo,hi in ((bottom,middle),(middle,top)):
            face(lo[j],hi[j],lo[k],(114,114,98))
            face(hi[j],hi[k],lo[k],(112,110,95))
        face(p,Vec(x,y+.5,z),top[k],(139,136,111))

    # Five toes and a heel in alternating tracks along the gravel margin.
    for j in range(18):
        z=51+j*.77
        x=7.9-.18*(z-51)-8.6+.21*math.cos(j*math.pi)
        for toe in range(-2,4):
            heel=toe==3
            cx=x if heel else x+toe*.029
            cz=z if heel else z+.10-.012*abs(toe)
            r=.067 if heel else .020
            mid=Vec(cx,height(cx,cz)+.026,cz)
            edge=[Vec(cx+r*math.cos(i*math.tau/8),height(cx+r*math.cos(i*math.tau/8),cz+r*math.sin(i*math.tau/8))+.026,
                      cz+r*math.sin(i*math.tau/8)) for i in range(8)]
            for i,p in enumerate(edge):face(mid,p,edge[i-1],(84,73,54))


def photo_paths():
    from data_paths import rainier_cache
    return sorted((rainier_cache()/'photos').glob('*.png'),key=lambda p:p.stat().st_mtime_ns,reverse=True)


def read_photo(path):
    """Decode the RGB/filter-zero format written by the walk."""
    if path.stat().st_size>52*1024*1024:raise ValueError('Oversize photo')
    data=path.read_bytes()
    if data[:16]!=b'\x89PNG\r\n\x1a\n\0\0\0\rIHDR':raise ValueError('Invalid photo')
    w,h,depth,color,_,_,_=struct.unpack_from('>2I5B',data,16)
    if not (0<w<=4096 and 0<h<=4096 and depth==8 and color==2 and data[37:41]==b'IDAT'):
        raise ValueError('Unsupported photo')
    stride=3*w+1
    size=struct.unpack_from('>I',data,33)[0]
    decoder=zlib.decompressobj()
    raw=decoder.decompress(data[41:41+size],h*stride+1)
    if len(raw)!=h*stride or not decoder.eof or any(raw[::stride]):raise ValueError('Damaged photo')
    return w,h,b''.join(raw[i+1:i+stride] for i in range(0,len(raw),stride))
