"""Bounded standard Debian glxgears on the physical display; restore its VT."""
from pathlib import Path
import os,sys,subprocess,time,signal,json,hashlib,threading,fcntl,struct
root=Path(sys.argv[1]).resolve()
assert os.geteuid()==0
assert os.uname().release=='5.15.224-n810-mbx-clock-wip1'
gpu_parameters=Path('/sys/module/n810_mbx_gpu_probe/parameters')
assert not gpu_parameters.exists()
gpu_jobs_before=0
assert not Path('/tmp/.X1-lock').exists()
assert not Path('/tmp/.X11-unix/X1').exists()
assert not any(x in os.environ for x in ('LIBGL_ALWAYS_SOFTWARE','MESA_LOADER_DRIVER_OVERRIDE','GALLIUM_DRIVER'))
backlight=Path('/sys/class/backlight/n810-backlight/brightness')
if not backlight.exists():backlight=next(Path('/sys/class/backlight').glob('*/brightness'))
original_brightness=backlight.read_text().strip()
display_rate=Path('/sys/module/omap2fb/parameters/auto_update_freq')
original_display_rate=display_rate.read_text().strip()
requested_display_rate=os.environ.get('N810_MBX_DISPLAY_HZ')
assert requested_display_rate in (None,'30','60')
display_rate_changed=False
assert os.environ.get('N810_MBX_PARALLEL_START','0') in ('0','1')
parallel_startup=os.environ.get('N810_MBX_PARALLEL_START','0')=='1'
original=Path('/sys/class/tty/tty0/active').read_text().strip()
assert original in ('tty1','tty8'),original
# Ask the kernel for an unused VT; openvt still refuses an intervening owner.
with open('/dev/tty0','rb',buffering=0) as console:
 available=bytearray(4);fcntl.ioctl(console.fileno(),0x5600,available)
test_vt=struct.unpack('i',available)[0]
assert 1<=test_vt<=63 and 'tty'+str(test_vt)!=original,test_vt
for path in Path('/proc').glob('[0-9]*/stat'):
 try:fields=path.read_text().rsplit(')',1)[1].split()
 except (FileNotFoundError,ProcessLookupError):continue
 assert int(fields[4])!=os.makedev(4,test_vt),'Test VT already has an owner'
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
session=Path('/home/nokia/.local/state/current-world/session.msgpack')
saved_preferences=session.read_bytes()
package=root/'mesa-utils-bin_8.5.0-1_armel.deb'
assert hashlib.sha256(package.read_bytes()).hexdigest()=='437189037ab235e5c450c0c682b6c843c8aea43a37d65c4ca3a40bd4c2bbe898'
extract=root/'extract';extract.mkdir(exist_ok=True)
subprocess.run(['dpkg-deb','-x',str(package),str(extract)],check=True)
gears=list((extract/'usr/bin').glob('glxgears*'));info=list((extract/'usr/bin').glob('glxinfo*'))
assert len(gears)==len(info)==1
for binary in (gears[0],info[0]):
 linked=subprocess.check_output(['ldd',str(binary)],text=True)
 (root/(binary.name+'.ldd.txt')).write_text(linked)
 assert 'not found' not in linked,linked
config=root/'xorg.conf';authority=root/'Xauthority'
config.write_text('''Section "ServerFlags"
 Option "AutoAddDevices" "false"
 Option "AutoEnableDevices" "false"
 Option "BlankTime" "0"
 Option "StandbyTime" "0"
 Option "SuspendTime" "0"
 Option "OffTime" "0"
EndSection
Section "Device"
 Identifier "NokiaFramebuffer"
 Driver "fbdev"
 Option "fbdev" "/dev/fb0"
EndSection
Section "Screen"
 Identifier "NokiaScreen"
 Device "NokiaFramebuffer"
 DefaultDepth 16
 SubSection "Display"
  Depth 16
 EndSubSection
EndSection
''')
direct_x=os.environ.get('N810_MBX_DIRECT_X')=='1'
if direct_x:
 config.write_text(config.read_text().replace(' Option "fbdev" "/dev/fb0"',' Option "fbdev" "/dev/fb0"\n Option "ShadowFB" "false"'))
subprocess.run(['xauth','-f',str(authority),'add',':1','.',os.urandom(16).hex()],check=True)
authority.chmod(0o600)
env=dict(os.environ,DISPLAY=':1',XAUTHORITY=str(authority),GALLIUM_DRIVER='softpipe')
gears_env=dict(env,LD_LIBRARY_PATH=str(root/'lib'),N810_MBX_DEVICE='1',N810_MBX_FAST_VS='check',MESA_RGB_VISUAL='TrueColor 16',MESA_INFO='1')
report=dict(boot_id=boot,kernel=os.uname().release,original_vt=original,display=':1',server_driver='fbdev',
            raster_backend='MBX GPU; Mesa CPU transform and lighting',package_sha256=hashlib.sha256(package.read_bytes()).hexdigest())
report['test_vt']='tty'+str(test_vt)
report['x_shadow_framebuffer_requested']=not direct_x
report['driver_options']={name:os.environ.get(name,'0') for name in ('N810_MBX_ARM_JIT','N810_MBX_REUSE_INPUTS','N810_MBX_SHARED_IMAGE','N810_MBX_STREAMING_FRAME','N810_MBX_SPARSE_PARAMETERS','N810_MBX_TILE_DAMAGE','N810_MBX_DIRECT_X','N810_MBX_SCATTER_FRAME','N810_MBX_REUSE_VERTEX_BUFFERS','N810_MBX_ASYNC','N810_MBX_DEFER_VERTEX_STORES','N810_MBX_EARLY_CULL','N810_MBX_DETAILED_PROFILE','N810_MBX_CPU_PROFILE','N810_MBX_FLOAT_FETCH','N810_MBX_DIRECT_PACK','N810_MBX_PAUSE_DESKTOP','N810_MBX_VERTEX_CACHE','N810_MBX_UNIFORM_CACHE','N810_MBX_DEFER_REUSE','N810_MBX_ASYNC_FENCES','N810_MBX_TRACE')}
report['glxgears_executable_sha256']=hashlib.sha256(gears[0].read_bytes()).hexdigest()
def cpu_snapshot(pids=None):
 records={}
 paths=Path('/proc').glob('[0-9]*/stat') if pids is None else (Path('/proc')/str(pid)/'stat' for pid in pids)
 for stat in paths:
  try:
   text=stat.read_text();fields=text.rsplit(')',1)[1].split()
   records[stat.parent.name]={'name':text.split('(',1)[1].rsplit(')',1)[0],
      'ticks':int(fields[11])+int(fields[12]),'start':fields[19],
      'minor_faults':int(fields[7]),'major_faults':int(fields[9]),'sample_ns':time.monotonic_ns()}
  except (OSError,ValueError,IndexError):continue
 return time.monotonic(),records
def display_interrupts():
 return int(next(line for line in Path('/proc/interrupts').read_text().splitlines() if 'OMAP DISPC' in line).split()[1])
x=None;g=None;server_pid=None;status=None;reader=None
preflight=None;ready_read=None;ready_write=None;sampler=None
idle_paused=False;desktop_pause=None
assert os.environ.get("N810_MBX_PAUSE_DESKTOP","0") in ("0","1")
idle_was_running=subprocess.run(['/etc/init.d/n810-wake','status'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
try:
 if idle_was_running:
  subprocess.run(['/etc/init.d/n810-wake','stop'],check=True);idle_paused=True
 subprocess.run(['/usr/local/sbin/n810-screen','on'],check=True,timeout=10)
 with (root/'x-launch.log').open('wb') as log:
  x=subprocess.Popen(['openvt','-c',str(test_vt),'-s','-w','--','/usr/lib/xorg/Xorg',':1','vt'+str(test_vt),'-dpms','-extension','GLX','-keeptty','-nolisten','tcp','-noreset','-config',str(config),'-auth',str(authority),'-logfile',str(root/'Xorg.log')],env=env,stdout=log,stderr=subprocess.STDOUT)
  for _ in range(160):
   if Path('/tmp/.X11-unix/X1').exists():break
   if x.poll() is not None:raise RuntimeError('X server exited; see x-launch.log and Xorg.log')
   time.sleep(.25)
  else:raise RuntimeError('X startup timeout')
  server_pid=int(Path('/tmp/.X1-lock').read_text())
  assert str(config).encode() in Path(f'/proc/{server_pid}/cmdline').read_bytes()
  subprocess.run([str(root/'gears-status'),'--ready-only'],env=env,check=True,timeout=60)
  assert Path('/sys/devices/platform/omapdss/display0/enabled').read_text().strip()=='1'
  if os.environ.get('N810_MBX_PAUSE_DESKTOP')=='1':
   from desktop_pause import pause_desktop
   desktop_pause=pause_desktop(original)
   report['hidden_desktop_paused']=True
  status=subprocess.Popen([str(root/'gears-status')],env=env,stdin=subprocess.PIPE)
  status.stdin.write(b'N810_MBX_STAGE GPU checks + Mesa loading\n' if parallel_startup else b'N810_MBX_STAGE Checking GPU baseline\n');status.stdin.flush()
  ready_read,ready_write=os.pipe()
  gears_env['N810_MBX_READY_FD']=str(ready_read)
  preflight_started=time.monotonic()
  preflight=subprocess.Popen([sys.executable,str(root/'run_service_frame.py'),str(root),str(root/'gears-frame.mbf'),'--preflight-native'])
  if not parallel_startup and preflight.wait()!=0:raise RuntimeError('GPU preflight failed')
  with (root/'glxgears.txt').open('wb') as output:
   application_started=time.monotonic()
   g=subprocess.Popen(['stdbuf','-oL',str(gears[0]),'-info','-geometry','400x400+200+40'],env=gears_env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,pass_fds=(ready_read,))
   os.close(ready_read);ready_read=None
   def copy_log():
    for line in iter(g.stdout.readline,b''):
     try:output.write(line);output.flush()
     except ValueError:break
     try:status.stdin.write(line);status.stdin.flush()
     except BrokenPipeError:pass
   reader=threading.Thread(target=copy_log,daemon=True);reader.start()
   if preflight.wait()!=0:raise RuntimeError('GPU preflight failed; readiness not released')
   report['gpu_preflight_seconds']=time.monotonic()-preflight_started
   assert (gpu_parameters/'gpu_service_active').read_text().strip()=='1'
   assert (gpu_parameters/'gpu_service_baseline_verified').read_text().strip()=='1'
   gpu_jobs_before=int((gpu_parameters/'gpu_service_jobs').read_text())
   report['display_initialized_before_gpu']=True
   if requested_display_rate is not None:
    display_rate.write_text(requested_display_rate+'\n');display_rate_changed=True
   report['display_update_setting']=display_rate.read_text().strip()
   status.stdin.write(b'N810_MBX_STAGE Starting first frame\n');status.stdin.flush()
   ready_sent=time.monotonic();os.write(ready_write,b'\x01');os.close(ready_write);ready_write=None
   report['concurrent_application_startup']=parallel_startup
   deadline=time.monotonic()+180
   while 'FPS' not in (root/'glxgears.txt').read_text():
    if g.poll() is not None:
     report['gears_exit_code']=g.returncode
     raise RuntimeError('glxgears exited before producing frames: '+str(g.returncode))
    if time.monotonic()>deadline:raise RuntimeError('No measured gears frames within180seconds')
    time.sleep(1)
   assert Path('/sys/class/tty/tty0/active').read_text().strip()=='tty'+str(test_vt)
   assert 'N810_MBX_GPU_FRAME' in (root/'glxgears.txt').read_text()
   report['application_to_first_fps_seconds']=time.monotonic()-application_started
   report['ready_to_first_fps_seconds']=time.monotonic()-ready_sent
   assert int((gpu_parameters/'gpu_service_jobs').read_text())>gpu_jobs_before
   assert status.poll() is None,'Status panel failed'
   time.sleep(1)
   assert Path('/sys/class/graphics/fb0/stride').read_text().strip()=='1600'
   with open('/dev/fb0','rb',buffering=0) as fb:frame=fb.read(800*480*2)
   assert len(frame)==800*480*2
   assert len(set(frame))>4,'No visible rendered content'
   (root/'gears.rgb565').write_bytes(frame)
   traced=os.environ.get('N810_MBX_TRACE')=='1'
   tracked=[g.pid,server_pid,os.getpid()]
   if traced:
    for proc in Path('/proc').glob('[0-9]*/cmdline'):
     try:command=proc.read_bytes()
     except OSError:continue
     if b'/n810-pocket-session' in command or b'/device_services.py' in command:tracked.append(int(proc.parent.name))
    report['trace_clock_ticks_per_second']=os.sysconf('SC_CLK_TCK')
    sampler=subprocess.Popen([str(root/'profile-sampler'),str(root/'intervals.jsonl'),'12','5000',*map(str,sorted(set(tracked)))])
    report['trace_sampler_pid']=sampler.pid
   cpu_start=cpu_snapshot()
   report['gpu_jobs_at_cpu_start']=int((gpu_parameters/'gpu_service_jobs').read_text())
   display_interrupts_start=display_interrupts()
   print('VISIBLE_GEARS_CAPTURED',flush=True)
   # Keep the real application visible for attended inspection, while saving
   # updated screenshots and counters. No change to the application's code.
   for _ in range(12):
    if g.poll() is not None:raise RuntimeError('glxgears stopped during visible test')
    time.sleep(5)
   with open('/dev/fb0','rb',buffering=0) as fb:second=fb.read(800*480*2)
   (root/'gears-second.rgb565').write_bytes(second)
   cpu_end=cpu_snapshot();elapsed=cpu_end[0]-cpu_start[0];hz=os.sysconf('SC_CLK_TCK')
   report['display_interrupts_per_second']=(display_interrupts()-display_interrupts_start)/elapsed
   usage=[]
   for pid,entry in cpu_end[1].items():
    old=cpu_start[1].get(pid)
    if old and old['start']==entry['start']:
     usage.append({'pid':int(pid),'name':entry['name'],
        'cpu_percent':round(100*(entry['ticks']-old['ticks'])/hz/elapsed,2),
        'minor_faults':entry['minor_faults']-old['minor_faults'],
        'major_faults':entry['major_faults']-old['major_faults']})
   report['cpu_sample_seconds']=elapsed
   report['gpu_jobs_at_cpu_end']=int((gpu_parameters/'gpu_service_jobs').read_text())
   report['sample_gpu_frames']=report['gpu_jobs_at_cpu_end']-report['gpu_jobs_at_cpu_start']
   report['sample_gpu_completed_fps']=report['sample_gpu_frames']/elapsed
   if report['sample_gpu_frames']:
    report['render_cpu_ms_per_completed_frame']=sum(item['cpu_percent'] for item in usage if item['name'].startswith('glxgears'))*elapsed*10/report['sample_gpu_frames']
   if sampler is not None:
    assert sampler.wait(timeout=3)==0,'Native profiler failed'
    report['trace_interval_samples']=[json.loads(line) for line in (root/'intervals.jsonl').read_text().splitlines()]
    assert len(report['trace_interval_samples'])==12
    for sample in report['trace_interval_samples']:
     for pid,entry in sample['processes'].items():
      entry['name']='profile-sampler' if int(pid)==sampler.pid else cpu_start[1].get(pid,{}).get('name','unknown')
    sampler=None
   report['cpu_usage']=sorted(usage,key=lambda x:x['cpu_percent'],reverse=True)[:12]
   report['memory_after']=Path('/proc/meminfo').read_text()
   report['two_captures_differ']=second!=frame
   g.terminate();g.wait(timeout=8);reader.join(timeout=5);g=None
  report['gears_log']=(root/'glxgears.txt').read_text()
  report['glxinfo']='Renderer identity is recorded by the unchanged glxgears -info invocation'
  report['gpu_jobs_completed']=int((gpu_parameters/'gpu_service_jobs').read_text())-gpu_jobs_before
  report['gpu_phase_average_us']={name:int((gpu_parameters/('gpu_frame_'+name+'_us')).read_text()) for name in ('prepare','clear','render','verify','tail_verify')}
  report['native_vertex_requested']=os.environ.get('N810_MBX_ARM_JIT','0')=='1'
  report['hardware_acceleration_confirmed']=report['gpu_jobs_completed']>0 and 'N810_MBX_GPU_FRAME' in report['gears_log'] and 'N810_MBX_GPU_FAILED' not in report['gears_log']
  report['mesa_library_sha256']=hashlib.sha256((root/'lib/libGL.so.1').read_bytes()).hexdigest()
  report['status']='STANDARD_GLXGEARS_GPU_EXECUTED_WITH_VISIBLE_MODE_AND_FPS'
finally:
 if sampler is not None and sampler.poll() is None:
  sampler.terminate();sampler.wait(timeout=3)
 for fd in (ready_read,ready_write):
  if fd is not None:os.close(fd)
 if preflight is not None and preflight.poll() is None:preflight.wait()
 if display_rate_changed:
  display_rate.write_text(original_display_rate+'\n')
 report['display_update_setting_restored']=display_rate.read_text().strip()==original_display_rate
 if g is not None and g.poll() is None:
  g.terminate()
  try:g.wait(timeout=8)
  except subprocess.TimeoutExpired:g.kill();g.wait()
 if reader is not None:reader.join(timeout=5)
 if status is not None and status.poll() is None:
  status.terminate();status.wait(timeout=5)
 # Release GPU ownership while X still holds the same stable display mode.
 # A failed release leaves X and the idle hold intact; never modeset through it.
 if gpu_parameters.exists():
  stopped=subprocess.run([sys.executable,str(root/'stop_service.py'),str(root/'service-stop')])
  if stopped.returncode or gpu_parameters.exists():
   report['status']='GPU_RELEASE_FAILED_DISPLAY_MODE_RETAINED'
   (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
   raise RuntimeError('GPU release incomplete; display kept in its existing mode')
 report['gpu_removed_before_display_restore']=True
 if server_pid is None and Path('/tmp/.X1-lock').exists():
  candidate=int(Path('/tmp/.X1-lock').read_text())
  try:
   if str(config).encode() in Path(f'/proc/{candidate}/cmdline').read_bytes():server_pid=candidate
  except FileNotFoundError:pass
 if server_pid is not None:
  try:os.kill(server_pid,signal.SIGTERM)
  except ProcessLookupError:pass
 if x is not None:
  try:x.wait(timeout=12)
  except subprocess.TimeoutExpired:report['x_launch_wait_timeout']=True
 if desktop_pause is not None:
  desktop_pause.close();report['hidden_desktop_resumed']=True
 subprocess.run(['chvt',original.removeprefix('tty')],check=True)
 backlight.write_text(original_brightness+'\n')
 if idle_paused:subprocess.run(['/etc/init.d/n810-wake','start'],check=True)
 # A benchmark may begin after the idle timer has already blanked the panel.
 # Return visibly to Pocket rather than restoring that transient zero value.
 if int(original_brightness)==0:
  subprocess.run(['/usr/local/sbin/n810-screen','on'],check=True,timeout=10)
 report['idle_service_restored']=not idle_paused or subprocess.run(['/etc/init.d/n810-wake','status'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
 report['restored_brightness']=backlight.read_text().strip()
 report['restored_vt']=Path('/sys/class/tty/tty0/active').read_text().strip()
 report['boot_unchanged']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
 report['session_preferences_changed']=session.read_bytes()!=saved_preferences
 report['session_sha256_before']=hashlib.sha256(saved_preferences).hexdigest()
 report['session_sha256_after']=hashlib.sha256(session.read_bytes()).hexdigest()
 (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print('DISPLAY_RESTORED',report['restored_vt'],flush=True)
