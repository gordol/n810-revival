"""Own the normal native Pocket desktop and restore the prior display on exit."""
from pathlib import Path
import os,sys,subprocess,fcntl,struct,json
import tempfile,shutil,pwd,signal,argparse
assert os.geteuid()==0
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--release',type=Path,default=Path('/usr/local/lib/n810-graphics/current'))
parser.add_argument('--source',type=Path,default=Path('/usr/local/share/pocket-gui/managed-native/source'))
parser.add_argument('--symbian-code',type=Path)
parser.add_argument('--symbian-windows',action='store_true')
parser.add_argument('--probe',type=Path,help='run one offscreen GPU integration probe instead of Pocket')
options=parser.parse_args()
release=options.release.resolve(strict=True)
source=options.source.resolve(strict=True)
manifest=json.loads((release/'MANIFEST.json').read_text())
import hashlib
for name,digest in manifest['files'].items():assert hashlib.sha256((release/name).read_bytes()).hexdigest()==digest
runtime=Path('/run/n810-pocket-native');runtime.mkdir(exist_ok=True)
lock=open(runtime/'owner.lock','w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
root=Path(tempfile.mkdtemp(prefix='run-',dir=runtime));os.chmod(root,0o755)
shutil.copytree('/usr/local/lib/n810-pocket/native-template',root,dirs_exist_ok=True)
(root/'payload/n810_mbx_gpu_probe.ko').unlink();(root/'payload/n810_mbx_gpu_probe.ko').symlink_to(release/'n810_mbx_gpu_probe.ko')
# Pin the module identity to the selected release, not the old template.
assert os.uname().release==manifest['kernel_release']
build_path=root/'BUILD.json';build=json.loads(build_path.read_text());build['module_sha256']=manifest['files']['n810_mbx_gpu_probe.ko'];build_path.write_text(json.dumps(build))
identity_path=root/'MANIFEST.json';identity=json.loads(identity_path.read_text());identity['files']['payload/n810_mbx_gpu_probe.ko']['sha256']=build['module_sha256'];identity_path.write_text(json.dumps(identity))
settings=json.loads((release/'defaults.json').read_text()).get('pocket_module',{})
allowed={'gpu_dma_damage_mapping','gpu_dma_reuse_channel','gpu_verification_mode','gpu_window_native'}
assert set(settings)<=allowed and all(type(v) is int and v in (0,1) for v in settings.values())
if options.symbian_windows:
 assert settings.get('gpu_window_native')==1 and options.symbian_code is not None
 assert hashlib.sha256((options.symbian_code/'symbian-runtime').read_bytes()).hexdigest()==manifest['symbian_runtime_sha256']
 assert hashlib.sha256((options.symbian_code/'lib/libOSMesa.so.8').read_bytes()).hexdigest()==manifest['files']['libOSMesa.so.8.0.0']
if settings:
 helper=root/'run_service_frame.py';text=helper.read_text();kick=" subprocess.run(['/sbin/insmod',str(module)]"
 assert kick in text;helper.write_text(text.replace(kick,' p.update('+repr(settings)+')\n'+kick,1))
assets=Path('/usr/local/share/pocket-gui/managed-native/assets')
# Optional preparation accelerators belong to the same immutable release.
# Older releases retain their existing native library and replay policy.
native_library=(release if '_cellengine.abi3.so' in manifest['files'] else assets)/'_cellengine.abi3.so'
page_groups=json.loads((release/'defaults.json').read_text()).get('native',{}).get('POCKET_SCENE_PAGE_GROUPS','0')
assert page_groups in ('0','1')
base=Path('/sys/module/n810_mbx_gpu_probe/parameters')
subprocess.run([sys.executable,str(root/'owner_session.py'),'start','--device-released'],check=True)
account=pwd.getpwnam('nokia')
device=Path('/dev/n810-mbx-render');render_fd=None;job_lock_fd=None
assert os.geteuid()==0
for n,v in [('gpu_service_active','1'),('gpu_service_baseline_verified','1'),('gpu_service_failed','0'),('resident_fault','0'),('gpu_error','0')]:assert (base/n).read_text().strip()==v
assert (base/'gpu_service_opened').read_text().strip() in ('N','0')
mode=Path('/sys/class/graphics/fb0/update_mode');original_mode=mode.read_text();assert original_mode.strip()=='1'
active=Path('/sys/class/tty/tty0/active');original=active.read_text().strip();boot=Path('/proc/sys/kernel/random/boot_id').read_text()
console=os.open('/dev/tty0',os.O_RDWR|os.O_NOCTTY|os.O_CLOEXEC);available=bytearray(4);fcntl.ioctl(console,0x5600,available);vt=struct.unpack('i',available)[0]
assert 1<=vt<=63 and vt!=int(original[3:])
for f in Path('/proc').glob('[0-9]*/stat'):
 try:assert int(f.read_text().rsplit(')',1)[1].split()[4])!=os.makedev(4,vt)
 except (FileNotFoundError,ProcessLookupError):pass
tty=os.open('/dev/tty'+str(vt),os.O_RDWR|os.O_NOCTTY|os.O_CLOEXEC);kd=bytearray(4);fcntl.ioctl(tty,0x4b3b,kd);old_kd=struct.unpack('i',kd)[0]
fb=os.open('/dev/fb0',os.O_RDWR|os.O_CLOEXEC);switched=False;child=None;stopping=False
fcntl.ioctl(fb,0x4f25);saved_frame=os.pread(fb,768000,0);assert len(saved_frame)==768000
report=dict(original_vt=original,test_vt=vt,boot_before=boot)
env={k:v for k,v in os.environ.items() if not k.startswith('N810_MBX_')}
if options.symbian_windows:env['POCKET_SYMBIAN_WINDOWS']='1'
env.update(POCKET_SCENE_DAMAGE_ROOM='1',POCKET_SCENE_OUTPUT_TILE='400x256',POCKET_SUBMIT_LABEL=root.name,POCKET_DIAGNOSTIC=os.environ.get('POCKET_DIAGNOSTIC','0'),LD_LIBRARY_PATH=str(assets),LD_PRELOAD=str(assets/'libOSMesa.so.8'),GALLIUM_DRIVER='softpipe',NATIVE_FB_FD=str(fb),N810_MBX_NATIVE32_LAYOUT='bgra',N810_MBX_LINEAR_TEXTURE='1',N810_MBX_MIXED_RESOURCES='1',N810_MBX_EXPERIMENTAL_SCISSOR='1',N810_MBX_EXPERIMENTAL_MODULATE='1',N810_MBX_SEPARATE_ALPHA='1',N810_MBX_RESIDENT_CHECKPOINT='0')
for n in ['DEVICE','GPU_VERTEX','EXCLUSIVE_SURFACE','STREAMING_FRAME','WIRE_REPLAY','VERIFY_BURST','VERIFY_UPLOAD_BURST','EXPERIMENTAL_2D','EXPERIMENTAL_MIXED','MULTI_TEXTURE','EXPERIMENTAL_BLEND','EXPERIMENTAL_TEXTURE','REUSE_VERTEX_BUFFERS','FLOAT_FETCH','TEXTURE_CACHE']:env['N810_MBX_'+n]='1'
for n in ['SHARED_IMAGE','ASYNC','TEMPLATE','RASTER_PAUSE_US']:env['N810_MBX_'+n]='0'
env['POCKET_NATIVE_PIXELS']='1'
env['N810_MBX_TEMPLATE']='0'
env['N810_MBX_TRACE']=os.environ.get('POCKET_DIAGNOSTIC','0')
env['N810_MBX_DEBUG']=os.environ.get('POCKET_DIAGNOSTIC','0')
enabled='1'
for n in ('POCKET_SCENE_DIRECT_ROOM','POCKET_SCENE_DIRECT_BASE','POCKET_SCENE_OPAQUE_TARGETS'):env[n]=enabled
env['POCKET_OWNED_SINK']='1'
env['POCKET_DMA_SINK']='0'
suffix='normal';env['POCKET_DATA_ROOT']='/home/nokia/.local/share/pocket'
def symbian_drop():
 os.setsid();os.initgroups(account.pw_name,account.pw_gid);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
def child_tty():
 phase='setsid'
 try:
  os.setsid();phase='controlling-terminal';fcntl.ioctl(0,0x540e,0)
  phase='groups';os.initgroups(account.pw_name,account.pw_gid)
  phase='gid';os.setgid(account.pw_gid);phase='uid';os.setuid(account.pw_uid)
 except BaseException as error:
  os.write(2,('desktop_spawn_failure phase='+phase+' error='+str(error)+'\n').encode());raise

try:
 mode.write_text('2\n');fcntl.ioctl(fb,0x4f25)
 fcntl.ioctl(tty,0x4b3a,1);fcntl.ioctl(console,0x5606,vt);fcntl.ioctl(console,0x5607,vt);switched=True
 with (root/('visible-'+suffix+'.log')).open('x') as log:
  env.update(HOME=account.pw_dir,USER='nokia',LOGNAME='nokia',POCKET_NATIVE_PIXELS='1',POCKET_GL_TARGET='direct',POCKET_SCENE_BATCHES='1',POCKET_SCENE_PARTIAL='1',POCKET_SCENE_MOVE_REUSE='1',POCKET_SCENE_COMPILED='1',POCKET_SCENE_MATRIX_CACHE='1',POCKET_SCENE_DMA_DAMAGE='1',POCKET_SCENE_WINDOW_IMAGES='1',POCKET_SCENE_WINDOW_WARMUP='8',POCKET_SCENE_OVERLAP='1',POCKET_SCENE_OUTPUT_TILE='800x480',POCKET_DMA_SINK='1',POCKET_DMA_FORWARD='1',N810_MBX_TEXTURE_SUBSET='1',N810_MBX_TEXTURE_RESIDENCY='1',N810_MBX_WINDOW_IMAGES='1',N810_MBX_RESOURCE_REFERENCES='1',N810_MBX_DESKTOP_TARGET='1',LD_LIBRARY_PATH=str(release)+':'+str(assets),LD_PRELOAD=str(release/'libOSMesa.so.8'))
  env['POCKET_SCENE_PAGE_GROUPS']=page_groups
  env['POCKET_SCENE_DAMAGE_CULL']='0'
  command=[sys.executable,str(source/'graphics/nokia.py'),'--framebuffer-fd',str(fb),'--font',str(assets/'console-font.psf'),'--renderer-library',str(assets/'renderer.so'),'--display-library',str(release/'window.so'),'--native-library',str(native_library),'--state','/home/nokia/.local/state/current-world','--touch-device','/dev/input/n810-touch','--touch-calibration','/home/nokia/.local/state/current-world/touch-calibration.json','--touch-display','800x480','--touch-rotation','0']
  render_fd=os.open(device,os.O_RDWR|os.O_CLOEXEC);env['N810_MBX_RENDER_FD']=str(render_fd)
  window_mode=env.get('POCKET_SYMBIAN_WINDOWS')=='1'
  if window_mode:
   ui=runtime/'ui';ui.mkdir(mode=0o700,exist_ok=True);os.chown(ui,account.pw_uid,account.pw_gid);ui.chmod(0o700)
   from symbian_windows import retire_stale_control
   retire_stale_control(ui/'desktop.sock',account.pw_uid)
   command+=['--control-socket',str(ui/'desktop.sock')]
   env['N810_DESKTOP_SOCKET']=str(ui/'desktop.sock')
   job_lock_fd=os.memfd_create('pocket-gpu-jobs',os.MFD_CLOEXEC)
   env.update(N810_MBX_JOB_LOCK_FD=str(job_lock_fd),N810_MBX_NATIVE_WINDOWS='1',N810_MBX_WINDOW_FIRST='6',N810_MBX_WINDOW_COUNT='8',N810_MBX_SEPARATE_ALPHA='1')
  if options.probe:command=[str(options.probe.resolve(strict=True))]
  desktop_fds=(fb,render_fd,job_lock_fd) if window_mode else (fb,render_fd)
  child=subprocess.Popen(command,env=env,cwd=root,stdin=tty,stdout=log,stderr=subprocess.STDOUT,pass_fds=desktop_fds,preexec_fn=child_tty)
  def record_child(application='pocket'):
   (runtime/'active.json').write_text(json.dumps(dict(owner_pid=os.getpid(),child_pid=child.pid,application=application,release=str(release),log=str(root/('visible-'+suffix+'.log')))))
  record_child('probe' if options.probe else 'pocket')
  def stop(signum,frame):
   global stopping
   stopping=True
   if child.poll() is None:child.send_signal(signal.SIGTERM)
  signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
  sys.path.insert(0,str(Path(__file__).resolve().parent))
  from symbian_session import Session,command as symbian_command,run as run_symbian,keyboard_device
  from symbian_windows import Broker
  broker=Broker(account,render_fd,job_lock_fd,env,symbian_drop,status_directory=runtime,code=options.symbian_code) if window_mode and not options.probe else None
  launches=None if options.probe else Session(runtime,account.pw_uid,account.pw_gid,windows=broker)
  def ready(app):
   symbian_command(app,account.pw_dir)
   keyboard_device()
  try:
   while True:
    application=None if options.probe else launches.wait(child,ready)
    if application is None:
     report['returncode']=child.wait();break
    child.send_signal(signal.SIGTERM)
    child.wait(timeout=30)
    os.close(tty);tty=os.open('/dev/tty'+str(vt),os.O_RDWR|os.O_NOCTTY|os.O_CLOEXEC)
    # Closing the desktop finishes its GL work before another context starts.
    for key in ('gpu_service_failed','resident_fault','gpu_error'):
     if (base/key).read_text().strip()!='0':raise RuntimeError('GPU session is faulted; launch refused')
    def track_symbian(process):
     global child
     child=process
     record_child(application)
    try:
     result=run_symbian(application,account,fb,render_fd,env,tty,symbian_drop,track_symbian)
     (runtime/'symbian-result').write_text(str(result)+'\t'+application+'\n')
     (runtime/'symbian-result').chmod(0o644)
    except (OSError,subprocess.SubprocessError) as error:print('Symbian launch failed:',error,file=log,flush=True)
    if stopping:
     report['returncode']=child.returncode;break
    for key in ('gpu_service_failed','resident_fault','gpu_error'):
     if (base/key).read_text().strip()!='0':raise RuntimeError('GPU session faulted during Symbian execution')
    os.close(tty);tty=os.open('/dev/tty'+str(vt),os.O_RDWR|os.O_NOCTTY|os.O_CLOEXEC)
    child=subprocess.Popen(command,env=env,cwd=root,stdin=tty,stdout=log,stderr=subprocess.STDOUT,pass_fds=desktop_fds,preexec_fn=child_tty)
    record_child()
  finally:
   if broker:broker.close()
   if launches:launches.close()
 report['status']=('OFFSCREEN_PROBE_FINISHED' if options.probe else 'VISIBLE_COMPARISON_FINISHED') if child.returncode==0 else 'COMPARISON_FAILED'
finally:
 if child is None or child.poll() is not None:
  fcntl.ioctl(fb,0x4f25)
  assert os.pwrite(fb,saved_frame,0)==768000
  fcntl.ioctl(fb,0x40444f36,struct.pack('17I',0,0,800,480,0,0,0,800,480,*([0]*8)));fcntl.ioctl(fb,0x4f25)
  if switched:
   os.close(tty);tty=os.open('/dev/tty'+str(vt),os.O_RDWR|os.O_NOCTTY|os.O_CLOEXEC);fcntl.ioctl(tty,0x4b3a,old_kd);fcntl.ioctl(console,0x5606,int(original[3:]));fcntl.ioctl(console,0x5607,int(original[3:]))
  mode.write_text(original_mode)
  os.close(fb);os.close(tty);os.close(console)
  report.update(vt_restored=active.read_text().strip()==original,mode_restored=mode.read_text()==original_mode,boot_unchanged=Path('/proc/sys/kernel/random/boot_id').read_text()==boot)
 (root/('owner-'+suffix+'.json')).write_text(json.dumps(report,indent=2)+'\n')
 if render_fd is not None:os.close(render_fd)
 if job_lock_fd is not None:os.close(job_lock_fd)
 (runtime/'active.json').unlink(missing_ok=True)
 subprocess.run([sys.executable,str(root/'owner_session.py'),'stop','--device-released'],check=True)
 archives=Path('/var/log/n810-pocket-native');archives.mkdir(mode=0o700,exist_ok=True)
 assert not archives.is_symlink() and archives.stat().st_uid==0
 archives.chmod(0o700)
 assert not (archives/root.name).exists()
 shutil.move(str(root),str(archives/root.name))
raise SystemExit(report.get('returncode',1))
