"""Explicit fresh-image graphics owner. Start/stop without reboot or force unload."""
from pathlib import Path
import argparse,json,os,subprocess,sys,fcntl
p=Path(__file__).resolve().parent
base=Path('/sys/module/n810_mbx_gpu_probe/parameters')
mode=Path('/sys/class/graphics/fb0/update_mode')
boot=Path('/proc/sys/kernel/random/boot_id')
vt=Path('/sys/class/tty/tty0/active')
panel=Path('/sys/devices/platform/omapdss/display0/enabled')
def pocket():
 result=[]
 for d in Path('/proc').iterdir():
  if not d.name.isdecimal():continue
  try:
   args=(d/'cmdline').read_bytes().split(b'\0')
   if any(name in args for name in (
      b'/usr/local/lib/n810-pocket/console_helper.py',
      b'/usr/local/libexec/n810-pocket-session',
      b'/usr/local/lib/pocket/bootstrap_desktop.py',
      b'/usr/local/share/pocket/graphics/nokia.py')):
    result.append(int(d.name))
  except OSError:pass
 return result

def check_audio_owner():
 # The old audio setup could hard-lock the tablet. The boot service now checks
 # the corrected McBSP2 configuration before allowing PCM. Keep rejecting an
 # unapproved audio driver, but permit the verified audio and GPU paths together.
 if Path('/sys/module/snd_soc_n810').exists():
  subprocess.run(['/usr/local/sbin/n810-audio','pcm-status'],check=True)

def main():
 a=argparse.ArgumentParser(description=__doc__);a.add_argument('action',choices=['start','stop']);a.add_argument('--device-released',action='store_true');args=a.parse_args()
 assert args.device_released and os.geteuid()==0
 statefile=p/'owner-state.json'
 if args.action=='start':
  assert not statefile.exists() and not base.exists()
  # The pinned external module sets bit12; reject every fault/warning bit.
  assert int(Path('/proc/sys/kernel/tainted').read_text()) in (0,1<<12)
  check_audio_owner()
  assert not pocket(),'Preserve Pocket: handoff must already have it stopped'
  assert panel.read_text().strip() in ('0','1') and mode.read_text().strip()=='1'
  s=dict(boot=boot.read_text(),vt=vt.read_text(),mode=mode.read_text(),panel=panel.read_text())
  statefile.write_text(json.dumps(s,indent=2)+'\n')
  if s['panel'].strip()=='0':
   with open('/dev/fb0','rb',buffering=0) as fb:fcntl.ioctl(fb,0x4611,0)
   assert panel.read_text().strip()=='1'
  os.environ.update(N810_MBX_RESET_PAUSE_US='1000',N810_MBX_STREAMING_FRAME='1',N810_MBX_EXCLUSIVE_SURFACE='1',N810_MBX_WIRE_REPLAY='1',N810_MBX_FIFO_SPIN_POLLS='16',N810_MBX_RASTER_PAUSE_US='0',N810_MBX_VERIFY_BURST='1',N810_MBX_VERIFY_UPLOAD_BURST='1')
  from run_service_frame import start_service
  try:start_service(p)
  except BaseException:
   # No guessed recovery on a failed start.
   if not base.exists():
    mode.write_text(s['mode'])
   raise
  assert boot.read_text()==s['boot'] and vt.read_text()==s['vt']
  print('OWNED_GPU_READY_NO_REBOOT',flush=True)
 else:
  s=json.loads(statefile.read_text());assert boot.read_text()==s['boot']
  for n in ['gpu_service_failed','resident_fault','cleanup_error','gpu_error']:
   assert (base/n).read_text().strip()=='0','Fault retained; no automatic recovery'
  assert (base/'gpu_service_opened').read_text().strip() in ('0','N')
  subprocess.run([sys.executable,str(p/'stop_service.py'),str(p/'owner-stop')],check=True,timeout=45)
  assert not base.exists()
  mode.write_text(s['mode'])
  if s['panel'].strip()=='0':
   with open('/dev/fb0','rb',buffering=0) as fb:fcntl.ioctl(fb,0x4611,4)
  report=dict(module_unloaded=True,boot_unchanged=boot.read_text()==s['boot'],vt_unchanged=vt.read_text()==s['vt'],panel_unchanged=panel.read_text()==s['panel'],pocket_still_stopped=not pocket())
  (p/'owner-restored.json').write_text(json.dumps(report,indent=2)+'\n');assert all(report.values()),report
  print(json.dumps(report))
if __name__=='__main__':main()
