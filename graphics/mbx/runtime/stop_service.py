"""Drain display updates, release the owned GPU service, restore display."""
from pathlib import Path
import json,os,subprocess,sys
assert os.geteuid()==0
base=Path('/sys/module/n810_mbx_gpu_probe/parameters')
out=Path(sys.argv[1]);out.mkdir(mode=0o700)
mode=Path('/sys/class/graphics/fb0/update_mode')
assert mode.read_text().strip()=='1'
setter=subprocess.Popen(['/bin/sh','-c','printf "2\\n" > /sys/class/graphics/fb0/update_mode'])
setter.wait(timeout=5);assert setter.returncode==0
def snapshot():
    return {p.name:int(p.read_text()) for p in base.iterdir() if p.name!='recover'}
try:
    before=snapshot();(out/'before.json').write_text(json.dumps(before,indent=2)+'\n')
    (base/'recover').write_text('1\n')
    after=snapshot();(out/'after.json').write_text(json.dumps(after,indent=2)+'\n')
    for k,v in {'recovery_complete':1,'recovery_error':0,'lifetime_pinned':0,'resident_fault':0,
                'gpu_dma_stage':0,'enabled_references':0,'held_clock_handles':0,'active_divider':1,'cleanup_phase':11}.items():assert after[k]==v,(k,after[k])
    (out/'kernel-log.txt').write_bytes(subprocess.check_output(['dmesg'])[-262144:])
    subprocess.run(['/sbin/rmmod','n810_mbx_gpu_probe'],check=True)
finally:
    if not base.exists():mode.write_text('1\n')
