"""Touch navigation and a wildlife camera for the river walk."""
import math
import os
from pathlib import Path
import struct
import tempfile
import zlib


def ground_target(camera,u,v,aspect,height,wet,*,bounds=(-1024,1024,-1024,1024),regional=False):
    """Intersect a touch ray with the same ground used by the walking camera."""
    x,y,z,yaw,pitch=camera
    from hike_camera import screen_ray
    dx,dy,dz=screen_ray(u,v,aspect,yaw,pitch)
    # Stop at the bank even when the tapped hillside is across the river.
    last=(x,z)
    bank=None
    t=0.
    while t<100000:
        # Small steps at the hiker's feet, coarser samples for distant slopes.
        t+=max(.4,min(40.,t*.025)) if regional else (.4 if t<80 else 2.)
        px,pz=x+t*dx,z+t*dz
        if not (bounds[0]<=px<=bounds[1] and bounds[2]<=pz<=bounds[3]):return None
        if bank is None and wet(px,pz):bank=last
        if y+t*dy<=height(px,pz):return bank or (px,pz)
        if dx*dx+dz*dz<1e-12 and dy>=0:return None
        last=(px,pz)
    return None


def project_subject(camera,aspect,zoom,subject):
    x,y,z,yaw,pitch=camera
    _,px,py,pz,size=subject
    dx,dy,dz=px-x,py-y,pz-z
    ahead=dx*math.sin(yaw)+dz*math.cos(yaw)
    depth=ahead*math.cos(pitch)-dy*math.sin(pitch)
    if not .2<depth<(55. if zoom<=1 else 230.*zoom) or size*zoom/depth<.004:return None
    side=dx*math.cos(yaw)-dz*math.sin(yaw)
    up=dy*math.cos(pitch)+ahead*math.sin(pitch)
    return .5+zoom*side/(1.1086*aspect*depth),.5-zoom*up/(1.1086*depth),depth


def sighting(camera,u,v,aspect,subjects,height,*,zoom=1.,tracked=None):
    x,y,z=camera[:3]
    hits=[]
    for subject in subjects:
        point=project_subject(camera,aspect,zoom,subject)
        if point is None:continue
        sx,sy,depth=point
        key,px,py,pz,_=subject
        dx,dy,dz=px-x,py-y,pz-z
        if not (0<=sx<=1 and 0<=sy<=1):continue
        # A generous elliptical focus area scales with the screen in portrait.
        miss=math.hypot((u-sx)/.28,(v-sy)/.22)
        if miss>(1.45 if key==tracked else 1.):continue
        samples=max(2,int(depth))
        if any(height(x+dx*j/samples,z+dz*j/samples)>y+dy*j/samples+.08 for j in range(1,samples)):continue
        hits.append((miss-(.55 if key==tracked else 0.),depth,key))
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


def walk_to(owner,target,dt,*,face_path=True,speed=3.2):
    dx,dz=target[0]-owner.x,target[1]-owner.z
    distance=math.hypot(dx,dz)
    if distance<.28:return None
    if face_path:
        heading=math.atan2(dx,dz)
        turn=math.remainder(heading-owner.yaw,math.tau)
        owner.yaw+=max(-2.7*dt,min(2.7*dt,turn))
    step=min(distance,dt*speed)
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
