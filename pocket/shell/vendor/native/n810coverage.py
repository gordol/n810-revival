# SPDX-License-Identifier: MIT
"""Resumable coverage over scratch packed arrays; commit only on completion."""
from array import array
from contextlib import contextmanager
import ctypes
import time
D=ctypes.POINTER(ctypes.c_double)
I=ctypes.POINTER(ctypes.c_uint32)
F=ctypes.POINTER(ctypes.c_float)
def load_library(path):
    lib=ctypes.CDLL(str(path))
    lib.n810_coverage_abi.argtypes=[];lib.n810_coverage_abi.restype=ctypes.c_uint32
    lib.n810_coverage_vfp.argtypes=[];lib.n810_coverage_vfp.restype=ctypes.c_int
    if lib.n810_coverage_abi()!=1:raise ValueError("unsupported coverage ABI")
    lib.n810_coverage_step.argtypes=[D,I,F,I,F,D,ctypes.c_size_t,ctypes.c_size_t,ctypes.c_size_t,ctypes.c_size_t,
                                    ctypes.c_int,ctypes.c_size_t,ctypes.c_size_t,ctypes.c_int]
    lib.n810_coverage_step.restype=ctypes.c_int
    return lib
@contextmanager
def phase(state,name):
    state["coverage_phase"]=name;wall=time.monotonic();cpu=time.thread_time()
    try:yield
    finally:
        state[name+"_wall_seconds"]=time.monotonic()-wall
        state[name+"_thread_cpu_seconds"]=time.thread_time()-cpu
def compute(mesh,projected,pw,ph,focal,depths,samples,triangle_type,checked,checkpoint,lib,state,
            backend=2,triangle_budget=64,pixel_budget=4096,workspace=None):
    if type(projected) not in (tuple,list) or type(mesh.triangles) is not tuple:
        raise ValueError("coverage requires reusable projection/triangle sequences")
    nv=len(projected);nt=len(mesh.triangles);np=pw*ph
    if nv>65536 or nt>131072 or not 0<pw<=1024 or not 0<ph<=1024 or np>470400:raise ValueError("coverage bounds")
    if len(depths)!=np or len(samples)!=np or depths.typecode!='f' or samples.ids.typecode!='I' or samples.weights.typecode!='f':
        raise ValueError("coverage arrays")
    with phase(state,"coverage_pack"):
        points=workspace.get("projected_data") if workspace is not None and workspace.get("projected_owner") is projected else None
        if type(points) is not array or points.typecode!='d' or len(points)!=3*nv:points=None
        state["coverage_reused_projection"]=nv if points is not None else 0
        if points is None:
            points=array('d')
            for point in checked(projected):
                if len(point)!=3 or any(type(value) is not float for value in point):raise ValueError("coverage requires float projections")
                points.extend(point)
        triangles=workspace.get("triangle_data") if workspace is not None and workspace.get("triangle_owner") is mesh else None
        if type(triangles) is not array or triangles.typecode!='I' or len(triangles)!=3*nt:triangles=None
        state["coverage_reused_triangles"]=nt if triangles is not None else 0
        if triangles is None:
            triangles=array('I')
            for tri in checked(mesh.triangles,64):
                if type(tri) is not triangle_type:raise ValueError("coverage triangle type")
                triangles.extend(tri[:3])
        work_depths=array('f',depths);work_ids=array('I',samples.ids);work_weights=array('f',samples.weights)
        if points.itemsize!=8 or work_ids.itemsize!=4 or work_depths.itemsize!=4 or work_weights.itemsize!=4:
            raise ValueError("coverage array widths")
        if len(work_ids)!=3*np or len(work_weights)!=2*np:raise ValueError("coverage buffer lengths")
        cursor=array('d',[0.0])*32
        p=(ctypes.c_double*len(points)).from_buffer(points)
        t=(ctypes.c_uint32*len(triangles)).from_buffer(triangles)
        d=(ctypes.c_float*len(work_depths)).from_buffer(work_depths)
        ids=(ctypes.c_uint32*len(work_ids)).from_buffer(work_ids)
        weights=(ctypes.c_float*len(work_weights)).from_buffer(work_weights)
        progress=(ctypes.c_double*len(cursor)).from_buffer(cursor)
    with phase(state,"coverage_raster"):
        while not cursor[30]:
            checkpoint()
            before_triangle=cursor[0];before_pixels=cursor[17]
            result=lib.n810_coverage_step(p,t,d,ids,weights,progress,nv,nt,pw,ph,int(bool(focal)),
                                          triangle_budget,pixel_budget,backend)
            if result!=backend:raise RuntimeError("coverage step rejected: "+str(result)+"; shape="+repr((nv,nt,pw,ph,bool(focal),triangle_budget,pixel_budget))+"; cursor="+repr(list(cursor)))
            if not cursor[30] and cursor[0]==before_triangle and cursor[17]==before_pixels:
                raise RuntimeError("coverage made no progress")
            state.update(coverage_steps=state["coverage_steps"]+1,coverage_triangles=int(cursor[0]),
                coverage_tested_pixels=int(cursor[17]),coverage_updates=int(cursor[18]),
                coverage_prepared_triangles=int(cursor[19]),coverage_degenerate_triangles=int(cursor[20]),
                coverage_empty_bounds=int(cursor[21]),coverage_inside_pixels=int(cursor[22]),
                coverage_cursor_x=int(cursor[2]),coverage_cursor_y=int(cursor[3]))
    checkpoint()
    with phase(state,"coverage_commit"):
        depths[:]=work_depths;samples.ids[:]=work_ids;samples.weights[:]=work_weights
    state["coverage_phase"]="complete";state["coverage_samples"]=np
    return True
