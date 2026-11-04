# SPDX-License-Identifier: MIT
"""Bounded binary64 normal kernels; retain Python metadata and cancellation."""
from array import array
from contextlib import contextmanager
import ctypes
import math
from itertools import islice
import time

CHUNK=256
D=ctypes.POINTER(ctypes.c_double)
I=ctypes.POINTER(ctypes.c_uint32)
B=ctypes.POINTER(ctypes.c_ubyte)

def load_library(path):
    lib=ctypes.CDLL(str(path))
    lib.n810_normals_abi.argtypes=[];lib.n810_normals_abi.restype=ctypes.c_uint32
    lib.n810_normals_vfp.argtypes=[];lib.n810_normals_vfp.restype=ctypes.c_int
    if lib.n810_normals_abi()!=1:raise ValueError("unsupported normal ABI")
    lib.n810_normal_accumulate.argtypes=[D,I,D,ctypes.c_size_t,ctypes.c_size_t,ctypes.c_int]
    lib.n810_normal_accumulate.restype=ctypes.c_int
    lib.n810_normal_finish.argtypes=[D,D,B,ctypes.c_size_t,ctypes.c_int]
    lib.n810_normal_finish.restype=ctypes.c_int
    return lib

@contextmanager
def phase(state,name):
    state["normal_phase"]=name
    wall=time.monotonic();cpu=time.thread_time()
    try:yield
    finally:
        state[name+"_wall_seconds"]=time.monotonic()-wall
        state[name+"_thread_cpu_seconds"]=time.thread_time()-cpu


def _bounded_integer_compute(mesh,vec_type,triangle_type,checked,checkpoint,lib,state,backend,workspace):
    # New eligibility is deliberately narrower than the existing float route.
    # Source snapshots and original Python component types are retained.
    from geometry import Vec,Triangle,unit,dot
    if vec_type is not Vec or triangle_type is not Triangle or type(mesh.vertices) is not tuple or type(mesh.triangles) is not tuple:
        raise ValueError('bounded normals require canonical immutable mesh')
    nv,nt=len(mesh.vertices),len(mesh.triangles)
    if nv>65536 or nt>131072:raise ValueError('bounded normal dimensions')
    with phase(state,'normal_vertex_pack'):
        vertices=array('d');point_types=[];maximum=0
        for point in checked(mesh.vertices):
            if type(point) is not vec_type:raise ValueError('normal point type')
            mask=0
            for axis,value in enumerate(point):
                if type(value) not in (int,float) or (type(value) is int and abs(value)>1<<53) or not math.isfinite(value):
                    raise ValueError('finite integer/float normal coordinates required')
                maximum=max(maximum,abs(value))
                if type(value) is float:mask|=1<<axis
            point_types.append(mask);vertices.extend(point)
        # Each edge <=2M, product <=4M^2, oriented cross <=8M^2.
        # Three incident contributions per triangle includes repeated IDs.
        bound=24*max(1,nt)*math.ceil(maximum)**2
        if bound>1<<53:raise ValueError('integer normal exactness bound')
        if vertices.itemsize!=8:raise ValueError('binary64 array required')
    with phase(state,'normal_triangle_pack'):
        indices=array('I');types=bytearray(nv);materials=['terrain']*nv
        for triangle in checked(mesh.triangles):
            if type(triangle) is not triangle_type:raise ValueError('normal triangle type')
            ids=triangle[:3]
            if any(type(i) is not int or not 0<=i<nv for i in ids):raise ValueError('normal triangle index')
            axes=point_types[ids[0]]|point_types[ids[1]]|point_types[ids[2]]
            floating=int(bool(axes&6))|(int(bool(axes&5))<<1)|(int(bool(axes&3))<<2)
            for i in ids:types[i]|=floating;materials[i]=triangle.material
            indices.extend(ids)
        if indices.itemsize!=4:raise ValueError('uint32 indices required')
        sums=array('d',[0.0])*(3*nv)
        v=(ctypes.c_double*len(vertices)).from_buffer(vertices)
        acc=(ctypes.c_double*len(sums)).from_buffer(sums)
    with phase(state,'normal_accumulation'):
        for start in range(0,nt,CHUNK):
            batch=indices[start*3:min(nt,start+CHUNK)*3]
            ids=(ctypes.c_uint32*len(batch)).from_buffer(batch)
            checkpoint()
            result=lib.n810_normal_accumulate(v,ids,acc,nv,len(batch)//3,backend)
            if result!=backend:raise RuntimeError('normal accumulate rejected: '+str(result))
            state['normal_batches']+=1;state['normal_triangles']+=len(batch)//3
    # An integer accumulator stays integer until a floating contribution arrives.
    # The existing C finish computes binary64 square/sum; preserve Python here.
    with phase(state,'normal_normalization'):
        normals=[]
        for i in checked(range(nv)):
            value=vec_type(*(sums[3*i+j] if types[i]&(1<<j) else int(sums[3*i+j]) for j in range(3)))
            normals.append(unit(value) if dot(value,value)>1e-12 else vec_type(0,1,0))
    checkpoint()
    if workspace is not None:workspace.update(triangle_owner=mesh,triangle_data=indices)
    state.update(normal_phase='complete',normal_reason=None,normal_integer_bound=bound,
                 normal_accumulation_backend='native-vfp' if backend==2 else 'native-c',
                 normal_normalization_backend='python-canonical',
                 normal_python_normalized_vertices=state.get('normal_python_normalized_vertices',0)+nv)
    return tuple(normals),materials


def compute(mesh,vec_type,triangle_type,checked,checkpoint,lib,state,backend=2,workspace=None):
    nv=len(mesh.vertices)
    if workspace is not None:
        workspace.pop("triangle_owner",None);workspace.pop("triangle_data",None)
    triangle_data=array('I') if workspace is not None and type(mesh.triangles) is tuple and len(mesh.triangles)<=131072 else None
    if nv>65536:raise ValueError("normal vertex bound")
    with phase(state,"normal_vertex_pack"):
        vertices=array('d');integer_axes=set();bounded=False
        for point in checked(mesh.vertices):
            if type(point) is not vec_type:raise ValueError("normal point type")
            for axis,value in enumerate(point):
                if type(value) is int:integer_axes.add(axis)
                elif type(value) is not float:raise ValueError("normal coordinate type")
            if len(integer_axes)>1:bounded=True;break
            vertices.extend(point)
        if not bounded:
            if vertices.itemsize!=8:raise ValueError("binary64 array required")
            sums=array('d',[0.0])*(3*nv)
            v=(ctypes.c_double*len(vertices)).from_buffer(vertices)
            s=(ctypes.c_double*len(sums)).from_buffer(sums)
            materials=['terrain']*nv
    if bounded:return _bounded_integer_compute(mesh,vec_type,triangle_type,checked,checkpoint,lib,state,backend,workspace)
    state['normal_normalization_backend']='native-vfp' if backend==2 else 'native-c'
    with phase(state,"normal_accumulation"):
        iterator=iter(checked(mesh.triangles))
        while True:
            batch=tuple(islice(iterator,CHUNK))
            if not batch:break
            indices=array('I')
            for triangle in batch:
                if type(triangle) is not triangle_type:raise ValueError("normal triangle type")
                ids=triangle[:3]
                indices.extend(ids)
                for index in ids:materials[index]=triangle.material
            if indices.itemsize!=4:raise ValueError("uint32 indices required")
            if triangle_data is not None:triangle_data.extend(indices)
            ids=(ctypes.c_uint32*len(indices)).from_buffer(indices)
            checkpoint()
            result=lib.n810_normal_accumulate(v,ids,s,nv,len(batch),backend)
            if result!=backend:raise RuntimeError("normal accumulate rejected: "+str(result))
            state["normal_batches"]+=1;state["normal_triangles"]+=len(batch)
    with phase(state,"normal_normalization"):
        result=[]
        iterator=iter(checked(range(nv)))
        while True:
            batch=tuple(islice(iterator,CHUNK))
            if not batch:break
            start=batch[0];count=len(batch)
            output=array('d',[0.0])*(3*count);active=array('B',[0])*count
            src=ctypes.cast(ctypes.byref(s,start*3*8),D)
            out=(ctypes.c_double*len(output)).from_buffer(output)
            flags=(ctypes.c_ubyte*len(active)).from_buffer(active)
            checkpoint()
            status=lib.n810_normal_finish(src,out,flags,count,backend)
            if status!=backend:raise RuntimeError("normal finish rejected: "+str(status))
            for present,x,y,z in zip(active,output[0::3],output[1::3],output[2::3]):
                result.append(vec_type(x,y,z) if present else vec_type(0,1,0))
            state["normal_batches"]+=1;state["normal_vertices"]+=count
    if triangle_data is not None:workspace.update(triangle_owner=mesh,triangle_data=triangle_data)
    state["normal_phase"]="complete"
    return tuple(result),materials
