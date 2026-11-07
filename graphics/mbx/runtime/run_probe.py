"""Prepared attended runner. Default prints a plan; --run performs ONE insertion.
No boot, retry, force unload, radio changes, or automatic module removal.
"""
import argparse,hashlib,json,os,re,subprocess,sys,time,fcntl,struct
from pathlib import Path
from judge_probe import judge
from judge_probe import RELEASE
ROOT=Path(__file__).resolve().parent
def budget(name,baseline):
    raw=os.environ.get(name,str(baseline))
    if not raw.isascii() or not raw.isdecimal() or not 1<=int(raw)<=baseline:
        raise ValueError(name+' may only tighten its positive baseline')
    return int(raw)
LOG_LIMIT=budget('N810_GPU_KERNEL_LOG_BYTES',262144)
SCALAR_LIMIT=budget('N810_GPU_SCALAR_BYTES',256)

def drain(fd):
    chunks=[];total=0;previous=None;lost=False
    while True:
        try:raw=os.read(fd,16384)
        except BlockingIOError:break
        except OSError:lost=True;break
        if not raw:break
        total+=len(raw)
        if total>LOG_LIMIT:lost=True;break
        chunks.append(raw)
        try:
            seq=int(raw.split(b';',1)[0].split(b',')[1])
            if previous is not None and seq!=previous+1:lost=True
            previous=seq
        except (ValueError,IndexError):lost=True
    return b''.join(chunks),not lost

def parse_initial(log):
    rows=re.findall(r'n810_mbx_gpu_probe: initial fclk=([0-9a-f]+) iclk=([0-9a-f]+) idle=[0-9a-f]+ select=([0-9a-f]+)',log)
    if len(rows)!=1:raise ValueError('missing or repeated initial snapshot')
    return tuple(int(v,16) for v in rows[0])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=('identity','fill'),required=True)
    p.add_argument('--module',type=Path,default=ROOT/'payload/n810_mbx_gpu_probe.ko')
    p.add_argument('--identity-receipt',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--run',action='store_true')
    p.add_argument('--permit-global-clock-commit',action='store_true')
    a=p.parse_args()
    manifest=json.loads((ROOT/'MANIFEST.json').read_text())
    pin=manifest['files']['payload/n810_mbx_gpu_probe.ko']['sha256']
    data=a.module.read_bytes()
    if len(data)>1048576 or hashlib.sha256(data).hexdigest()!=pin:raise ValueError('module pin mismatch')
    settings=json.loads((ROOT/'PROBE-SETTINGS.json').read_text())['effective']
    parameters=settings|{'probe_mode':int(a.mode=='fill')}
    if not a.permit_global_clock_commit:raise ValueError('explicit global clock commit selection required')
    parameters.update(permit_global_commit=1,commit_samples=budget('N810_GPU_COMMIT_SAMPLES',32),commit_pause_us=budget('N810_GPU_COMMIT_PAUSE_US',100))
    if a.mode=='fill':
        if struct.calcsize('P')!=4:raise ValueError('framebuffer ABI requires native32bit Nokia runner')
        display_ranges=[]
        for fb in sorted(Path('/sys/class/graphics').glob('fb[0-9]*')):
            with open('/dev/'+fb.name,'rb',buffering=0) as display:
                fixed=bytearray(80);fcntl.ioctl(display,0x4602,fixed,True)
            start,length=struct.unpack_from('=II',fixed,16)
            if length:
                if not start or start+length>2**32:raise ValueError('invalid framebuffer physical range')
                display_ranges.append((start,start+length))
        if not display_ranges:raise ValueError('no physical framebuffer allocation to exclude')
        parameters['display_base']=min(x[0] for x in display_ranges)
        parameters['display_bytes']=max(x[1] for x in display_ranges)-parameters['display_base']
        if not a.identity_receipt:raise ValueError('fill requires the successful identity receipt')
        raw=a.identity_receipt.read_text()
        if len(raw)>32768:raise ValueError('receipt too large')
        receipt=json.loads(raw);verdict=judge(receipt,pin,settings)
        if verdict['status']!='CLEAN_IDENTITY_RECEIPT':raise ValueError('identity-only receipt required')
        for suffix in ('core_id','revision','product_id','part_number'):
            parameters['expected_'+suffix]=receipt['parameters']['observed_'+suffix]
    argv=['/sbin/insmod',str(a.module.resolve())]+[f'{k}={v}' for k,v in parameters.items()]
    if not a.run:
        print(json.dumps(dict(status='PLAN_ONLY',command=argv,kernel_required=RELEASE,radio_or_boot_action=False),indent=2));return
    if os.geteuid()!=0 or os.uname().release!=RELEASE:raise ValueError('root and exact experimental kernel required')
    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if a.mode=='fill' and receipt.get('boot_id')!=boot_id:raise ValueError('identity receipt belongs to a different boot')
    if b'nokia,n810\0' not in Path('/proc/device-tree/compatible').read_bytes():raise ValueError('not an N810')
    if Path('/sys/module/n810_mbx_gpu_probe').exists():raise ValueError('probe already resident; no retry/removal attempted')
    if not a.output:raise ValueError('--output is required and must be a new directory')
    a.output.mkdir(mode=0o700,parents=False,exist_ok=False)
    names=json.loads((ROOT/'PARAMETERS.json').read_text())
    fd=os.open('/dev/kmsg',os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        os.lseek(fd,0,os.SEEK_END)
        started=time.monotonic()
        # Deliberately no timeout/kill/retry: a stuck kernel requires attended recovery.
        done=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        elapsed=time.monotonic()-started
        log,complete=drain(fd)
    finally:os.close(fd)
    (a.output/'new-kmsg.log').write_bytes(log)
    (a.output/'loader-output.txt').write_bytes(done.stdout+done.stderr)
    values={};missing=[]
    for name in names:
        try:
            with (Path('/sys/module/n810_mbx_gpu_probe/parameters')/name).open() as f:value=f.read(SCALAR_LIMIT+1)
            if len(value)>SCALAR_LIMIT:raise ValueError('oversize scalar')
            values[name]=int(value.strip(),0)
        except (OSError,ValueError):missing.append(name)
    receipt=dict(kernel_release=os.uname().release,module_sha256=pin,boot_id=boot_id,mode=a.mode,
                 loader_exit_code=done.returncode,elapsed_seconds=elapsed,parameters=values,
                 capture_limits=dict(log_bytes=LOG_LIMIT,scalar_bytes=SCALAR_LIMIT),
                 missing_parameters=missing,log_complete=complete and not missing,
                 initial_final_gates_match=False,initial_final_selector_match=False,
                 log_sha256=hashlib.sha256(log).hexdigest(),command=argv,
                 kernel_log_complete=complete,module_present_after_load=Path('/sys/module/n810_mbx_gpu_probe').exists())
    try:
        fclk,iclk,select=parse_initial(log.decode(errors='replace'))
        receipt['initial_final_gates_match']=values.get('observed_fclk')==fclk and values.get('observed_iclk')==iclk
        receipt['initial_final_selector_match']=values.get('observed_select')==select
    except ValueError:receipt['log_complete']=False
    (a.output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if done.returncode:
        from check_abort import judge_abort
        verdict=judge_abort(receipt,log,pin)
        (a.output/'verdict.json').write_text(json.dumps(verdict,indent=2)+'\n')
        print(json.dumps(verdict,indent=2))
        raise SystemExit(2)  # failed operation, clean release; never auto-retry
    if a.mode=='fill' and values.get('gpu_capture_valid')==1:
        with open('/dev/n810-mbx-capture','rb',buffering=0) as f:blob=f.read(184385)
        (a.output/'capture.bin').write_bytes(blob)
    verdict=judge(receipt,pin,settings)
    if a.mode=='fill':
        from check_capture import validate
        verdict['capture']=validate(blob)
    (a.output/'verdict.json').write_text(json.dumps(verdict,indent=2)+'\n')
    print(json.dumps(verdict,indent=2))
    print('Probe remains loaded. After reviewing the complete clean receipt, normal removal is: /sbin/rmmod n810_mbx_gpu_probe')
if __name__=='__main__':main()
