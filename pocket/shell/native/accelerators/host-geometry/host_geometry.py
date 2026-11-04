# SPDX-License-Identifier: MIT
"""Optional host stage adapter. No engine hooks, raster replacement or eager NumPy."""
from array import array
import ctypes as ct
import math
import time

D=ct.POINTER(ct.c_double);I=ct.POINTER(ct.c_uint32);F=ct.POINTER(ct.c_float)
MAX_BYTES=128*1024*1024
MAX_VERTICES=2097152;MAX_TRIANGLES=4194304;MAX_SAMPLES=2097152
CHUNK=256;COLOR_CHUNK=128
_numpy=None

def _np():
    global _numpy
    if _numpy is None:import numpy;_numpy=numpy
    return _numpy

def capabilities():
    return dict(backend='native-c',mode=1,project=False,depth=False,normals=True,
                normal_accumulation='native-c',normal_normalization='python-reference',
                coverage=True,finish=True,albedo=True,normalization_uses_canonical_sum=True,
                requires_ordinary_sum=False,
                max_vertices=MAX_VERTICES,max_triangles=MAX_TRIANGLES,max_samples=MAX_SAMPLES,
                max_owned_buffer_bytes=MAX_BYTES,normal_chunk=CHUNK,color_chunk=COLOR_CHUNK,
                coverage_triangle_chunk=64,coverage_pixel_chunk=4096,numpy_required_for_host_optin=True)

def load_library(path):
    lib=ct.CDLL(str(path))
    lib.cold_geometry_abi.argtypes=[];lib.cold_geometry_abi.restype=ct.c_uint32
    if lib.cold_geometry_abi()!=1:raise ValueError('host geometry ABI mismatch')
    lib.cold_normals.argtypes=[D,I,D,ct.c_size_t];lib.cold_normals.restype=None
    lib.cold_materials.argtypes=[I,I,I,ct.c_size_t];lib.cold_materials.restype=None
    lib.cold_colors.argtypes=[D,D,ct.c_size_t];lib.cold_colors.restype=None
    lib.cold_coverage.argtypes=[D,I,F,I,F,D,ct.c_size_t,ct.c_size_t,ct.c_size_t,ct.c_int,ct.c_size_t,ct.c_size_t]
    lib.cold_coverage.restype=ct.c_int
    return lib

def _ptr(a,t):return a.ctypes.data_as(t)

def _budget(nv,nt,ns=0):
    if not 0<=nv<=MAX_VERTICES or not 0<=nt<=MAX_TRIANGLES or not 0<=ns<=MAX_SAMPLES:raise ValueError('host geometry limits')
    if nv*104+nt*16+ns*64>MAX_BYTES:raise ValueError('host geometry buffer budget')

def _mode(backend):
    if backend!=1:raise ValueError('host backend mode must be native-c (1)')

def _pack_vertices(mesh,vec_type,checked,checkpoint):
    np=_np();out=np.empty((len(mesh.vertices),3),dtype=np.float64);integers=set()
    for i,point in enumerate(checked(mesh.vertices)):
        if type(point) is not vec_type:raise ValueError('host vertex type')
        for axis,value in enumerate(point):
            if type(value) not in (float,int) or not math.isfinite(value) or abs(value)>1e12:raise ValueError('host vertex domain')
            if type(value) is int:integers.add(axis)
        if len(integers)>1:raise ValueError('multiple integer axes need canonical arithmetic')
        out[i]=point
    checkpoint();return out

def _pack_triangles(mesh,triangle_type,checked,checkpoint):
    np=_np();out=np.empty((len(mesh.triangles),3),dtype=np.uint32)
    for k,tri in enumerate(checked(mesh.triangles,64)):
        if type(tri) is not triangle_type or any(type(i) is not int or not 0<=i<len(mesh.vertices) for i in tri[:3]):raise ValueError('host triangle domain')
        out[k]=tri[:3]
    checkpoint();return out

def compute_normals(mesh,vec_type,triangle_type,checked,checkpoint,lib,state,backend=1,workspace=None):
    """Same return contract as n810normals.compute; canonical normalization."""
    _mode(backend);_budget(len(mesh.vertices),len(mesh.triangles));checkpoint()
    if workspace is not None:
        workspace.pop('host_triangle_owner',None);workspace.pop('host_triangle_data',None)
    np=_np();began=time.monotonic();state.update(normal_backend='native-c/python-normalize',normal_phase='pack',normal_batches=0)
    vertices=_pack_vertices(mesh,vec_type,checked,checkpoint)
    triangles=_pack_triangles(mesh,triangle_type,checked,checkpoint)
    materials=['terrain']*len(vertices);sums=np.zeros_like(vertices)
    state['normal_phase']='accumulate'
    for off in range(0,len(triangles),CHUNK):
        checkpoint();chunk=triangles[off:off+CHUNK]
        lib.cold_normals(_ptr(vertices,D),_ptr(chunk,I),_ptr(sums,D),len(chunk))
        for tri in mesh.triangles[off:off+CHUNK]:
            for index in tri[:3]:materials[index]=tri.material
        state['normal_batches']+=1
    # Keep the current engine's Python/version sum behavior; never claim that
    # the old ordinary-sum C normalization supports compensated summation.
    from geometry import unit,dot
    state['normal_phase']='normalize'
    normals=[]
    for value in checked(sums):
        n=vec_type(*(float(x) for x in value))
        normals.append(unit(n) if dot(n,n)>1e-12 else vec_type(0,1,0))
    checkpoint()
    if workspace is not None:workspace.update(host_triangle_owner=mesh,host_triangle_data=triangles)
    state.update(normal_phase='complete',normal_triangles=len(triangles),normal_vertices=len(vertices),normal_wall_seconds=time.monotonic()-began)
    return tuple(normals),tuple(materials)

def compute_coverage(mesh,projected,pw,ph,focal,depths,samples,triangle_type,checked,checkpoint,lib,state,backend=1,triangle_budget=64,pixel_budget=4096,workspace=None):
    """Same transactional coverage contract as n810coverage.compute."""
    _mode(backend);nv=len(mesh.vertices);nt=len(mesh.triangles);ns=pw*ph;_budget(nv,nt,ns)
    if type(pw) is not int or type(ph) is not int or not 1<=pw<=4096 or not 1<=ph<=4096 or len(projected)!=nv:raise ValueError('host coverage dimensions')
    if type(triangle_budget) is not int or not 1<=triangle_budget<=64 or type(pixel_budget) is not int or not 1<=pixel_budget<=4096:raise ValueError('host coverage step bounds')
    if not isinstance(depths,array) or depths.typecode!='f' or depths.itemsize!=4 or len(depths)!=ns:raise ValueError('host depth buffer')
    if samples.ids.typecode!='I' or samples.ids.itemsize!=4 or len(samples.ids)!=ns*3 or samples.weights.typecode!='f' or samples.weights.itemsize!=4 or len(samples.weights)!=ns*2:raise ValueError('host sample buffers')
    np=_np();checkpoint();began=time.monotonic();state.update(coverage_backend='native-c',coverage_phase='pack',coverage_steps=0)
    points=np.empty((nv,3),dtype=np.float64)
    for i,point in enumerate(checked(projected)):
        if len(point)!=3 or any(type(v) is not float or not math.isfinite(v) or abs(v)>1e12 for v in point):raise ValueError('host projection domain')
        points[i]=point
    if workspace is not None and workspace.get('host_triangle_owner') is mesh:
        triangles=workspace.get('host_triangle_data')
        if type(triangles) is not np.ndarray or triangles.dtype!=np.uint32 or triangles.shape!=(nt,3) or not triangles.flags.c_contiguous:raise ValueError('host workspace triangles')
        if triangles.size and int(triangles.max())>=nv:raise ValueError('host workspace indices')
        state['coverage_reused_triangles']=nt
    else:triangles=_pack_triangles(mesh,triangle_type,checked,checkpoint)
    if focal and triangles.size and np.any(points[triangles,2]<=0):raise ValueError('host perspective requires clipped referenced triangles')
    # Nothing reaches caller buffers until completion and the final checkpoint.
    wd=np.frombuffer(depths,dtype=np.float32).copy();ids=np.frombuffer(samples.ids,dtype=np.uint32).copy();weights=np.frombuffer(samples.weights,dtype=np.float32).copy()
    cursor=np.zeros(32,dtype=np.float64);state['coverage_phase']='raster'
    pointers=(_ptr(points,D),_ptr(triangles,I),_ptr(wd,F),_ptr(ids,I),_ptr(weights,F),_ptr(cursor,D))
    while not cursor[30]:
        checkpoint();before=(cursor[0],cursor[17])
        status=lib.cold_coverage(*pointers,nt,pw,ph,int(bool(focal)),triangle_budget,pixel_budget)
        if status:raise RuntimeError('host coverage status '+str(status))
        if not cursor[30] and before==(cursor[0],cursor[17]):raise RuntimeError('host coverage made no progress')
        state['coverage_steps']+=1
    checkpoint()
    completed=[]
    for kind,values in (('f',wd),('I',ids),('f',weights)):
        packed=array(kind);packed.frombytes(values.tobytes());completed.append(packed)
    depths[:]=completed[0];samples.ids[:]=completed[1];samples.weights[:]=completed[2]
    state.update(coverage_phase='complete',coverage_triangles=nt,coverage_samples=ns,coverage_tested_pixels=int(cursor[17]),coverage_updates=int(cursor[18]),coverage_wall_seconds=time.monotonic()-began)
    return True

def compute_finish(mesh,normals,materials,samples,depths,pw,ph,terrain,vec_type,albedos_type,checked,checkpoint,lib,state,backend=1,*,haze_strength=.88):
    """Same finish contract as n810finish.compute, with configured haze."""
    _mode(backend);ns=pw*ph;_budget(len(mesh.vertices),len(mesh.triangles),ns)
    if len(samples)!=ns or len(depths)!=ns or len(normals)!=len(mesh.vertices) or len(materials)!=len(normals):raise ValueError('host finish shape')
    if not math.isfinite(haze_strength) or not 0<=haze_strength<=100:raise ValueError('host haze domain')
    np=_np();checkpoint();began=time.monotonic();state.update(finish_backend='native-c',finish_phase='prepare',finish_batches=0,finish_samples=0,finish_terrain_samples=0)
    finite=[d for d in checked(depths,128) if math.isfinite(d)]
    near=min(finite,default=0);span=max(finite,default=1)-near
    haze=array('f',(0 if not math.isfinite(d) else 1-math.exp(-haze_strength*max(0,d-near)/max(span,1e-9)) for d in checked(depths,128)))
    # Packing is bounded by checked(), including Python material/normal metadata.
    vertices=_pack_vertices(mesh,vec_type,checked,checkpoint)
    normal_data=np.empty((len(normals),3),dtype=np.float64)
    for i,n in enumerate(checked(normals)):
        if len(n)!=3 or any(type(v) not in (float,int) or not math.isfinite(v) for v in n):raise ValueError('host normal domain')
        normal_data[i]=n
    albedos=albedos_type(ns);water=[];pending=[];points=[]
    def flush():
        if not pending:return
        checkpoint();inputs=np.asarray(points,dtype=np.float64);colors=np.empty((len(pending),3),dtype=np.float64)
        lib.cold_colors(_ptr(inputs,D),_ptr(colors,D),len(pending));checkpoint()
        for i,index in enumerate(pending):albedos[index]=tuple(float(v) for v in colors[i])
        state['finish_batches']+=1;state['finish_terrain_samples']+=len(pending)
        pending.clear();points.clear()
    state['finish_phase']='samples'
    for index,sample in enumerate(checked(samples,128)):
        if sample is None:water.append(None);state['finish_samples']=index+1;continue
        a,b,c,w1,w2,w3=sample
        if any(type(i) is not int or not 0<=i<len(vertices) for i in (a,b,c)) or not all(math.isfinite(v) for v in (w1,w2,w3)):raise ValueError('host finish coverage')
        material=materials[a]
        if material=='water' or (material=='terrain' and terrain.units=='meters'):
            va,vb,vc=vertices[a],vertices[b],vertices[c]
            # Explicit component order matches the canonical scalar expression.
            x=float(va[0])*w1+float(vb[0])*w2+float(vc[0])*w3
            y=float(va[1])*w1+float(vb[1])*w2+float(vc[1])*w3
            z=float(va[2])*w1+float(vb[2])*w2+float(vc[2])*w3
            if material=='water':water.append(vec_type(x,y,z))
            else:
                ny=float(normal_data[a,1])*w1+float(normal_data[b,1])*w2+float(normal_data[c,1])*w3
                points.append((x,y,z,ny));pending.append(index);water.append(None)
                if len(pending)==COLOR_CHUNK:flush()
        else:water.append(None)
        state['finish_samples']=index+1
    flush();checkpoint()
    state.update(finish_phase='complete',finish_wall_seconds=time.monotonic()-began)
    return haze,albedos,tuple(water)
