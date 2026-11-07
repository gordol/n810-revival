"""Run a complete standard-glxgears frame through the owned MBX service.

Mandatory exact-color GPU startup check, independent capture check, then real
application geometry at original resolution. Offscreen; no CPU rasterization,
no framebuffer writes, no reboot, no forced unload. Cleanup uses the owner's
verified same-boot reset after closing the rendering descriptor.
"""
from pathlib import Path
import fcntl, hashlib, json, os, struct, subprocess, sys, time
from bin_frame import jobs,unpack_jobs,whole_frame_job
from read_frame import summarize

root=Path(sys.argv[1]).resolve();source=Path(sys.argv[2]).resolve()
start_only='--start-only' in sys.argv[3:]
native_preflight='--preflight-native' in sys.argv[3:]
whole_frame='--whole-frame' in sys.argv[3:] or native_preflight
assert os.geteuid()==0 and os.uname().release=='5.15.224-n810-mbx-clock-wip1'
base=Path('/sys/module/n810_mbx_gpu_probe/parameters')
assert not base.exists()
out=root/('service-start' if start_only else 'service-result');out.mkdir(mode=0o700)
frame=source.read_bytes();description=summarize(frame)
prepared=source.with_suffix('.jobs')
packed=[] if start_only else (whole_frame_job(frame) if whole_frame else unpack_jobs(prepared.read_bytes(),frame) if prepared.exists() else list(jobs(frame)))
if native_preflight:
    ox,oy,tw,th,job=packed[0]
    header=list(struct.unpack_from('<6I',job));header[1]=3;header[5]=832
    packed=[(ox,oy,tw,th,struct.pack('<6I',*header)+job[24:])]
(out/'input.mbf').write_bytes(frame)
(out/'input.json').write_text(json.dumps(description,indent=2)+'\n')
report={'status':'STARTING','boot_before':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'hardware_glxgears_verified':False,'source_frame_sha256':hashlib.sha256(frame).hexdigest(),
        'width':description['width'],'height':description['height']}
mode=Path('/sys/class/graphics/fb0/update_mode')
assert mode.read_text().strip()=='1'
assert Path('/sys/devices/platform/omapdss/display0/enabled').read_text().strip()=='1'
def snapshot():
    result={}
    for p in base.iterdir():
        if p.name=='recover':continue
        try:result[p.name]=int(p.read_text())
        except (ValueError,PermissionError):pass
    return result

setter=subprocess.Popen(['/bin/sh','-c','printf "2\\n" > /sys/class/graphics/fb0/update_mode'])
setter.wait(timeout=5)
assert setter.returncode==0 and mode.read_text().strip()=='2'
fd=None;keep_service=False
try:
    subprocess.run([sys.executable,str(root/'run_probe.py'),'--mode','identity','--output',str(out/'identity'),
                    '--permit-global-clock-commit','--run'],check=True)
    identity=json.loads((out/'identity/receipt.json').read_text())
    verdict=json.loads((out/'identity/verdict.json').read_text())
    assert verdict['status']=='CLEAN_IDENTITY_RECEIPT'
    subprocess.run(['/sbin/rmmod','n810_mbx_gpu_probe'],check=True)
    build=json.loads((root/'BUILD.json').read_text())
    module=root/'payload/n810_mbx_gpu_probe.ko'
    assert hashlib.sha256(module.read_bytes()).hexdigest()==build['module_sha256']
    parameters=json.loads((root/'PROBE-SETTINGS.json').read_text())['effective']
    parameters.update(probe_mode=2,permit_global_commit=1,commit_samples=32,commit_pause_us=100)
    if native_preflight:
        parameters['gpu_frame_capacity_bytes']=832*description['height']
        parameters['gpu_frame_contiguous']=1
    for n in ('core_id','revision','product_id','part_number'):
        parameters['expected_'+n]=identity['parameters']['observed_'+n]
    fixed=bytearray(80)
    with open('/dev/fb0','rb',buffering=0) as f:fcntl.ioctl(f,0x4602,fixed,True)
    parameters['display_base'],parameters['display_bytes']=struct.unpack_from('=II',fixed,16)
    (out/'load-parameters.json').write_text(json.dumps(parameters,indent=2)+'\n')
    insert_started=time.monotonic()
    subprocess.run(['/sbin/insmod',str(module)]+[f'{k}={v}' for k,v in parameters.items()],check=True)
    report['service_insert_seconds']=time.monotonic()-insert_started
    loaded=snapshot();(out/'loaded.json').write_text(json.dumps(loaded,indent=2)+'\n')
    assert loaded['gpu_service_active']==loaded['gpu_service_baseline_verified']==1
    assert loaded['gpu_service_failed']==loaded['resident_fault']==0
    with open('/dev/n810-mbx-capture','rb',buffering=0) as f:cap=f.read(184385)
    assert len(cap)==184384
    (out/'baseline-capture.bin').write_bytes(cap)
    expected=(0xf800,0x07e0,0x001f,0xffff)
    pixels=struct.unpack_from('<1024H',cap,4160)
    assert all(p==expected[(i%32)//16+2*((i//32)//16)] for i,p in enumerate(pixels))
    assert cap[64:4160]==b'\x3c'*4096
    assert cap[6208:8256]==b'\x3c'*2048
    assert cap[8256:12352]==b'\xa5'*4096
    assert cap[12352:45120]==cap[45120:77888]
    assert cap[180288:184384]==b'\x5a'*4096
    report['verified_baseline_pixels']=1024
    if start_only:
        report['status']='PERSISTENT_GPU_SERVICE_READY_BASELINE_VERIFIED'
        keep_service=True
        raise SystemExit(0)
    fd=os.open('/dev/n810-mbx-render',os.O_RDWR|os.O_CLOEXEC)
    image=bytearray(description['width']*description['height']*2)
    started=time.monotonic()
    for ox,oy,tw,th,job in packed:
        assert os.write(fd,job)==len(job)
        tile=bytearray()
        expected_bytes=832*th if native_preflight else tw*th*2 if whole_frame else 2048
        row_bytes=832 if native_preflight else tw*2 if whole_frame else 64
        while len(tile)<expected_bytes:
            part=os.read(fd,expected_bytes-len(tile))
            if not part:raise RuntimeError('Truncated GPU tile')
            tile.extend(part)
        for y in range(th):
            dest=((oy+y)*description['width']+ox)*2
            image[dest:dest+tw*2]=tile[y*row_bytes:y*row_bytes+tw*2]
    report['render_seconds']=time.monotonic()-started
    report['gpu_jobs']=len(packed)
    report['nonblack_pixels']=sum(v!=0 for (v,) in struct.iter_unpack('<H',image))
    (out/'gpu-frame.rgb565').write_bytes(image)
    report['status']='GPU_FRAME_CAPTURED_REQUIRES_PIXEL_COMPARISON'
    if native_preflight:
        expected=(root/'expected-frame.rgb565').read_bytes()
        assert image==expected,'Native-stride pixels differ from verified full-frame baseline'
        report['native_pixels_bit_exact']=True
        report['status']='NATIVE_STRIDE_FRAME_BIT_EXACT_SERVICE_READY'
        keep_service=True
    print(json.dumps(report,indent=2),flush=True)
finally:
    if fd is not None:os.close(fd)
    if base.exists() and not keep_service:
        before=snapshot();(out/'before-stop.json').write_text(json.dumps(before,indent=2)+'\n')
        if before.get('lifetime_pinned'):
            (base/'recover').write_text('1\n')
        after=snapshot();(out/'after-stop.json').write_text(json.dumps(after,indent=2)+'\n')
        for k,v in {'lifetime_pinned':0,'resident_fault':0,'gpu_dma_stage':0,'enabled_references':0,
                    'held_clock_handles':0,'active_divider':1,'cleanup_phase':11}.items():assert after[k]==v,(k,after[k])
        subprocess.run(['/sbin/rmmod','n810_mbx_gpu_probe'],check=True)
    if not base.exists() or keep_service:mode.write_text('1\n')
    report['module_removed']=not base.exists()
    report['service_kept_for_live_application']=keep_service
    report['display_mode_after']=mode.read_text().strip()
    report['boot_after']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    (out/'kernel-log.txt').write_bytes(subprocess.check_output(['dmesg'])[-262144:])
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print('SERVICE_STOPPED',report['module_removed'],'DISPLAY_MODE',report['display_mode_after'],flush=True)
