"""Drain display updates, release the owned GPU service, restore display."""
from pathlib import Path
import json,os,subprocess,sys,time
assert os.geteuid()==0
base=Path('/sys/module/n810_mbx_gpu_probe/parameters')
out=Path(sys.argv[1]);out.mkdir(mode=0o700)
# X releases imported mappings when the application connection closes.
# File references keep the exclusive GPU owner alive until then.
owner=base/'gpu_service_opened'
deadline=time.monotonic()+8
while owner.exists() and owner.read_text().strip() in ('Y','1'):
    if time.monotonic()>deadline:raise RuntimeError('GPU/X mapping still owned; retain current display mode')
    time.sleep(.05)
mode=Path('/sys/class/graphics/fb0/update_mode')
assert mode.read_text().strip() in ('1','2')
if mode.read_text().strip()=='1':
    setter=subprocess.Popen(['/bin/sh','-c','printf "2\\n" > /sys/class/graphics/fb0/update_mode'])
    setter.wait(timeout=5);assert setter.returncode==0
def snapshot():
    def scalar(p):
        value=p.read_text().strip()
        return {'Y':1,'N':0}[value] if value in ('Y','N') else int(value)
    return {p.name:scalar(p) for p in base.iterdir() if p.name!='recover'}
try:
    receipt=json.loads((Path(__file__).parent/'service-identity/receipt.json').read_text())
    original_divider=receipt.get('initial_divider',1)
    assert type(original_divider) is int and original_divider in (1,2)
    before=snapshot();(out/'before.json').write_text(json.dumps(before,indent=2)+'\n')
    (base/'recover').write_text('1\n')
    after=snapshot();(out/'after.json').write_text(json.dumps(after,indent=2)+'\n')
    for k,v in {'recovery_complete':1,'recovery_error':0,'lifetime_pinned':0,'resident_fault':0,
                'gpu_dma_stage':0,'enabled_references':0,'held_clock_handles':0,'active_divider':original_divider,'cleanup_phase':11}.items():assert after[k]==v,(k,after[k])
    assert after['observed_select']==receipt['parameters']['observed_select']
    (out/'kernel-log.txt').write_bytes(subprocess.check_output(['dmesg'])[-262144:])
    if os.environ.get('N810_MBX_CAPTURE_FINAL')=='1' and (base/'gpu_capture_valid').read_text().strip()=='1':
        with open('/dev/n810-mbx-capture','rb',buffering=0) as f:data=f.read(2*1024*1024)
        assert 64<len(data)<2*1024*1024
        (out/'capture.bin').write_bytes(data)
    subprocess.run(['/sbin/rmmod','n810_mbx_gpu_probe'],check=True)
finally:
    if not base.exists():mode.write_text('1\n')
