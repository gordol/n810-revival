"""Bounded standard Debian glxgears on the physical display; restore its VT."""
from pathlib import Path
import os,sys,subprocess,time,signal,json,hashlib
root=Path(sys.argv[1]).resolve()
assert os.geteuid()==0
assert os.uname().release=='5.15.224-n810-mbx-clock-wip1'
assert not Path('/sys/module/n810_mbx_gpu_probe').exists()
assert not Path('/tmp/.X1-lock').exists()
assert not Path('/tmp/.X11-unix/X1').exists()
assert not any(x in os.environ for x in ('LIBGL_ALWAYS_SOFTWARE','MESA_LOADER_DRIVER_OVERRIDE','GALLIUM_DRIVER'))
backlight=Path('/sys/class/backlight/n810-backlight/brightness')
if not backlight.exists():backlight=next(Path('/sys/class/backlight').glob('*/brightness'))
original_brightness=backlight.read_text().strip()
original=Path('/sys/class/tty/tty0/active').read_text().strip()
assert original in ('tty1','tty8'),original
for path in Path('/proc').glob('[0-9]*/stat'):
 try:fields=path.read_text().rsplit(')',1)[1].split()
 except (FileNotFoundError,ProcessLookupError):continue
 assert int(fields[4])!=os.makedev(4,7),'VT7 already has an owner'
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
subprocess.run(['xauth','-f',str(authority),'add',':1','.',os.urandom(16).hex()],check=True)
authority.chmod(0o600)
env=dict(os.environ,DISPLAY=':1',XAUTHORITY=str(authority),GALLIUM_DRIVER='softpipe')
gears_env=dict(env,LD_LIBRARY_PATH=str(root/'lib'),N810_MBX_CAPTURE=str(root/'gears-frame.mbf'))
assert not (root/'gears-frame.mbf').exists()
report=dict(boot_id=boot,kernel=os.uname().release,original_vt=original,display=':1',server_driver='fbdev',software_override=True,package_sha256=hashlib.sha256(package.read_bytes()).hexdigest())
x=None;g=None;server_pid=None
try:
 with (root/'x-launch.log').open('wb') as log:
  x=subprocess.Popen(['openvt','-c','7','-s','-w','--','/usr/lib/xorg/Xorg',':1','vt7','-extension','GLX','-keeptty','-nolisten','tcp','-noreset','-config',str(config),'-auth',str(authority),'-logfile',str(root/'Xorg.log')],env=env,stdout=log,stderr=subprocess.STDOUT)
  for _ in range(160):
   if Path('/tmp/.X11-unix/X1').exists():break
   if x.poll() is not None:raise RuntimeError('X server exited; see x-launch.log and Xorg.log')
   time.sleep(.25)
  else:raise RuntimeError('X startup timeout')
  server_pid=int(Path('/tmp/.X1-lock').read_text())
  assert str(config).encode() in Path(f'/proc/{server_pid}/cmdline').read_bytes()
  with (root/'glxgears.txt').open('wb') as output:
   g=subprocess.Popen(['stdbuf','-oL',str(gears[0]),'-info','-geometry','400x400+200+40'],env=gears_env,stdout=output,stderr=subprocess.STDOUT)
   deadline=time.monotonic()+180
   while 'FPS' not in (root/'glxgears.txt').read_text():
    if g.poll() is not None:
     report['gears_exit_code']=g.returncode
     raise RuntimeError('glxgears exited before producing frames: '+str(g.returncode))
    if time.monotonic()>deadline:raise RuntimeError('No measured gears frames within180seconds')
    time.sleep(1)
   assert Path('/sys/class/tty/tty0/active').read_text().strip()=='tty7'
   assert Path('/sys/class/graphics/fb0/stride').read_text().strip()=='1600'
   with open('/dev/fb0','rb',buffering=0) as fb:frame=fb.read(800*480*2)
   assert len(frame)==800*480*2
   assert len(set(frame))>4,'No visible rendered content'
   (root/'gears.rgb565').write_bytes(frame)
   print('VISIBLE_GEARS_CAPTURED',flush=True)
   time.sleep(6)
   with open('/dev/fb0','rb',buffering=0) as fb:second=fb.read(800*480*2)
   (root/'gears-second.rgb565').write_bytes(second)
   report['two_captures_differ']=second!=frame
   g.terminate();g.wait(timeout=8);g=None
  report['gears_log']=(root/'glxgears.txt').read_text()
  report['glxinfo']='Not run in this software-only follow-up; renderer identity is in glxgears -info output'
  report['hardware_acceleration_confirmed']=False
  report['mesa_library_sha256']=hashlib.sha256((root/'lib/libGL.so.1').read_bytes()).hexdigest()
  report['mesa_geometry_capture_exists']=(root/'gears-frame.mbf').exists()
  assert report['mesa_geometry_capture_exists'], 'Mesa did not capture the application geometry'
  report['status']='STANDARD_GLXGEARS_MESA_REFERENCE_CAPTURED_NOT_GPU'
finally:
 if g is not None and g.poll() is None:
  g.terminate()
  try:g.wait(timeout=8)
  except subprocess.TimeoutExpired:g.kill();g.wait()
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
 subprocess.run(['chvt',original.removeprefix('tty')],check=True)
 backlight.write_text(original_brightness+'\n')
 report['restored_brightness']=backlight.read_text().strip()
 report['restored_vt']=Path('/sys/class/tty/tty0/active').read_text().strip()
 report['boot_unchanged']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()==boot
 report['session_preferences_changed']=session.read_bytes()!=saved_preferences
 report['session_sha256_before']=hashlib.sha256(saved_preferences).hexdigest()
 report['session_sha256_after']=hashlib.sha256(session.read_bytes()).hexdigest()
 (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')
 print('DISPLAY_RESTORED',report['restored_vt'],flush=True)
