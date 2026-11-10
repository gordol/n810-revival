"""Build isolated Mesa candidate; no device actions or production replacement."""
from pathlib import Path
import subprocess,json,base64,hashlib,os
p=Path(__file__).resolve().parent
pin=json.loads((p/'build-inputs/mesa-source.json').read_text())
archive=Path(os.environ.get('MBX_MESA_SOURCE_ARCHIVE',str(p.parents[5]/'outputs/shared-gpu-scene-20261108'/pin['archive'])))
assert hashlib.sha256(archive.read_bytes()).hexdigest()==pin['sha256'], 'Mesa source archive digest mismatch'
build_root=os.environ.get('MBX_MESA_BUILD_ROOT','/Users/gordo/Development/n810/.build-pocket-owned-surface-mesa-20261108')
assert Path(build_root).is_absolute()
remote=str(Path(build_root)/'source-base.tar.gz')
subprocess.run(['/opt/homebrew/bin/limactl','shell','n810-builder','--','mkdir','-p',str(Path(remote).parent)],check=True)
subprocess.run(['/opt/homebrew/bin/limactl','copy',str(archive),'n810-builder:'+remote],check=True)
sysroot_archive=Path(os.environ.get('MBX_MESA_SYSROOT_ARCHIVE',str(archive.parent/pin['sysroot']['archive'])))
assert hashlib.sha256(sysroot_archive.read_bytes()).hexdigest()==pin['sysroot']['sha256']
subprocess.run(['/opt/homebrew/bin/limactl','copy',str(sysroot_archive),'n810-builder:'+str(Path(remote).with_name('sysroot.tar.gz'))],check=True)
files={'src/gallium/drivers/softpipe/'+f.name:base64.b64encode(f.read_bytes()).decode() for f in (p/'mesa').iterdir() if f.is_file()}
files['src/gallium/drivers/softpipe/mbx_owned_surface.h']=base64.b64encode((p/'common/mbx_owned_surface.h').read_bytes()).decode()
for source_file in (p/'common').iterdir():
 if source_file.suffix in ('.c','.h'):files['src/gallium/auxiliary/draw/'+source_file.name]=base64.b64encode(source_file.read_bytes()).decode()
for name in ('mbx_vgp_shader.h','mbx_affine_uv.h'):files['src/gallium/auxiliary/draw/'+name]=base64.b64encode((p/'mesa'/name).read_bytes()).decode()
guest=r'''
from pathlib import Path
import shutil,subprocess,json,sys,base64
payload=json.load(sys.stdin);files=payload['files'];pin=payload['pin'];dest=Path(payload['build_root']);dest.mkdir(exist_ok=True)
import hashlib,tarfile
archive=dest/'source-base.tar.gz';assert hashlib.sha256(archive.read_bytes()).hexdigest()==pin['sha256']
for name,entry in payload['toolchain'].items():
 assert hashlib.sha256(Path(shutil.which(name)).read_bytes()).hexdigest()==entry['sha256'], name+' toolchain changed'
sysroot_archive=dest/'sysroot.tar.gz';assert hashlib.sha256(sysroot_archive.read_bytes()).hexdigest()==pin['sysroot']['sha256']
sysroot_base=dest/'frozen-sysroot'
if not (sysroot_base/'sysroot').exists():
 sysroot_base.mkdir(exist_ok=True)
 with tarfile.open(sysroot_archive) as t:t.extractall(sysroot_base,filter='data')
base=dest/'frozen-base'
if not (base/'mesa-22.3.6').exists():
 base.mkdir(exist_ok=True)
 with tarfile.open(archive) as t:t.extractall(base,filter='data')
import os
compiler_tmp=dest/'compiler-tmp';compiler_tmp.mkdir(exist_ok=True);os.environ['TMPDIR']=str(compiler_tmp)
cross=dest/'armel.cross';cross_data=base64.b64decode(payload['cross']).decode().replace('/tmp/mbx-mesa-build-20261102/sysroot',str(sysroot_base/'sysroot'))
if not cross.exists() or cross.read_text()!=cross_data:cross.write_text(cross_data)
source=dest/'mesa-pinned-22.3.6'
if not source.exists():shutil.copytree(base/'mesa-22.3.6',source)
# Reset optional integration files before overlaying this candidate. This
# prevents a previous incremental candidate from leaking into a later build.
for optional in ('sp_texture.c','sp_state_surface.c','sp_flush.c'):
 name='src/gallium/drivers/softpipe/'+optional
 if name not in files:
  data=(base/'mesa-22.3.6'/name).read_bytes();target=source/name
  if not target.exists() or target.read_bytes()!=data:target.write_bytes(data)
old=(base/'mesa-22.3.6/src/gallium/drivers/softpipe/sp_mbx.c').read_text()
marker='/* Native frontend: reject X-only modes, never silently emulate them. */'
for name,value in files.items():
 data=base64.b64decode(value)
 if name.endswith('/sp_mbx.c'):data+=('\n'+old[old.index(marker):]).encode()
 target=source/name
 if not target.exists() or target.read_bytes()!=data:target.write_bytes(data)
# The private GL-name bridge uses this pinned Mesa's state-tracker objects.
softpipe_build=source/'src/gallium/drivers/softpipe/meson.build'
text=softpipe_build.read_text()
text=text.replace('include_directories : [inc_gallium_aux,', 'include_directories : [inc_mapi, inc_mesa, inc_gallium_aux,')
text=text.replace('include_directories : [inc_mesa, inc_gallium_aux,', 'include_directories : [inc_mapi, inc_mesa, inc_gallium_aux,')
if softpipe_build.read_text()!=text:softpipe_build.write_text(text)
sym=source/'src/gallium/targets/osmesa/osmesa.sym'
text=sym.read_text()
for prefix in ('n810_mbx_surface_*;', 'n810_mbx_window_*;', 'n810_mbx_transaction_*;'):
 if prefix not in text:text=text.replace('global:', 'global:\n\t\t'+prefix)
if sym.read_text()!=text:sym.write_text(text)
options=['-Dbuildtype=release','-Db_ndebug=true','-Dglx=disabled','-Dosmesa=true','-Dgallium-drivers=swrast','-Dvulkan-drivers=','-Dllvm=disabled','-Dshared-glapi=disabled','-Degl=disabled','-Dgbm=disabled','-Dplatforms=','-Dgles1=disabled','-Dgles2=disabled','-Dgallium-vdpau=disabled','-Dgallium-va=disabled','-Dgallium-xa=disabled','-Dbuild-tests=false','-Dlibunwind=disabled','-Dzstd=disabled','-Dglvnd=false','-Dxlib-lease=disabled']
build=dest/'build-pinned'
if not (build/'build.ninja').exists():subprocess.run(['meson','setup',str(build),str(source),'--cross-file',str(cross),*options],check=True)
subprocess.run(['ninja','-C',str(build),'-j'+str(payload['jobs'])],check=True)
'''
subprocess.run(['/opt/homebrew/bin/limactl','shell','n810-builder','--','python3','-c',guest],input=json.dumps(dict(jobs=max(1,int(os.environ.get('MBX_MESA_JOBS','4'))),build_root=build_root,files=files,pin=pin,toolchain=json.loads((p/'build-inputs/toolchain.json').read_text()),cross=base64.b64encode((p/'build-inputs/armel.cross').read_bytes()).decode())),text=True,check=True)
