# SPDX-License-Identifier: MIT
"""Bounded terrain color batches with private output until raster completion."""
from array import array
import ctypes,math,time
D=ctypes.POINTER(ctypes.c_double)
CHUNK=128
def load_library(path):
    lib=ctypes.CDLL(str(path))
    lib.n810_finish_abi.argtypes=[];lib.n810_finish_abi.restype=ctypes.c_uint32
    lib.n810_finish_vfp.argtypes=[];lib.n810_finish_vfp.restype=ctypes.c_int
    if lib.n810_finish_abi()!=1:raise ValueError("unsupported finish ABI")
    lib.n810_ground_color.argtypes=[D,D,ctypes.c_size_t,ctypes.c_int]
    lib.n810_ground_color.restype=ctypes.c_int
    return lib
def compute(mesh,normals,materials,samples,depths,pw,ph,terrain,vec_type,albedos_type,
            checked,checkpoint,lib,state,backend=2,*,haze_strength=.88):
    if not math.isfinite(haze_strength) or haze_strength<0:raise ValueError("invalid haze strength")
    count=pw*ph
    if count>470400 or len(samples)!=count or len(depths)!=count:raise ValueError("finish bounds")
    if len(mesh.vertices)!=len(normals) or len(materials)!=len(normals):raise ValueError("finish metadata")
    checkpoint();start=time.thread_time();wall=time.monotonic()
    state.update(finish_phase="prepare",finish_samples=0,finish_terrain_samples=0,finish_batches=0)
    finite=[d for d in depths if math.isfinite(d)]
    near=min(finite,default=0);span=max(finite,default=1)-near
    haze=array('f',(0 if not math.isfinite(d) else 1-math.exp(-haze_strength*max(0,d-near)/max(span,1e-9)) for d in depths))
    albedos=albedos_type(count);water=[];pending=[];points=array('d')
    vertices=mesh.vertices;meters=terrain.units=="meters"
    def flush():
        if not pending:return
        checkpoint()
        output=array('d',[0.0])*(3*len(pending))
        src=(ctypes.c_double*len(points)).from_buffer(points)
        dst=(ctypes.c_double*len(output)).from_buffer(output)
        status=lib.n810_ground_color(src,dst,len(pending),backend)
        if status!=backend:raise RuntimeError("ground color rejected: "+str(status))
        checkpoint()
        for i,index in enumerate(pending):
            albedos[index]=output[3*i],output[3*i+1],output[3*i+2]
        state["finish_batches"]+=1;state["finish_terrain_samples"]+=len(pending)
        pending.clear();del src;del points[:]
    state["finish_phase"]="samples"
    for index,sample in enumerate(checked(samples,128)):
        if sample is None:water.append(None);state["finish_samples"]=index+1;continue
        a,b,c,w1,w2,w3=sample
        material=materials[a]
        if material=="water" or (material=="terrain" and meters):
            va,vb,vc=vertices[a],vertices[b],vertices[c]
            x=va[0]*w1+vb[0]*w2+vc[0]*w3
            y=va[1]*w1+vb[1]*w2+vc[1]*w3
            z=va[2]*w1+vb[2]*w2+vc[2]*w3
            if material=="water":water.append(vec_type(x,y,z))
            else:
                ny=normals[a][1]*w1+normals[b][1]*w2+normals[c][1]*w3
                points.extend((x,y,z,ny));pending.append(index);water.append(None)
                if len(pending)==CHUNK:flush()
        else:water.append(None)
        state["finish_samples"]=index+1
    flush();checkpoint()
    state.update(finish_phase="complete",finish_wall_seconds=time.monotonic()-wall,
                 finish_thread_cpu_seconds=time.thread_time()-start)
    return haze,albedos,tuple(water)
