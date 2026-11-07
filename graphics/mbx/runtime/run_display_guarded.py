"""Offscreen GPU iteration with no in-flight LCD update during clock commits."""
from pathlib import Path
import os,sys,subprocess,json
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
from judge_probe import CLEAN
assert os.geteuid()==0
mode=Path('/sys/class/graphics/fb0/update_mode')
assert Path('/sys/devices/platform/omapdss/display0/enabled').read_text().strip()=='1'
assert mode.read_text().strip()=='1'
assert not Path('/sys/module/n810_mbx_gpu_probe').exists()
report={'boot_before':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'display_mode_before':1}
# The existing setter drains the current transfer and cancels its worker. A
# timeout aborts BEFORE GPU loading; do not guess at a display bus semaphore.
setter=subprocess.Popen(['/bin/sh','-c','printf "2\\n" > /sys/class/graphics/fb0/update_mode'])
try:
 setter.wait(timeout=5)
except subprocess.TimeoutExpired:
 report['status']='DISPLAY_DRAIN_BLOCKED_NO_GPU_TEST'
 report['display_setter_pid']=setter.pid
 (root/'display-guard.json').write_text(json.dumps(report,indent=2)+'\n')
 raise RuntimeError('Display update did not drain; GPU test was not started')
assert setter.returncode==0 and mode.read_text().strip()=='2'
report['display_drained']=True
try:
 run=subprocess.run([sys.executable,str(root/'run_once.py'),str(root)])
 report['probe_exit']=run.returncode
 if Path('/sys/module/n810_mbx_gpu_probe').exists():
  base=Path('/sys/module/n810_mbx_gpu_probe/parameters')
  if int((base/'resident_fault').read_text())==1:
   recovery=subprocess.run([sys.executable,str(root/'recover_probe.py'),'--output',str(root/'recovery-result'),'--run'])
   report['recovery_exit']=recovery.returncode
   if recovery.returncode or Path('/sys/module/n810_mbx_gpu_probe').exists():raise RuntimeError('Retained GPU not safely released; display mode preserved')
  else:
   for name,want in (CLEAN|{'gpu_dma_stage':0}).items():
    assert int((base/name).read_text())==want,('Unverified clean removal',name)
   subprocess.run(['/sbin/rmmod','n810_mbx_gpu_probe'],check=True)
   report['clean_probe_removed']=True
finally:
 if not Path('/sys/module/n810_mbx_gpu_probe').exists():
  mode.write_text('1\n')
  report['display_mode_after']=mode.read_text().strip()
 report['boot_after']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
 (root/'display-guard.json').write_text(json.dumps(report,indent=2)+'\n')
raise SystemExit(run.returncode)
