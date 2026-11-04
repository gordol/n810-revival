"""Repeatable local microbenchmark; no hardware performance inference."""
import json
import statistics
import time
import tracemalloc
from core import Host, Window

h=Host(76,22,[Window('Contacts',1,1,35,12),Window('Connections',20,5,38,10)])
h.content('Contacts',1,('N0CALL | unconfirmed',));h.content('Connections',1,('APRS | observed',))
h.flush(76*22)
samples=[];cells=[];sizes=[]
tracemalloc.start()
for i in range(1000):
    start=time.perf_counter_ns()
    h.begin();h.motion((i%3)-1,0);h.finish(True)
    out,changed,computed=h.flush()
    samples.append((time.perf_counter_ns()-start)/1e6)
    cells.append(computed);sizes.append(len(out.encode()))
current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
print(json.dumps({'iterations':len(samples),'median_ms':round(statistics.median(samples),3),
    'max_ms':round(max(samples),3),'max_composed_cells':max(cells),
    'max_output_bytes':max(sizes),'traced_peak_bytes_including_samples':peak,
    'content_builds':[w.builds for w in h.windows]},indent=2))
