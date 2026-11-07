"""Bin an actual Mesa frame into full-resolution 32x32 MBX jobs.

No pixel rasterization occurs here. Clipping preserves window depth and
perspective color interpolation; every framebuffer tile is emitted, including
empty background. The kernel owns all hardware addresses and command words.
"""
import math, struct
import hashlib
from read_frame import read_frame

JOB_HEADER=struct.Struct('<6I')
PRIMITIVE=struct.Struct('<4I15I')

def pack_jobs(data):
    packed=list(jobs(data))
    return struct.pack('<II32s',0x3150424d,len(packed),hashlib.sha256(data).digest())+b''.join(
        struct.pack('<5I',x,y,w,h,len(job))+job for x,y,w,h,job in packed)

def unpack_jobs(data,frame):
    if len(data)<40:raise ValueError('Short prepared job header')
    magic,count,pin=struct.unpack_from('<II32s',data)
    h,_=read_frame(frame)
    if magic!=0x3150424d or pin!=hashlib.sha256(frame).digest() or count!=((h[4]+31)//32)*((h[5]+31)//32):
        raise ValueError('Prepared jobs do not match application frame')
    offset=40;result=[]
    for oy in range(0,h[5],32):
        for ox in range(0,h[4],32):
            if offset+20>len(data):raise ValueError('Truncated job record')
            x,y,w,height,n=struct.unpack_from('<5I',data,offset);offset+=20
            if (x,y,w,height)!=(ox,oy,min(32,h[4]-ox),min(32,h[5]-oy)) or n<24 or n>24+256*76 or offset+n>len(data):
                raise ValueError('Invalid prepared job record')
            job=data[offset:offset+n];offset+=n
            j=JOB_HEADER.unpack_from(job)
            if j[:2]!=(0x314a424d,1) or j[2]*76+24!=n or j[3:6]!=(w,height,0):raise ValueError('Invalid job ABI')
            result.append((x,y,w,height,job))
    if offset!=len(data):raise ValueError('Trailing prepared job data')
    return result

def clip_polygon(vertices, axis, bound, keep_greater, perspective):
    result=[]
    previous=vertices[-1]
    p_in=(previous[axis]>=bound) if keep_greater else (previous[axis]<=bound)
    for current in vertices:
        c_in=(current[axis]>=bound) if keep_greater else (current[axis]<=bound)
        if c_in != p_in:
            t=(bound-previous[axis])/(current[axis]-previous[axis])
            v=[previous[i]+t*(current[i]-previous[i]) for i in range(8)]
            v[axis]=bound
            result.append(v)
        if c_in: result.append(current)
        previous,p_in=current,c_in
    return result

def bits(v): return struct.unpack('<I',struct.pack('<f',v))[0]
def pack_color(v):
    # Matches N95 normal RGBA packing, without the fog-only half-alpha.
    c=[min(255,max(0,int(x*255+.5))) for x in v]
    return c[0]|c[1]<<8|c[2]<<16|c[3]<<24

def jobs(data):
    h,triangles=read_frame(data)
    width,height=h[4:6]
    if h[12:16]!=(0.,0.,0.,0.) or h[16]!=1.0:
        raise ValueError('Initial backend requires black clear and depth1')
    # Reject unsupported states before yielding any job.
    for t in triangles:
        if t[0:3]!=(1,1,1) or t[3] not in (1,3) or t[4:8]!=(0,15,1,0):
            raise ValueError('Unsupported Mesa state: '+repr(t[:8]))
        if t[8:12]!=(0,0,width,height):raise ValueError('Unsupported application scissor')
    for oy in range(0,height,32):
        for ox in range(0,width,32):
            tw,th=min(32,width-ox),min(32,height-oy)
            primitives=[]
            for t in triangles:
                vertices=[list(t[12+i*8:20+i*8]) for i in range(3)]
                if max(v[0] for v in vertices)<ox or min(v[0] for v in vertices)>ox+tw or \
                   max(v[1] for v in vertices)<oy or min(v[1] for v in vertices)>oy+th:continue
                perspective=t[3]==3
                if perspective:
                    for v in vertices:
                        if v[3]<=0:raise ValueError('Nonpositive reciprocal W')
                        v[4:8]=[x*v[3] for x in v[4:8]]
                for axis,bound,greater in ((0,ox,True),(0,ox+tw,False),(1,oy,True),(1,oy+th,False)):
                    if not vertices:break
                    vertices=clip_polygon(vertices,axis,bound,greater,perspective)
                for i in range(1,len(vertices)-1):
                    tri=[vertices[0],vertices[i],vertices[i+1]]
                    area=(tri[1][0]-tri[0][0])*(tri[2][1]-tri[0][1])-(tri[1][1]-tri[0][1])*(tri[2][0]-tri[0][0])
                    if abs(area)<1e-8:continue
                    words=[t[0],t[1],t[2],int(perspective)]
                    for v in tri:
                        color=[x/v[3] for x in v[4:8]] if perspective else v[4:8]
                        words.extend([bits(max(0.,min(32.,v[0]-ox))),bits(max(0.,min(32.,v[1]-oy))),bits(v[2]),bits(v[3]),pack_color(color)])
                    primitives.append(PRIMITIVE.pack(*words))
            if len(primitives)>256:raise ValueError('Tile exceeds bounded GPU scene capacity')
            yield ox,oy,tw,th,JOB_HEADER.pack(0x314a424d,1,len(primitives),tw,th,0)+b''.join(primitives)

if __name__=='__main__':
    import sys,json
    from pathlib import Path
    packed=list(jobs(Path(sys.argv[1]).read_bytes()))
    print(json.dumps(dict(tiles=len(packed),max_triangles=max((len(x[4])-JOB_HEADER.size)//PRIMITIVE.size for x in packed),
                         bytes=sum(len(x[4]) for x in packed),cpu_rasterization=False,hardware_verified=False),indent=2))


def whole_frame_job(data):
    h,triangles=read_frame(data)
    width,height=h[4:6]
    if not (0<width<=512 and 0<height<=512 and width%2==0 and len(triangles)<=512):
        raise ValueError('Whole frame capacity exceeded')
    if h[12:16]!=(0.,0.,0.,0.) or h[16]!=1.0:
        raise ValueError('Unsupported clear')
    primitives=[]
    for t in triangles:
        if t[:3]!=(1,1,1) or t[3] not in (1,3) or t[4:12]!=(0,15,1,0,0,0,width,height):
            raise ValueError('Unsupported Mesa state')
        words=[1,1,1,int(t[3]==3)]
        for i in range(3):
            v=t[12+i*8:20+i*8]
            words.extend([bits(x) for x in v[:4]]+[pack_color(v[4:8])])
        primitives.append(PRIMITIVE.pack(*words))
    return [(0,0,width,height,JOB_HEADER.pack(0x314a424d,2,len(primitives),width,height,0)+b''.join(primitives))]
