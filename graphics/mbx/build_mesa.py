"""Build isolated Mesa candidate; no device actions or production replacement."""
from pathlib import Path
import subprocess,json,base64,hashlib,os
p=Path(__file__).resolve().parent
pin=json.loads((p/'build-inputs/mesa-source.json').read_text())
archive=Path(os.environ['MBX_MESA_SOURCE_ARCHIVE'])
assert hashlib.sha256(archive.read_bytes()).hexdigest()==pin['sha256'], 'Mesa source archive digest mismatch'
build_root=os.environ.get('MBX_MESA_BUILD_ROOT',str(Path.home()/'.cache/n810/mesa'))
assert Path(build_root).is_absolute()
remote=str(Path(build_root)/'source-base.tar.gz')
subprocess.run(['/opt/homebrew/bin/limactl','shell','n810-builder','--','mkdir','-p',str(Path(remote).parent)],check=True)
subprocess.run(['/opt/homebrew/bin/limactl','copy',str(archive),'n810-builder:'+remote],check=True)
sysroot_archive=Path(os.environ.get('MBX_MESA_SYSROOT_ARCHIVE',str(archive.parent/pin['sysroot']['archive'])))
assert hashlib.sha256(sysroot_archive.read_bytes()).hexdigest()==pin['sysroot']['sha256']
subprocess.run(['/opt/homebrew/bin/limactl','copy',str(sysroot_archive),'n810-builder:'+str(Path(remote).with_name('sysroot.tar.gz'))],check=True)
files={'src/gallium/drivers/softpipe/'+f.name:base64.b64encode(f.read_bytes()).decode() for f in (p/'mesa').iterdir() if f.is_file()}
files['src/gallium/drivers/softpipe/mbx_owned_surface.h']=base64.b64encode((p/'common/mbx_owned_surface.h').read_bytes()).decode()
for name in ('mbx_vgp_draw.h','mbx_vgp_wire.h','mbx_image_abi.h'):files['src/gallium/auxiliary/draw/'+name]=base64.b64encode((p/'common'/name).read_bytes()).decode()
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
cross=dest/'armel.cross';cross.write_text(base64.b64decode(payload['cross']).decode().replace('/tmp/mbx-mesa-build-20261102/sysroot',str(sysroot_base/'sysroot')))
source=dest/'mesa-pinned-22.3.6'
if not source.exists():shutil.copytree(base/'mesa-22.3.6',source)
# Reset optional integration files before overlaying this candidate. This
# prevents a previous incremental candidate from leaking into a later build.
for optional in ('sp_texture.c','sp_state_surface.c','sp_flush.c'):
 shutil.copy2(base/'mesa-22.3.6/src/gallium/drivers/softpipe'/optional, source/'src/gallium/drivers/softpipe'/optional)
old=(base/'mesa-22.3.6/src/gallium/drivers/softpipe/sp_mbx.c').read_text()
marker='/* Native frontend: reject X-only modes, never silently emulate them. */'
for name,value in files.items():
 data=base64.b64decode(value)
 if name.endswith('/sp_mbx.c'):data+=('\n'+old[old.index(marker):]).encode()
 (source/name).write_bytes(data)
sym=source/'src/gallium/targets/osmesa/osmesa.sym'
text=sym.read_text()
if 'n810_mbx_surface_*;' not in text:sym.write_text(text.replace('global:', 'global:\n\t\tn810_mbx_surface_*;'))
options=['-Dbuildtype=release','-Db_ndebug=true','-Dglx=disabled','-Dosmesa=true','-Dgallium-drivers=swrast','-Dvulkan-drivers=','-Dllvm=disabled','-Dshared-glapi=disabled','-Degl=disabled','-Dgbm=disabled','-Dplatforms=','-Dgles1=disabled','-Dgles2=disabled','-Dgallium-vdpau=disabled','-Dgallium-va=disabled','-Dgallium-xa=disabled','-Dbuild-tests=false','-Dlibunwind=disabled','-Dzstd=disabled','-Dglvnd=false','-Dxlib-lease=disabled']
build=dest/'build-pinned'
if not (build/'build.ninja').exists():subprocess.run(['meson','setup',str(build),str(source),'--cross-file',str(cross),*options],check=True)
subprocess.run(['ninja','-C',str(build),'-j'+str(payload['jobs'])],check=True)
'''
subprocess.run(['/opt/homebrew/bin/limactl','shell','n810-builder','--','python3','-c',guest],input=json.dumps(dict(jobs=max(1,int(os.environ.get('MBX_MESA_JOBS','4'))),build_root=build_root,files=files,pin=pin,toolchain=json.loads((p/'build-inputs/toolchain.json').read_text()),cross=base64.b64encode((p/'build-inputs/armel.cross').read_bytes()).decode())),text=True,check=True)
