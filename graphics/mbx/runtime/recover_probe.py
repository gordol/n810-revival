"""Explicit owner-managed GPU reset, failed-buffer capture, and normal unload."""
from pathlib import Path
import argparse,json,os,subprocess
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--run',action='store_true');a=p.parse_args()
base=Path('/sys/module/n810_mbx_gpu_probe/parameters')
def snapshot():
 return {n:int((base/n).read_text()) for n in json.loads((Path(__file__).parent/'PARAMETERS.json').read_text())}
if os.geteuid()!=0 or os.uname().release!='5.15.224-n810-mbx-clock-wip1':raise SystemExit('Root and exact kernel required')
before=snapshot()
for k,v in {'resident_fault':1,'lifetime_pinned':1,'gpu_dma_stage':3,'active_divider':2,'enabled_references':3,'recovery_attempted':0}.items():
 if before.get(k)!=v:raise SystemExit('Recovery precondition mismatch: '+k)
if not (base/'recover').exists():raise SystemExit('Owner recovery interface absent')
if not a.run:print('PLAN: verified owner reset, failure capture, regular unload. No reboot.');raise SystemExit(0)
a.output.mkdir(mode=0o700)
(a.output/'before.json').write_text(json.dumps(before,indent=2)+'\n')
(base/'recover').write_text('1\n')
after=snapshot();(a.output/'after.json').write_text(json.dumps(after,indent=2)+'\n')
checks={'recovery_complete':1,'recovery_error':0,'recovery_tables_cleared':1,'recovery_mmu_control':0,
 'resident_fault':0,'lifetime_pinned':0,'gpu_dma_stage':0,'enabled_references':0,'held_clock_handles':0,
 'active_divider':1,'cleanup_phase':11,'reset_asserted_verified':1,'observed_fclk':0,'observed_iclk':0,'observed_select':1}
for k,v in checks.items():
 if after.get(k)!=v:raise SystemExit('Recovery not verified: '+k)
with open('/dev/n810-mbx-capture','rb',buffering=0) as f:blob=f.read(184385)
if len(blob)!=184384:raise SystemExit('Wrong failed-command capture size')
(a.output/'failed-command-capture.bin').write_bytes(blob)
(a.output/'kernel-log.txt').write_bytes(subprocess.check_output(['dmesg'])[-262144:])
subprocess.run(['/sbin/rmmod','n810_mbx_gpu_probe'],check=True)
if base.exists():raise SystemExit('Normal unload not completed')
(a.output/'verified.json').write_text(json.dumps({'status':'OWNER_RESET_CAPTURE_AND_NORMAL_UNLOAD_VERIFIED','boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'gpu_rendering_verified':False},indent=2)+'\n')
print('Owner reset, stable failed-command capture, DMA/clock cleanup and normal unload verified. No reboot.',flush=True)
