"""Measure actual bounded shadow/transparency redraws; terminal writes are excluded."""
import argparse,hashlib,json,sys,time
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--shell',type=Path,default=Path(__file__).resolve().parents[1]/'shell')
p.add_argument('--native',type=Path,required=True)
p.add_argument('--reference-compose',action='store_true',help='use existing Python blending with the same scene generator')
p.add_argument('--frames',type=int,default=5)
a=p.parse_args()
if not 2<=a.frames<=1000:p.error('frames must be 2–1000')
sys.path.insert(0,str(a.shell))
from core import Host,Window
from native_scene import flux
h=Host(100,29,[Window('System',2,2,49,17,lines=['System status','Battery: 65%','CPU: 35%']*5),Window('Connections',39,9,48,17,lines=['Local services','SSH: connected','Reticulum: online']*5)])
h.background_enabled=False;h.shadow_enabled=True;h.window_opacity=.88;h.animate=False;h.show_clock=False;h.show_connectivity=False
h.observe_composition=True
assert h.enable_native(a.native),h.native_error
if a.reference_compose:h._native.supports_blend=lambda host,windows:False
for step in range(a.frames):
    start=time.monotonic();cpu=time.process_time()
    h.background(h.scene_cells(flux(h._native.lib,100,29,step,False,1.,.15,2)))
    generated=time.process_time()
    h.content('System',step,['System status','Battery: 65%','Sample age: '+str(step)]*5,spans=((0,0,13,'heading'),(1,0,12,'control')))
    digest=hashlib.sha256();batches=changed=0
    while h.damage:
        output,c,n=h.flush(2900,max_seconds=.012);batches+=1;changed+=c;digest.update(output.encode())
    print(json.dumps(dict(step=step,cpu_seconds=time.process_time()-cpu,generation_cpu_seconds=generated-cpu,wall_seconds=time.monotonic()-start,batches=batches,changed=changed,output_sha256=digest.hexdigest(),backend=h.render_backend,phases=h.compose_phases)),flush=True)
