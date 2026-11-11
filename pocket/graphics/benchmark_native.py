"""Owner-launched native baseline: idle desktop or Room, no animated backdrop.

Consumes an inherited framebuffer; never loads drivers, switches VTs or reboots.
Idle FPS is not a throughput score: report CPU use and unnecessary submissions.
"""
from pathlib import Path
import argparse,ctypes as C,fcntl,hashlib,json,os,resource,signal,sys,time,termios,tty
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--framebuffer-fd',type=int,required=True);p.add_argument('--workload',choices=('idle','repaint','interactive','room'),default='idle');a=p.parse_args()
sys.path[:0]=[str(a.source/'graphics'),str(a.source/'shell')]
from nokia import NokiaPlatform
from window import Window
assert os.environ.get('POCKET_GL_TARGET') in ('legacy','direct')
assert os.environ.get('N810_MBX_DEVICE')=='1'
a.output.mkdir();(a.output/'state').mkdir()
def usage():
 r=resource.getrusage(resource.RUSAGE_SELF)
 return dict(system_cpu=[int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]],wall=time.monotonic_ns(),cpu=time.process_time_ns(),minor=r.ru_minflt,major=r.ru_majflt,peak_rss_kib=r.ru_maxrss)
def driver_counters():
 base=Path('/sys/module/n810_mbx_gpu_probe/parameters')
 names=('gpu_dma_sink_bytes','gpu_dma_sink_jobs','gpu_dma_sink_ns','gpu_dma_sink_failures','gpu_sink_bytes','gpu_sink_calls','gpu_success_capture_ns','gpu_full_copy_ns','gpu_full_encode_ns','gpu_texture_verify_ns','gpu_bounds_only_ns','gpu_service_jobs','gpu_read_calls','gpu_read_bytes','gpu_read_copy_ns','gpu_template_upload_bytes','gpu_texture_verify_bytes','gpu_profile_fifo_ns','gpu_profile_ta_finish_ns','gpu_profile_raster_observed_ns')
 return {name:int((base/name).read_text()) for name in names}
def status():
 result={}
 for name,path in [('memory','/proc/self/status'),('frequency','/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq')]:
  try:
   raw=Path(path).read_text();result[name]=[line for line in raw.splitlines() if line.startswith(('VmRSS:','VmSwap:'))] if name=='memory' else raw.strip()
  except OSError:result[name]=None
 return result
class Benchmark(NokiaPlatform):
 def __init__(self,*args,**kw):
  super().__init__(*args,**kw);self.phase=1 if a.workload=='room' else 0;self.began=None;self.start=None;self.results=[];self.cost={};self.failure=None
 def attach(self,*args):
  super().attach(*args)
  assert self.host.flux_performance=='balanced'
  assert 'Nokia MBX GPU transform' in self.renderer.renderer_name
  for name in ('cells','compose','present'):
   original=getattr(self.gpu_context,name)
   def wrapped(*args,_fn=original,_name=name,**kw):
    t=time.monotonic_ns();c=time.process_time_ns()
    try:return _fn(*args,**kw)
    finally:
     if self.start is not None:
      v=self.cost.setdefault(_name,[0,0,0]);v[0]+=1;v[1]+=time.monotonic_ns()-t;v[2]+=time.process_time_ns()-c
   setattr(self.gpu_context,name,wrapped)
 def room(self):return next((x for x in self.pixel_apps if x.name=='Surface room'),None)
 def present(self,complete):
  room=self.room();before=room.pixel_frames if room else 0
  result=super().present(complete)
  if self.start is not None and room and room.pixel_frames>before:
   v=self.cost.setdefault('room_native',[0,0,0]);v[0]+=room.pixel_frames-before;v[1]+=room.stats['last_pixel_wall_ns'];v[2]+=room.stats['last_pixel_cpu_ns']
  return result
 def wait_timeout(self,timeout):
  bounded=0 if a.workload=='repaint' else .25
  return min(bounded,timeout) if timeout is not None else bounded
 def events(self):
  events=super().events();now=time.monotonic()
  if a.workload=='repaint':self.host.invalidate((0,0,self.host.width,self.host.height));self.dirty=True
  if self.began is None and self.frames:
   if a.workload=='room' and not self.room():self.registry.open('surface-room');return events
   self.began=now
   print('PLAIN_DESKTOP_READY workload='+a.workload,flush=True)
  if self.began is None:return events
  if now-self.began>(210 if a.workload=='interactive' else 70):raise RuntimeError('Phase failed to finish in bound')
  if self.start is None and now-self.began>=5 and self.frames:
   fcntl.ioctl(a.framebuffer_fd,0x4f25)
   self.cost={};self.frame_start=self.frames;room=self.room();self.room_start=room.pixel_frames if room else 0
   self.state_start=status();self.scene_start=self.gpu_context.status();self.driver_start=driver_counters();self.start=usage()
  elif self.start is not None and (time.monotonic_ns()-self.start['wall'])>=(180_000_000_000 if a.workload=='interactive' else 20_000_000_000):
   fcntl.ioctl(a.framebuffer_fd,0x4f25);end=usage();room=self.room();frames=self.frames-self.frame_start;rf=(room.pixel_frames-self.room_start) if room else 0;seconds=(end['wall']-self.start['wall'])/1e9
   assert frames>=0 and self.host.flux_performance=='balanced' and not self.host.background_enabled
   if self.phase:assert room and rf>0 and frames>0
   driver_end=driver_counters();driver_delta={k:driver_end[k]-v for k,v in self.driver_start.items()}
   name='desktop_'+a.workload
   actual=os.pread(a.framebuffer_fd,768000,0);assert len(actual)==768000
   (a.output/(name+'.rgb565')).write_bytes(actual)
   system_delta=[b-a for a,b in zip(self.start['system_cpu'],end['system_cpu'])];system_total=sum(system_delta)
   report=dict(system_cpu_jiffies=system_delta,system_busy_percent=100*(system_total-sum(system_delta[3:5]))/system_total if system_total else None,workload=name,seconds=seconds,desktop_frames=frames,desktop_fps=frames/seconds,room_frames=rf,room_fps=rf/seconds,process_cpu_ms=(end['cpu']-self.start['cpu'])/1e6,cpu_ms_per_desktop_frame=(end['cpu']-self.start['cpu'])/frames/1e6 if frames else None,minor_faults=end['minor']-self.start['minor'],major_faults=end['major']-self.start['major'],peak_rss_kib=end['peak_rss_kib'],quality=dict(flux=self.host.flux_performance,effect=None,background_enabled=self.host.background_enabled,room_pixels=room.size if room else None,canvas=[800,480]),phase_counters=self.cost,driver_counters=driver_delta,state_start=self.state_start,state_end=status(),image_sha256=hashlib.sha256(actual).hexdigest(),framebuffer_matches=None,pixel_proof='separate DMA exact comparison',scene_start=self.scene_start,scene_end=self.gpu_context.status())
   self.results.append(report);self.start=None
   (a.output/'results.json').write_text(json.dumps(self.results,indent=2));print(json.dumps(report),flush=True)
   self.closed=True
  return events
window=Window(a.assets/'window.so',a.framebuffer_fd)
b=Benchmark(a.assets/'console-font.psf',a.assets/'renderer.so',window,require_gpu=True,cell_renderer='gpu',diagnostics=False,seconds=205 if a.workload=='interactive' else 145)
old=termios.tcgetattr(sys.stdin)
try:
 tty.setraw(sys.stdin,when=termios.TCSANOW)
 result=b.run(['--shell','--session',str(a.output/'state/desktop.json'),'--app-state',str(a.output/'state'),'--station-db',str(a.output/'state/directory.sqlite3'),'--native',str(a.assets/'_cellengine.abi3.so'),'--scene-seed','2420','--no-save','--touch-device','/dev/input/n810-touch','--touch-calibration','/home/nokia/.local/state/current-world/touch-calibration.json','--touch-display','800x480','--touch-rotation','0','--touch-acquisition','process'])
 assert result in (None,0) and len(b.results)==1
finally:
 try:b.close()
 finally:termios.tcsetattr(sys.stdin,termios.TCSANOW,old)
