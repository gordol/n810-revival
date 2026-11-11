"""Build original GPU probe for the verified5.15.224 kernel; no device actions."""
from pathlib import Path
import subprocess,json,base64,hashlib
root=Path(__file__).parent
module_root=root/'kernel'
candidate=root/'build-inputs'
# The portable encoder is the single source for both userspace and kernel builds.
for name in ('mbx_command_cache.h','mbx_window_images.h','mbx_texture_resident.h','mbx_owned_surface.h','mbx_surface_lease.h','channel_request.h','mbx_wire_resources.h','mbx_image_abi.h','mbx_vgp_wire.c','mbx_vgp_wire.h','mbx_packets.c','mbx_packets.h','mbx_context.c','mbx_context.h','mbx_vertex_program.c','mbx_vertex_program.h','mbx_vgp_transform.c','mbx_vgp_transform.h','mbx_vgp_batch.c','mbx_vgp_batch.h','mbx_gears_fixture.h','mbx_gears_frame.c','mbx_gears_frame_fixture.h','mbx_vgp_topology.c','mbx_vgp_topology.h','mbx_vgp_stream.c','mbx_vgp_stream.h','mbx_vgp_draw.c','mbx_vgp_draw.h','mbx_vgp_isa.c','mbx_vgp_isa.h'):
 (module_root/name).write_bytes((root/'common'/name).read_bytes())
inputs={p.name:base64.b64encode(p.read_bytes()).decode() for p in module_root.iterdir() if p.suffix in ('.c','.h') or p.name=='Makefile'}
for name in ('Module.symvers','candidate.config','binding-api-whitelist.txt'):inputs[name]=base64.b64encode((candidate/name).read_bytes()).decode()
guest=r'''
from pathlib import Path
import subprocess,tempfile,json,base64,hashlib,sys
files=json.load(sys.stdin)
import os
temp_root=Path('/Users/gordo/Development/n810/.build-pocket-owned-surface-kernel-tmp');temp_root.mkdir(exist_ok=True)
os.environ['TMPDIR']=str(temp_root)
tempfile.tempdir=str(temp_root)
source=Path('/Users/gordo/Development/n810/kernel/n810-5.15-maintained')
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()=='6bd43ee8d27b207c958808368251d55ec0475f9e'
assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip()
with tempfile.TemporaryDirectory(prefix='original-gpu224-') as d:
 p=Path(d);m=p/'module';m.mkdir();b=p/'build';b.mkdir()
 for n,v in files.items():(m/n).write_bytes(base64.b64decode(v,validate=True))
 # Verify every private descriptor offset against the pinned kernel source,
 # using the same ARM compiler/config as the module. Never infer this ABI.
 if (m/'omap_dma_pinned.h').exists():
  import re
  dma=(source/'drivers/dma/ti/omap-dma.c').read_text()
  virt=(source/'drivers/dma/virt-dma.h').read_text()
  structs=[]
  for name,body in [('virt_dma_desc',virt),('omap_sg',dma),('omap_desc',dma)]:
   definition=re.search(r'struct '+name+r' \{.*?\n\};',body,re.S).group()
   for old in ('virt_dma_desc','omap_sg','omap_desc'):definition=definition.replace('struct '+old+' ', 'struct verified_'+old+' ')
   structs.append(definition)
  checks=[]
  for actual,local,fields in [('virt_dma_desc','mbx_omap_vdesc',('tx','tx_result','node')),('omap_sg','mbx_omap_sg',('addr','en','fn','fi','ei','t2_desc','t2_desc_paddr')),('omap_desc','mbx_omap_desc',('vd','using_ll','dir','dev_addr','polled','fi','ei','es','ccr','clnk_ctrl','cicr','csdp','sglen','sg'))]:
   checks.append('static_assert(sizeof(struct verified_'+actual+')==sizeof(struct '+local+'));')
   for field in fields:checks.append('static_assert(offsetof(struct verified_'+actual+','+field+')==offsetof(struct '+local+','+field+'));')
  f=m/'n810_mbx_gpu_probe.c';f.write_text(f.read_text()+'\n'+'\n'.join(structs+checks)+'\n')
 config=(m/'candidate.config').read_text()
 import re
 config=re.sub(r'^CONFIG_UNUSED_KSYMS_WHITELIST=.*$', 'CONFIG_UNUSED_KSYMS_WHITELIST=\"'+str(m/'binding-api-whitelist.txt')+'\"',config,flags=re.M)
 (b/'.config').write_text(config)
 base=['make','-C',str(source),'O='+str(b),'ARCH=arm','CROSS_COMPILE=arm-linux-gnueabihf-','LOCALVERSION=']
 def run(args):
  r=subprocess.run(args,capture_output=True,timeout=180)
  if r.returncode:raise RuntimeError(r.stdout.decode(errors='replace')[-6000:]+'\n'.join(line for line in r.stderr.decode(errors='replace').splitlines() if 'error:' in line or 'mbx_dma_sink' in line)+r.stderr.decode(errors='replace')[-3000:])
 run(base+['olddefconfig','modules_prepare'])
 (b/'Module.symvers').write_bytes((m/'Module.symvers').read_bytes())
 assert (b/'include/config/kernel.release').read_text().strip()=='5.15.224-n810-mbx-clock-wip1'
 run(base+['M='+str(m),'KCFLAGS=-fstack-usage','modules'])
 stack_usage=[]
 for sf in m.rglob('*.su'):
  for line in sf.read_text().splitlines():
   fields=line.split('\t')
   if len(fields)>=3:stack_usage.append({'function':fields[0].split(':')[-1],'bytes':int(fields[1]),'kind':fields[2]})
 ko=m/'n810_mbx_gpu_probe.ko'
 versions=subprocess.check_output(['modprobe','--dump-modversions',str(ko)],text=True)
 exports={l.split()[1]:l.split()[0] for l in (b/'Module.symvers').read_text().splitlines()}
 for l in versions.splitlines():
  crc,name=l.split();assert exports.get(name)==crc,(name,crc,exports.get(name))
 info=subprocess.check_output(['modinfo',str(ko)],text=True)
 assert '5.15.224-n810-mbx-clock-wip1 mod_unload modversions ARMv6' in info
 print(json.dumps({'module':base64.b64encode(ko.read_bytes()).decode(),'info':info,'versions':versions,'source_commit':'6bd43ee8d27b207c958808368251d55ec0475f9e','all_import_crcs_match':True,'dma_descriptor_abi_verified':(m/'omap_dma_pinned.h').exists(),'stack_usage':sorted(stack_usage,key=lambda x:x['bytes'],reverse=True)}))
'''
r=subprocess.run(['/opt/homebrew/bin/limactl','shell','n810-builder','--','python3','-c',guest],input=json.dumps(inputs),capture_output=True,text=True,timeout=420)
if r.returncode:raise RuntimeError(r.stderr[-12000:])
j=json.loads(r.stdout);data=base64.b64decode(j.pop('module'));(root/'n810_mbx_gpu_probe.ko').write_bytes(data)
j.update(module_sha256=hashlib.sha256(data).hexdigest(),module_bytes=len(data),device_action=False,source_sha256={name:hashlib.sha256(base64.b64decode(value)).hexdigest() for name,value in inputs.items()})
(root/'BUILD.json').write_text(json.dumps(j,indent=2)+'\n');print(json.dumps(j,indent=2))
