"""Summarize opt-in driver CPU/wall windows without adding overlapping threads."""
import argparse,json,re
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('--after-seconds',type=float,default=0);p.add_argument('--output',type=Path);a=p.parse_args()
s=a.input.read_text();document={}
if a.input.suffix=='.json':document=json.loads(s);s=document.get('gears_log','')
windows=[]
for line in s.splitlines():
 if not line.startswith('N810_MBX_TRACE '):continue
 row={k:(v if k=='stage' else int(v)) for k,v in re.findall(r'(\w+)=(\S+)',line)}
 required={'thread','stage','calls','units','wall_ns','cpu_ns','max_wall_ns','begin_ns','end_ns'}
 if not required<=row.keys() or row['calls']<=0 or row['end_ns']<row['begin_ns']:raise ValueError('Malformed trace window')
 windows.append(row)
if not windows:raise ValueError('No driver trace windows found; do not interpret missing instrumentation as zero work')
start=min((r['begin_ns'] for r in windows),default=0)+int(a.after_seconds*1e9)
groups={}
for r in windows:
 if r['begin_ns']<start:continue
 groups.setdefault((r['thread'],r['stage']),[]).append(r)
if not groups:raise ValueError('No complete trace windows after the selected warm-up cutoff')
out=[]
for (thread,stage),rows in sorted(groups.items()):
 calls=sum(r['calls'] for r in rows);wall=sum(r['wall_ns'] for r in rows);cpu=sum(r['cpu_ns'] for r in rows)
 out.append({'thread':thread,'stage':stage,'windows':len(rows),'calls':calls,'units':sum(r['units'] for r in rows),
  'wall_ms_per_call':wall/calls/1e6,'cpu_ms_per_call':cpu/calls/1e6,'off_cpu_ms_per_call':max(0,wall-cpu)/calls/1e6,
  'clock_pair_skew_ns':max(0,cpu-wall),'largest_observed_call_ms':max(r['max_wall_ns'] for r in rows)/1e6})
result={'stages':out,'windows':windows,'nested_stages':{'geometry':['vertex_fetch','pipeline_shade','post_vertex','primitive_emit'],'pipeline_shade':['vertex_shader'],'queue_submit':['queue_publish']},'notes':['Nested stages overlap and must not be added to their parents.','CPU time is thread CPU, including kernel time on that thread.','Off-CPU time includes scheduling and blocking; it is not a measurement of GPU time.','Stages on different threads can overlap; do not sum them into frame latency.','Trace timing has observer overhead; compare with an uninstrumented control.','Cache counters are cumulative per shader instance and must be differenced within that instance.']}
cache_contexts={}
for line in document.get('gears_log',s).splitlines():
 if not line.startswith('N810_MBX_CACHE '):continue
 values=dict(re.findall(r'(\w+)=(\S+)',line))
 context=values.pop('context')
 row={k:int(v) for k,v in values.items()}
 old=cache_contexts.get(context)
 if old and row['calls']<old['calls']:
  raise ValueError('Cache context address reused; counters require an instance generation')
 cache_contexts[context]=row
hits=sum(row.get('vertices_hit',0) for row in cache_contexts.values())
misses=sum(row.get('vertices_missed',0) for row in cache_contexts.values())
result['cache']={'contexts':cache_contexts,'reported_hits':hits,'reported_misses':misses,
 'hit_fraction':hits/(hits+misses) if hits+misses else None,
 'note':'Latest cumulative report per context; excludes unreported tail calls.'}
intervals=[]
samples=document.get('trace_interval_samples',[]);hz=document.get('trace_clock_ticks_per_second',100)
for previous,current in zip(samples,samples[1:]):
 dt=(current['monotonic_ns']-previous['monotonic_ns'])/1e9
 if dt<=0:raise ValueError('Nonmonotonic interval sample')
 jobs=current['gpu_jobs']-previous['gpu_jobs']
 gpu_dt=(current.get('gpu_sample_ns',current['monotonic_ns'])-previous.get('gpu_sample_ns',previous['monotonic_ns']))/1e9
 display_dt=(current.get('display_sample_ns',current['monotonic_ns'])-previous.get('display_sample_ns',previous['monotonic_ns']))/1e9
 row={'seconds':dt,'completed_gpu_fps':jobs/gpu_dt,'display_transfers_per_second':(current['display_interrupts']-previous['display_interrupts'])/display_dt,
  'cpu_khz_at_end':current.get('cpu_khz'),'collection_ms':current['collection_ns']/1e6,'collection_cpu_ms':current.get('collection_cpu_ns',0)/1e6,'counter_timestamps_precise':'gpu_sample_ns' in current,'processes':[]}
 for pid,entry in current['processes'].items():
  old=previous['processes'].get(pid)
  if not old or old['start']!=entry['start']:continue
  cpu=(entry['ticks']-old['ticks'])/hz
  process_dt=(entry.get('sample_ns',current['monotonic_ns'])-old.get('sample_ns',previous['monotonic_ns']))/1e9
  row['processes'].append({'pid':int(pid),'name':entry['name'],'cpu_percent':cpu/process_dt*100,
   'cpu_ms_per_gpu_job':cpu*1000/jobs if jobs>0 else None,'major_faults':entry['major_faults']-old['major_faults'],'minor_faults':entry['minor_faults']-old['minor_faults']})
 deltas=[b-a for a,b in zip(previous['cpu_total_ticks'][:8],current['cpu_total_ticks'][:8])];total=sum(deltas)
 if total:row['system_busy_percent']=(total-deltas[3]-deltas[4])/total*100;row['system_iowait_percent']=deltas[4]/total*100
 intervals.append(row)
result['intervals']=intervals
s=json.dumps(result,indent=2)+'\n' 
if a.output:a.output.write_text(s)
else:print(s,end='')
