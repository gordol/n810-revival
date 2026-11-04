# SPDX-License-Identifier: MIT
"""Batched geometry compute with an optional native CPU backend."""
from functools import lru_cache
from array import array
import importlib.util
from pathlib import Path
from build_trace import checkpoint

CHUNK = 256
_library = None
_adapter = None
_status = {'backend':'python-batch','reason':'not initialized'}
_counts = dict(native_batches=0, native_points=0, python_batches=0, python_points=0,
               reference_fallback_batches=0, reference_fallback_points=0,
               depth_native_batches=0,depth_native_points=0,depth_fallback_batches=0)


def _reference_sum_supported():
    return sum((1e16,1.0,-1e16)) == 0.0


def configure(library=None, adapter=None):
    """Configure once at startup, before scene workers or cached geometry exist."""
    global _library, _adapter
    _library = Path(library).resolve() if library is not None else None
    _adapter = Path(adapter).resolve() if adapter is not None else None
    _native.cache_clear()
    _status.clear()
    for key in _counts:_counts[key]=0
    return status()


@lru_cache(maxsize=1)
def _native():
    if _library is None or not _library.is_file():
        _status.update(backend='python-batch',reason='native library unavailable')
        return None
    if not _reference_sum_supported():
        _status.update(backend='python-batch',reason='reference uses compensated summation')
        return None
    choices=(_adapter,) if _adapter is not None else (
        _library.with_name('n810compute.py'),
        Path(__file__).with_name('native')/'accelerators/userspace/n810compute.py')
    source=next((p for p in choices if p.is_file()),None)
    if source is None:
        _status.update(backend='python-batch',reason='native adapter unavailable')
        return None
    try:
        spec=importlib.util.spec_from_file_location('_geometry_compute_adapter',source)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        probe=module.Projector((),_library)
        vfp=bool(probe.library.n810_compute_vfp())
    except (OSError,ValueError,ImportError,AttributeError,RuntimeError,SyntaxError) as error:
        _status.update(backend='python-batch',reason=str(error))
        return None
    _status.update(backend='native-vfp' if vfp else 'native-soft',
                   reason=None,library=str(_library))
    return module.Projector


def status():
    _native()
    return dict(_status,**_counts,**_normal_status,**_coverage_status,**_finish_status,**_pixel_status)


def _python(camera,points,axes):
    right,down,forward=axes
    ox,oy,oz=camera.origin
    rx,ry,rz=right;dx,dy,dz=down;fx,fy,fz=forward
    focal=camera.focal;sx=camera.span_x;sy=camera.span_y
    result=[]
    for px,py,pz in points:
        x,y,z=px-ox,py-oy,pz-oz
        # Keep sum() and component order, including compensated Python sums.
        depth=sum((x*fx,y*fy,z*fz))
        scale=focal/depth if focal and abs(depth)>1e-9 else 1
        result.append((sum((x*rx,y*ry,z*rz))*scale/sx+.5,
                       sum((x*dx,y*dy,z*dz))*scale/sy+.5,
                       depth))
    return result


def project(camera,points,workspace=None):
    """Project a sequence; retain no geometry beyond the caller's existing cache."""
    if workspace is not None:
        workspace.pop("projected_owner",None);workspace.pop("projected_data",None)
    if not points:return []
    native=_native()
    axes=camera.axes()
    result=[]
    packed=array('d') if workspace is not None and native is not None and len(points)<=65536 else None
    for offset in range(0,len(points),CHUNK):
        checkpoint()
        batch=points[offset:offset+CHUNK]
        if native is not None:
            try:
                projector=native(batch,_library)
                projected=projector.project(camera)
            except (ValueError,RuntimeError,OverflowError):
                packed=None
                _counts['reference_fallback_batches']+=1
                _counts['reference_fallback_points']+=len(batch)
                projected=[camera.project(point) for point in batch]
            else:
                if projector.last_backend in ('vfp','soft'):
                    _counts['native_batches']+=1;_counts['native_points']+=len(batch)
                    if packed is not None:packed.extend(projector.output)
                else:
                    packed=None
                    _counts['reference_fallback_batches']+=1
                    _counts['reference_fallback_points']+=len(batch)
            result.extend(projected)
        else:
            result.extend(_python(camera,batch,axes))
            _counts['python_batches']+=1;_counts['python_points']+=len(batch)
    if packed is not None:workspace.update(projected_owner=result,projected_data=packed)
    return result


_normal_module=None
_normal_c=None
_normal_call=None
_normal_mode=2
_normal_status=dict(normal_backend="disabled",normal_reason="not configured",
 normal_phase="disabled",normal_batches=0,normal_triangles=0,normal_vertices=0,normal_fallbacks=0)

def configure_normals(library=None):
    global _normal_module,_normal_c,_normal_call,_normal_mode
    _normal_module=None;_normal_c=None;_normal_call=None;_normal_mode=2
    _normal_status.clear()
    _normal_status.update(normal_backend="disabled",normal_reason="not configured",normal_phase="disabled",
        normal_batches=0,normal_triangles=0,normal_vertices=0,normal_fallbacks=0)
    if library is None:return dict(_normal_status)
    if not _reference_sum_supported():
        _normal_status["normal_reason"]="reference uses compensated summation"
        return dict(_normal_status)
    library=Path(library).resolve()
    source=library.with_name("n810normals.py")
    spec=importlib.util.spec_from_file_location("_geometry_normals_adapter",source)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    lib=module.load_library(library)
    if not lib.n810_normals_vfp():raise RuntimeError("normal VFP backend unavailable")
    _normal_module=module;_normal_c=lib
    _normal_status.update(normal_backend="native-vfp",normal_reason=None,normal_phase="ready",
                          normal_library=str(library))
    return dict(_normal_status)

def normal_data(mesh,vec_type,triangle_type,checked,workspace=None):
    if _normal_module is None:return None
    try:
        call=_normal_call or _normal_module.compute
        return call(mesh,vec_type,triangle_type,checked,checkpoint,_normal_c,_normal_status,_normal_mode,workspace)
    except (ValueError,RuntimeError,OverflowError,IndexError) as error:
        _normal_status["normal_fallbacks"]+=1
        _normal_status["normal_phase"]="python_fallback"
        _normal_status["normal_reason"]=type(error).__name__+": "+str(error)
        return None


# SPDX-License-Identifier: MIT
_coverage_module=None
_coverage_c=None
_coverage_call=None
_coverage_mode=2
_coverage_status=dict(coverage_backend="disabled",coverage_reason="not configured",coverage_phase="disabled",
 coverage_steps=0,coverage_triangles=0,coverage_tested_pixels=0,coverage_updates=0,
 coverage_prepared_triangles=0,coverage_degenerate_triangles=0,coverage_empty_bounds=0,
 coverage_inside_pixels=0,coverage_samples=0,coverage_fallbacks=0)

def configure_coverage(library=None):
    global _coverage_module,_coverage_c,_coverage_call,_coverage_mode
    _coverage_module=None;_coverage_c=None;_coverage_call=None;_coverage_mode=2
    _coverage_status.clear()
    _coverage_status.update(coverage_backend="disabled",coverage_reason="not configured",coverage_phase="disabled",
        coverage_steps=0,coverage_triangles=0,coverage_tested_pixels=0,coverage_updates=0,
        coverage_prepared_triangles=0,coverage_degenerate_triangles=0,coverage_empty_bounds=0,
        coverage_inside_pixels=0,coverage_samples=0,coverage_fallbacks=0)
    if library is None:return dict(_coverage_status)
    if not _reference_sum_supported():
        _coverage_status["coverage_reason"]="reference uses compensated summation"
        return dict(_coverage_status)
    library=Path(library).resolve()
    spec=importlib.util.spec_from_file_location("_geometry_coverage_adapter",library.with_name("n810coverage.py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    lib=module.load_library(library)
    if not lib.n810_coverage_vfp():raise RuntimeError("coverage VFP unavailable")
    _coverage_module=module;_coverage_c=lib
    _coverage_status.update(coverage_backend="native-vfp",coverage_reason=None,coverage_phase="ready",coverage_library=str(library))
    return dict(_coverage_status)

def coverage_data(mesh,projected,pw,ph,focal,depths,samples,triangle_type,checked,workspace=None):
    if _coverage_module is None:return False
    try:
        call=_coverage_call or _coverage_module.compute
        return call(mesh,projected,pw,ph,focal,depths,samples,triangle_type,checked,checkpoint,
                    _coverage_c,_coverage_status,_coverage_mode,workspace=workspace)
    except (ValueError,RuntimeError,OverflowError,IndexError,TypeError,AttributeError) as error:
        _coverage_status["coverage_fallbacks"]=_coverage_status.get("coverage_fallbacks",0)+1
        _coverage_status["coverage_phase"]="python_fallback"
        _coverage_status["coverage_reason"]=type(error).__name__+": "+str(error)
        return False


# SPDX-License-Identifier: MIT
_finish_module=None
_finish_c=None
_finish_call=None
_finish_mode=2
_finish_status=dict(finish_backend="disabled",finish_phase="disabled",finish_reason="not configured",
 finish_samples=0,finish_terrain_samples=0,finish_batches=0,finish_fallbacks=0)
def configure_finish(library=None):
    global _finish_module,_finish_c,_finish_call,_finish_mode
    _finish_module=None;_finish_c=None;_finish_call=None;_finish_mode=2;_finish_status.clear()
    _finish_status.update(finish_backend="disabled",finish_phase="disabled",finish_reason="not configured",
        finish_samples=0,finish_terrain_samples=0,finish_batches=0,finish_fallbacks=0)
    if library is None:return dict(_finish_status)
    if not _reference_sum_supported():
        _finish_status["finish_reason"]="reference uses compensated summation";return dict(_finish_status)
    library=Path(library).resolve()
    spec=importlib.util.spec_from_file_location("_geometry_finish_adapter",library.with_name("n810finish.py"))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    lib=module.load_library(library)
    if not lib.n810_finish_vfp():raise RuntimeError("finish VFP unavailable")
    _finish_module=module;_finish_c=lib
    _finish_status.update(finish_backend="native-vfp",finish_phase="ready",finish_reason=None,finish_library=str(library))
    return dict(_finish_status)
def finish_data(mesh,normals,materials,samples,depths,pw,ph,terrain,vec_type,albedos_type,checked,*,haze_strength=.88):
    if _finish_module is None:return None
    try:
        call=_finish_call or _finish_module.compute
        return call(mesh,normals,materials,samples,depths,pw,ph,terrain,vec_type,albedos_type,
                    checked,checkpoint,_finish_c,_finish_status,_finish_mode,haze_strength=haze_strength)
    except (ValueError,RuntimeError,OverflowError,IndexError,TypeError,AttributeError) as error:
        _finish_status["finish_fallbacks"]+=1
        _finish_status.update(finish_phase="python_fallback",finish_reason=type(error).__name__+": "+str(error))
        return None


_pixel_module=None
_pixel_c=None
_pixel_status={}
def configure_pixels(library=None,mode=2):
    """Startup registration; runtime verifies bundled provenance before calling."""
    global _pixel_module,_pixel_c
    _pixel_module=None;_pixel_c=None;_pixel_status.clear()
    _pixel_status.update(pixel_backend='disabled',pixel_phase='disabled',pixel_reason='not configured',
        pixel_batches=0,pixel_samples=0,pixel_water_samples=0,pixel_fallbacks=0,pixel_pack_batches=0,
        pixel_packed_samples=0,pixel_pack_fallbacks=0,pixel_wall_seconds=0.,pixel_cpu_seconds=0.)
    if library is None:return dict(_pixel_status)
    library=Path(library).resolve()
    spec=importlib.util.spec_from_file_location('_geometry_pixel_adapter',library.with_name('n810pixels.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    lib=module.load(library,mode)
    _pixel_module=module;_pixel_c=lib
    _pixel_status.update(pixel_backend='native-vfp' if mode==2 else 'native-ready',pixel_phase='ready',pixel_reason=None,pixel_library=str(library))
    return dict(_pixel_status)

def pixel_data(coverage,colors,lights,env,season,camera=None):
    if _pixel_module is None:return None
    import time
    wall=time.monotonic();cpu=time.thread_time()
    try:
        result=_pixel_module.shade(_pixel_c,coverage,colors,lights,env,season,camera=camera,state=_pixel_status)
        _pixel_status.update(pixel_phase='complete',pixel_reason=None)
        return result
    except (ValueError,RuntimeError,OverflowError,IndexError,TypeError,AttributeError) as error:
        _pixel_status['pixel_fallbacks']+=1
        _pixel_status.update(pixel_phase='python_fallback',pixel_reason=type(error).__name__+': '+str(error))
        return None
    finally:
        _pixel_status['pixel_wall_seconds']+=time.monotonic()-wall
        _pixel_status['pixel_cpu_seconds']+=time.thread_time()-cpu

configure_pixels()


# SPDX-License-Identifier: MIT
def configure_host_stages(library,adapter):
    """Startup-only registration after the owner verifies source/binary provenance.

    Retain canonical projection, clipping and stage fallback bodies. The host
    adapter uses C accumulation and canonical Python normalization; it does not
    change the ordinary-sum/VFP guards used by the separate ARM adapters.
    """
    global _normal_module,_normal_c,_normal_call,_normal_mode
    global _coverage_module,_coverage_c,_coverage_call,_coverage_mode
    global _finish_module,_finish_c,_finish_call,_finish_mode
    source=Path(adapter).resolve()
    spec=importlib.util.spec_from_file_location('_geometry_host_stage_adapter',source)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    caps=module.capabilities()
    required=('normals','coverage','finish','normalization_uses_canonical_sum')
    if caps.get('mode')!=1 or not all(caps.get(name) is True for name in required):
        raise ValueError('unsupported host stage capabilities')
    if caps.get('project') is not False or caps.get('depth') is not False:
        raise ValueError('host stages must retain canonical projection')
    if caps.get('requires_ordinary_sum',True) and not _reference_sum_supported():
        raise ValueError('host adapter requires ordinary summation')
    calls=tuple(getattr(module,name) for name in ('compute_normals','compute_coverage','compute_finish'))
    if not all(callable(call) for call in calls):raise ValueError('host stage entrypoint missing')
    # Opt-in initialization failures happen before any existing selection changes.
    # Default module import and the Nokia path remain independent of NumPy.
    if caps.get('numpy_required_for_host_optin'):
        module._np()
    lib=module.load_library(Path(library).resolve())
    configure(None);configure_normals(None);configure_coverage(None);configure_finish(None)
    _normal_module=_coverage_module=_finish_module=module
    _normal_c=_coverage_c=_finish_c=lib
    _normal_call,_coverage_call,_finish_call=calls
    _normal_mode=_coverage_mode=_finish_mode=1
    _normal_status.update(normal_backend='native-c/python-normalize',normal_reason=None,
                          normal_phase='ready',normal_library=str(Path(library).resolve()))
    _coverage_status.update(coverage_backend='native-c',coverage_reason=None,
                            coverage_phase='ready',coverage_library=str(Path(library).resolve()))
    _finish_status.update(finish_backend='native-c',finish_reason=None,
                          finish_phase='ready',finish_library=str(Path(library).resolve()))
    return status()


# SPDX-License-Identifier: MIT
def native_depths(camera,points):
    """Reuse the existing bounded projection engine for clipping depths."""
    if type(points) not in (tuple,list) or len(points)>65536:return None
    native=_native()
    if native is None:return None
    result=[]
    for offset in range(0,len(points),CHUNK):
        checkpoint();batch=points[offset:offset+CHUNK]
        try:
            projector=native(batch,_library);values=projector.project(camera)
        except (ValueError,RuntimeError,OverflowError,TypeError):
            _counts["depth_fallback_batches"]+=1
            return None
        if projector.last_backend not in ("vfp","soft"):
            _counts["depth_fallback_batches"]+=1
            return None
        result.extend(value[2] for value in values)
        _counts["depth_native_batches"]+=1;_counts["depth_native_points"]+=len(batch)
    checkpoint()
    return result

# Finish deferred selection before the importing consumer can call geometry.
from compute_runtime import ensure_selected
ensure_selected()
