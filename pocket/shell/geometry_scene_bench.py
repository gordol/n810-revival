# SPDX-License-Identifier: MIT
"""Bounded scene computation and ANSI generation; no terminal or device IO."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import resource
import sys
import time

def digest(scene):
    return hashlib.sha256(repr(sorted(scene.items())).encode()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('reference','python-batch','native'),required=True)
    parser.add_argument('--reference-directory',type=Path)
    parser.add_argument('--library',type=Path)
    parser.add_argument('--scene',choices=('small','terrain'),default='terrain')
    parser.add_argument('--width',type=int,default=80)
    parser.add_argument('--height',type=int,default=24)
    parser.add_argument('--host-native-plumbing',action='store_true')
    args=parser.parse_args()
    if not 1<=args.width<=160 or not 1<=args.height<=60:parser.error('viewport exceeds bounded benchmark')
    if args.mode=='reference':
        if args.reference_directory is None:parser.error('reference directory required')
        sys.path.insert(0,str(args.reference_directory.resolve()))
    process_work_start=time.monotonic_ns()
    print(json.dumps(dict(phase='imports',mode=args.mode,scene=args.scene)),flush=True)
    import geometry
    import geometry_compute
    if args.mode=='native':
        if args.library is None:parser.error('native library required')
        if args.host_native_plumbing:
            geometry_compute._reference_sum_supported=lambda:True
        state=geometry_compute.configure(args.library)
        if state['backend'] not in ('native-vfp','native-soft'):
            raise RuntimeError('requested native path unavailable: '+str(state))
    else:geometry_compute.configure(None)
    from core import Host
    import loading
    imports_and_configuration=time.monotonic_ns()-process_work_start
    print(json.dumps(dict(phase='ready',backend=geometry_compute.status(),imports_and_configuration_ns=imports_and_configuration)),flush=True)
    start=time.monotonic_ns()
    if args.scene=='terrain':
        import model_scene
        from landscape_detail import resolve
        nature=resolve(None,0)
        scene=model_scene.frame(args.width,args.height,mode='night',nature=nature)
        source=model_scene.tahoma()
    else:
        from dataclasses import replace
        source=geometry.build(2)
        source=replace(source,camera=geometry.Camera(origin=geometry.Vec(0,1,-200),
                                                    elevation=0,focal=200))
        scene=geometry.render(source,args.width,args.height,prepare_wire=True)[0]
    cold=time.monotonic_ns()-start
    first_hash=digest(scene)
    stats_after_cold=geometry_compute.status()
    print(json.dumps(dict(phase='cold-complete',elapsed_ns=cold,scene_sha256=first_hash,
                          source_vertices=len(source.mesh.vertices),
                          source_triangles=len(source.mesh.triangles),
                          backend=stats_after_cold)),flush=True)
    if args.mode=='native':assert stats_after_cold['native_points']>0
    if args.mode=='python-batch':assert stats_after_cold['python_points']>0
    start=time.monotonic_ns()
    host=Host(args.width,args.height,[])
    host.background(host.scene_cells(scene))
    first_output,first_changed,_=host.flush(args.width*args.height)
    first_composition=time.monotonic_ns()-start
    start=time.monotonic_ns()
    if args.scene=='terrain':
        lit=model_scene.frame(args.width,args.height,age=35020,nature=nature)
    else:
        from lighting import environment
        lit=geometry.render(source,args.width,args.height,environment=environment(35020),prepare_wire=True)[0]
    lighting=time.monotonic_ns()-start
    lit_hash=digest(lit)
    after_lighting=geometry_compute.status()
    if args.mode!='reference':
        assert after_lighting['native_points']==stats_after_cold['native_points']
        assert after_lighting['python_points']==stats_after_cold['python_points']
    start=time.monotonic_ns()
    if args.scene=='terrain':
        again=model_scene.frame(args.width,args.height,age=35020,nature=nature)
        assert again.base is lit.base
    else:
        again=geometry.render(source,args.width,args.height,environment=environment(35020),prepare_wire=True)[0]
    cached=time.monotonic_ns()-start
    start=time.monotonic_ns()
    host.background(host.scene_cells(lit))
    output,changed,_=host.flush(args.width*args.height)
    composition=time.monotonic_ns()-start
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_bytes=int(peak if sys.platform=='darwin' else peak*1024)
    print(json.dumps(dict(status='PASS',mode=args.mode,scene=args.scene,
        host_native_plumbing=args.host_native_plumbing,
        hardware_execution_verified=False,python=platform.python_version(),
        platform=platform.platform(),viewport=[args.width,args.height],
        cold_ns=cold,lighting_ns=lighting,cached_request_ns=cached,
        composition_and_ansi_ns=composition,
        cold_plus_composition_ns=cold+first_composition,
        imports_and_configuration_ns=imports_and_configuration,
        first_composition_and_ansi_ns=first_composition,
        first_frame_work_ns=imports_and_configuration+cold+first_composition,
        process_work_total_ns=time.monotonic_ns()-process_work_start,
        first_ansi_sha256=hashlib.sha256(first_output.encode()).hexdigest(),
        first_ansi_bytes=len(first_output.encode()),first_changed_cells=first_changed,
        cold_scene_sha256=first_hash,lighting_scene_sha256=lit_hash,
        ansi_sha256=hashlib.sha256(output.encode()).hexdigest(),
        ansi_bytes=len(output.encode()),changed_cells=changed,peak_rss_bytes=peak_bytes,
        raster_cache=geometry.raster.cache_info()._asdict(),backend=after_lighting,
        geometry_sha256=hashlib.sha256(Path(geometry.__file__).read_bytes()).hexdigest(),
        loading_sha256=hashlib.sha256(Path(loading.__file__).read_bytes()).hexdigest(),
        scope='Full scene generation, clipping, rasterization, lighting, wire detail, composition and ANSI generation; terminal transport/display excluded.')),flush=True)

if __name__=='__main__':main()
