"""Local full-path weather microbenchmark; no N810 inference."""
import json
import statistics
import time
from core import Host,Window
from weather import PRESETS,detail_budget

for width,height in ((80,24),(160,50),(240,80)):
    now=[0.0]
    h=Host(width,height,[Window('Contacts',5,5,32,10)],clock=lambda:now[0])
    h.set_effect('snow');h.set_weather(PRESETS[2]);h.background_enabled=True
    h.flush(width*height)
    samples=[];emitted=[];composed=[];retained=[]
    for step in range(1,61):
        now[0]=step/6
        start=time.perf_counter_ns()
        out,changed,work=h.flush(width*height)
        samples.append((time.perf_counter_ns()-start)/1e6)
        emitted.append(len(out.encode()));composed.append(work);retained.append(len(h.backdrop))
    print(json.dumps({'grid':[width,height],'detail_budget':detail_budget(width,height),
        'median_ms':round(statistics.median(samples),3),'max_ms':round(max(samples),3),
        'max_scene_cells':max(retained),'max_recomposed_cells':max(composed),'max_bytes':max(emitted)}))
