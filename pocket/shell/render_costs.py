"""Local same-model cost comparison. No device access, animation loop or deployment."""
import argparse
import json
from pathlib import Path
import resource
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width',type=int,default=100);parser.add_argument('--height',type=int,default=27)
    parser.add_argument('--out',type=Path);args=parser.parse_args();w,h=args.width,args.height
    imported=time.perf_counter()
    from model_scene import view
    from landscape_detail import Nature
    from geometry import raster,render,cell_samples
    from lighting import environment
    from loading import wires,WorldReveal,Arrival,ripple_damage
    import vegetation
    from core import Host
    imports_ms=(time.perf_counter()-imported)*1000
    start=time.perf_counter();model=view(aspect=w/(h*2),nature=Nature('spring',True,True,True,False,123));model_ms=(time.perf_counter()-start)*1000
    results=[];original=vegetation.ground_color
    for mode in ('geometry_flat','static_material_light'):
        raster.cache_clear();wires.cache_clear();material_started=[None]
        def material(point,normal):
            if material_started[0] is None:material_started[0]=time.perf_counter()
            return (70,90,75) if mode=='geometry_flat' else original(point,normal)
        vegetation.ground_color=material
        start=time.perf_counter();coverage=raster(model,w,h);ready=time.perf_counter()
        mesh,_,materials,samples,_,_,pw,ph,*_=coverage
        if mode=='geometry_flat':
            colors={'terrain':0x465a4b,'water':0x203c50}
            pixels=[0x15202a if sample is None else colors.get(materials[sample[0]],0x203c2a) for sample in samples]
            cells={(i%w,i//w):('▄',(1<<48)|(b<<24)|a) for i,(a,b) in enumerate(cell_samples(pixels,pw,ph,w,h))}
        else:cells,_=render(model,w,h,environment=environment(0),prepare_wire=False)
        shaded=time.perf_counter()
        host=Host(w,h,[]);host.shadow_enabled=False;host.background(host.scene_cells(cells))
        output,changed,composed=host.flush(w*h);composed_at=time.perf_counter()
        results.append(dict(mode=mode,coverage_ms=((material_started[0] or ready)-start)*1000,material_binding_ms=(ready-(material_started[0] or ready))*1000,static_shading_or_flat_pack_ms=(shaded-ready)*1000,composition_serialization_ms=(composed_at-shaded)*1000,changed_cells=changed,composed_cells=composed,ansi_bytes=len(output.encode())))
    vegetation.ground_color=original
    start=time.perf_counter();wire=wires(model,w,h);wire_ms=(time.perf_counter()-start)*1000
    plan=Arrival(w,h);fx=[]
    for previous,current in ((.105,.14),(.4,.52)):
        indices=ripple_damage(wire,w,previous,current,plan);shader=WorldReveal(plan.world(0,0,current),current,wire)
        start=time.perf_counter()
        for index in indices:shader.cell(cells[index%w,index//w],index)
        fx.append(dict(previous_phase=previous,phase=current,affected_cells=len(indices),world_shader_ms=(time.perf_counter()-start)*1000))
    result=dict(viewport=[w,h],seed=123,geometry_vertices=len(model.mesh.vertices),triangles=len(model.mesh.triangles),imports_ms=imports_ms,model_prepare_ms=model_ms,modes=results,wire_prepare_ms=wire_ms,wire_cells=len(wire),fx=fx,peak_rss_native=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,notes=['Same real DEM, camera and instance geometry in both modes; base geometry is never disabled.','Flat mode omits procedural noise and directional shading; coverage still binds flat materials.','Coverage/material split marks the first ground-material callback; material binding includes interpolation overhead.','FX timing covers continuous-depth world shader only; no animated loop or terminal write is included.','ANSI byte counts and composition are local; no terminal transport or physical-device FPS claim.'])
    text=json.dumps(result,indent=2)+'\n'
    if args.out:args.out.write_text(text)
    else:print(text,end='')


if __name__=='__main__':main()
