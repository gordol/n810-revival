"""Local render/composition measurements, without terminal IO or frame-rate claims."""
from time import perf_counter
import json,resource,sys,math
from model_scene import frame,tahoma,base
from geometry import raster,raster_size
from core import Host

for width,height in ((160,50),(420,140)):
    base.cache_clear();raster.cache_clear()
    start=perf_counter();scene=frame(width,height,mode='night');cold=(perf_counter()-start)*1000
    start=perf_counter();frame(width,height,age=35020);lighting=(perf_counter()-start)*1000
    start=perf_counter()
    for _ in range(100):frame(width,height,mode='night')
    cached=(perf_counter()-start)*10
    host=Host(width,height,[])
    start=perf_counter();host.background(host.scene_cells(scene));output,changed,_=host.flush(width*height);compose=(perf_counter()-start)*1000
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1024**2 if sys.platform=='darwin' else 1024)
    print(json.dumps(dict(viewport=[width,height],raster_samples=math.prod(raster_size(width,height)),cold_ms=round(cold,2),lighting_ms=round(lighting,2),cached_ms=round(cached,4),first_composition_ms=round(compose,2),full_ansi_bytes=len(output.encode()),cells_changed=changed,process_peak_mib=round(peak,1))),flush=True)
print('triangles',len(tahoma().mesh.triangles),'peak elevation',max(tahoma().terrain.values),'dx dz',tahoma().terrain.dx,tahoma().terrain.dz)
