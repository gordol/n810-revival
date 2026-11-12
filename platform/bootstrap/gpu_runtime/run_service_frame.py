"""Start the bounded GPU vertex service after identity and persistent render proof."""
from pathlib import Path
import hashlib,json,os,sys,subprocess,fcntl,struct,time

def start_service(directory):
 root=Path(directory).resolve()
 started=time.monotonic();last=started;timing={}
 def stamp(name):
  nonlocal last
  now=time.monotonic();timing[name]=now-last;last=now
 assert os.geteuid()==0 and os.uname().release=='5.15.224-n810-mbx-clock-wip1'
 base=Path('/sys/module/n810_mbx_gpu_probe/parameters');assert not base.exists()
 assert Path('/sys/class/power_supply/tahvo-charger/online').read_text().strip()=='1'
 assert Path('/sys/devices/platform/omapdss/display0/enabled').read_text().strip()=='1'
 mode=Path('/sys/class/graphics/fb0/update_mode');assert mode.read_text().strip() in ('1','2')
 module=root/'payload/n810_mbx_gpu_probe.ko';build=json.loads((root/'BUILD.json').read_text())
 assert hashlib.sha256(module.read_bytes()).hexdigest()==build['module_sha256']
 mode.write_text('2\n')
 stamp('checks_and_manual_mode')
 from run_probe import main as run_identity
 run_identity(['--mode','identity','--output',str(root/'service-identity'),'--permit-global-clock-commit','--run'])
 stamp('identity_runner')
 ident=json.loads((root/'service-identity/receipt.json').read_text())
 assert json.loads((root/'service-identity/verdict.json').read_text())['status']=='CLEAN_IDENTITY_RECEIPT'
 subprocess.run(['/sbin/rmmod','n810_mbx_gpu_probe'],check=True)
 stamp('identity_verification_and_unload')
 p=json.loads((root/'PROBE-SETTINGS.json').read_text())['effective']
 value=os.environ.get('N810_MBX_VERIFY_BURST','0');assert value in ('0','1');p['gpu_verify_burst']=int(value)
 value=os.environ.get('N810_MBX_VERIFY_UPLOAD_BURST','0');assert value in ('0','1');p['gpu_verify_upload_burst']=int(value)
 p.update(gpu_window_images=1,gpu_desktop_target=1,gpu_frame_capacity_bytes=768000,gpu_readonly_frame_cache=1,gpu_texture_residency=1,gpu_capture_success=0,probe_mode=3,permit_global_commit=1,commit_samples=32,commit_pause_us=100,vgp_test_translate=0)
 if 'N810_MBX_RESET_PAUSE_US' in os.environ:
  pause=int(os.environ['N810_MBX_RESET_PAUSE_US']);assert 1000<=pause<=500000
  p['gpu_reset_pause_us']=pause
 if os.environ.get('N810_MBX_STREAMING_FRAME')=='1':p.update(gpu_frame_streaming=1,gpu_frame_shared=1)
 if os.environ.get('N810_MBX_EXCLUSIVE_SURFACE')=='1':p.update(gpu_frame_shared=0,gpu_frame_buffers=1)
 for option,parameter in (('N810_MBX_PREPARED_COMMANDS','gpu_prepared_commands'),('N810_MBX_WIRE_REPLAY','gpu_wire_replay'),('N810_MBX_FIFO_BATCH','gpu_fifo_batch'),('N810_MBX_PROFILE_SLEEPS','gpu_profile_sleeps')):
  if option in os.environ:
   assert os.environ[option] in ('0','1')
   p[parameter]=int(os.environ[option])
 if 'N810_MBX_FIFO_SPIN_POLLS' in os.environ:
  spin=int(os.environ['N810_MBX_FIFO_SPIN_POLLS']);assert 0<=spin<=32
  p['gpu_fifo_spin_polls']=spin
 if os.environ.get('N810_MBX_DOUBLE_IMAGE')=='1':p['gpu_frame_buffers']=2
 if 'N810_MBX_CONTROL_SPIN_POLLS' in os.environ:
  control_spin=int(os.environ['N810_MBX_CONTROL_SPIN_POLLS']);assert 0<=control_spin<=128
  p['gpu_control_spin_polls']=control_spin
 if 'N810_MBX_RASTER_PAUSE_US' in os.environ:
  raster_pause=int(os.environ['N810_MBX_RASTER_PAUSE_US']);assert raster_pause==0 or 100<=raster_pause<=1000
  p['gpu_raster_pause_us']=raster_pause
 for n in ('core_id','revision','product_id','part_number'):p['expected_'+n]=ident['parameters']['observed_'+n]
 fixed=bytearray(80)
 with open('/dev/fb0','rb',buffering=0) as f:fcntl.ioctl(f,0x4602,fixed,True)
 p['display_base'],p['display_bytes']=struct.unpack_from('=II',fixed,16)
 (root/'service-load-parameters.json').write_text(json.dumps(p,indent=2)+'\n')
 stamp('prepare_service_parameters')
 subprocess.run(['/sbin/insmod',str(module)]+[f'{k}={v}' for k,v in p.items()],check=True)
 stamp('service_insmod')
 for k,v in {'gpu_service_active':'1','gpu_service_baseline_verified':'1','gpu_service_failed':'0'}.items():assert (base/k).read_text().strip()==v,k
 if p.get('gpu_frame_buffers')==2:
  from verify_images import verify_images
  verify_images(root)
  stamp('two_image_render_proof')
 if os.environ.get('N810_MBX_TEMPLATE_PROOF')=='1':
  from verify_template import verify_template
  verify_template(root)
  stamp('template_render_proof')
 mode.write_text('1\n')
 stamp('ready_checks_and_auto_mode');timing['total_seconds']=time.monotonic()-started
 (root/'service-startup-timing.json').write_text(json.dumps(timing,indent=2)+'\n')
 print('GPU_VERTEX_SERVICE_READY',flush=True)

if __name__=="__main__":start_service(sys.argv[1])
