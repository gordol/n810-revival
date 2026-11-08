#!/usr/bin/env python3
"""Build the original MBX module and Mesa integration using explicit local outputs."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,sys
HERE=Path(__file__).resolve().parent

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('target',choices=['module','mesa']);p.add_argument('--work',type=Path,required=True)
    p.add_argument('--kernel-source',type=Path);p.add_argument('--kernel-build',type=Path)
    p.add_argument('--osmesa',action='store_true',help='also build the headless OSMesa library for Pocket framebuffer graphics')
    p.add_argument('--jobs',type=int,default=4)
    p.add_argument('--checkpoint',choices=['30fps-20261104'])
    p.add_argument('--download-cache',type=Path,help='Read checksum-pinned archives from an existing cache')
    a=p.parse_args()
    if a.osmesa and a.target!='mesa':p.error('--osmesa applies only to the mesa target')
    source_root=HERE/'checkpoints'/a.checkpoint if a.checkpoint else HERE
    if a.checkpoint:
        subprocess.run([sys.executable,source_root/'verify.py'],check=True)
    work=a.work.resolve();work.mkdir(parents=True,exist_ok=False)
    logs=work/'logs';logs.mkdir();out=work/'package';out.mkdir()
    def run(args,label,cwd=None,env=None):
        print(label,flush=True)
        with (logs/(label+'.log')).open('wb') as f:r=subprocess.run(list(map(str,args)),cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
        if r.returncode:raise RuntimeError(f'{label} failed; see {logs/(label+".log")}')
    if a.target=='module':
        if not a.kernel_source or not a.kernel_build:p.error('module needs --kernel-source and --kernel-build from the completed kernel build')
        source=a.kernel_source.resolve();build=a.kernel_build.resolve();module=work/'module'
        kernel=source_root/'experiments/vgp-service-20261104/kernel' if a.checkpoint else HERE/'kernel'
        shutil.copytree(kernel,module)
        if not a.checkpoint:
            for name in ('mbx_packets.c','mbx_packets.h','mbx_context.c','mbx_context.h','mbx_vertex_program.c','mbx_vertex_program.h'):
                shutil.copyfile(HERE/'common'/name,module/name)
        run(['make','-C',source,'O='+str(build),'ARCH=arm','CROSS_COMPILE=arm-linux-gnueabihf-','LOCALVERSION=','M='+str(module),'modules'],'module')
        ko=module/'n810_mbx_gpu_probe.ko';release=(build/'include/config/kernel.release').read_text().strip()
        versions=subprocess.check_output(['modprobe','--dump-modversions',str(ko)],text=True)
        exports={x.split()[1]:x.split()[0] for x in (build/'Module.symvers').read_text().splitlines()}
        imports={x.split()[1]:x.split()[0] for x in versions.splitlines()}
        assert imports and all(exports.get(n)==c for n,c in imports.items())
        vermagic=subprocess.check_output(['modinfo','-F','vermagic',str(ko)],text=True).strip();assert vermagic.startswith(release+' ')
        shutil.copyfile(ko,out/ko.name);report={'kernel_release':release,'crc_checks':len(imports),'vermagic':vermagic}
    else:
        lock=json.loads((HERE/'dependencies.lock.json').read_text());downloads=work/'downloads';downloads.mkdir();sysroot=work/'sysroot';sysroot.mkdir()
        def fetch(name,row):
            target=downloads/name
            cached=a.download_cache.resolve()/name if a.download_cache else None
            if cached and cached.is_file():
                if digest(cached)!=row['sha256']:raise RuntimeError('Cached checksum mismatch: '+name)
                shutil.copyfile(cached,target)
                return target
            urls=row.get('urls',[row.get('url')])
            for i,url in enumerate(urls):
                try:run(['curl','-fLsS','--retry','2','--proto','=https','-o',target,url],f'download-{name}-{i}')
                except RuntimeError:continue
                if digest(target)==row['sha256']:
                    if cached:
                        cached.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(target,cached)
                    return target
                raise RuntimeError('Checksum mismatch: '+name)
            raise RuntimeError('Could not download pinned input: '+name)
        archive=fetch('mesa.tar.xz',lock['mesa']);run(['tar','-xJf',archive,'-C',work],'extract-mesa')
        for row in lock['sysroot_packages']:
            package=fetch(row['file'],row);run(['dpkg-deb','-x',package,sysroot],'extract-'+row['file'])
        intrinsic=Path(subprocess.check_output(['arm-linux-gnueabi-gcc','-print-file-name=include'],text=True).strip())
        shutil.copytree(intrinsic,sysroot/'gcc-intrinsic')
        # Relocate absolute symlinks from the Debian packages into this sysroot.
        for f in sysroot.rglob('*'):
            if f.is_symlink() and os.readlink(f).startswith('/'):
                destination=sysroot/os.readlink(f).lstrip('/');f.unlink();f.symlink_to(os.path.relpath(destination,f.parent))
        integration=work/'integration';shutil.copytree(source_root/'mesa',integration)
        for f in (source_root/'common').iterdir():
            if f.suffix in ('.c','.h'):shutil.copyfile(f,integration/f.name)
        mesa=work/('mesa-'+lock['mesa']['version']);run([sys.executable,integration/'prepare_mesa.py',mesa],'prepare-mesa')
        cross=work/'armel.cross';cross.write_text((HERE/'mesa/armel.cross.in').read_text().replace('@SYSROOT@',str(sysroot)))
        options=['-Dbuildtype=release','-Db_ndebug=true','-Dglx=xlib','-Dgallium-drivers=swrast','-Dvulkan-drivers=',
                 '-Dllvm=disabled','-Dshared-glapi=disabled','-Degl=disabled','-Dgbm=disabled','-Dplatforms=x11',
                 '-Dgles1=disabled','-Dgles2=disabled','-Dgallium-vdpau=disabled','-Dgallium-va=disabled',
                 '-Dgallium-xa=disabled','-Dbuild-tests=false','-Dlibunwind=disabled','-Dzstd=disabled','-Dglvnd=false','-Dxlib-lease=disabled']
        if a.osmesa:
            options.append('-Dosmesa=true')
            target=mesa/'src/gallium/targets/osmesa'
            shutil.copyfile(HERE/'mesa/osmesa_frontend.c',target/'mbx_frontend.c')
            recipe=target/'meson.build';text=recipe.read_text()
            if text.count("  'target.c',")!=1:raise RuntimeError('Unexpected OSMesa target recipe')
            recipe.write_text(text.replace("  'target.c',","  ['target.c', 'mbx_frontend.c'],"))
        env=os.environ.copy();env['PKG_CONFIG_SYSROOT_DIR']=str(sysroot)
        env['PKG_CONFIG_LIBDIR']=str(sysroot/'usr/lib/arm-linux-gnueabi/pkgconfig')+':'+str(sysroot/'usr/share/pkgconfig')
        run(['meson','setup',work/'build',mesa,'--cross-file',cross,*options],'configure-mesa',env=env)
        run(['ninja','-C',work/'build','-j'+str(a.jobs)],'compile-mesa',env=env)
        library=work/'build/src/gallium/targets/libgl-xlib/libGL.so.1.5.0'
        run(['arm-linux-gnueabi-strip','--strip-unneeded','-o',out/'libGL.so.1',library],'strip-export')
        if a.osmesa:
            osmesa=work/'build/src/gallium/targets/osmesa/libOSMesa.so.8.0.0'
            run(['arm-linux-gnueabi-strip','--strip-unneeded','-o',out/'libOSMesa.so.8',osmesa],'strip-osmesa')
            shutil.copytree(mesa/'include',out/'include')
        versions=subprocess.check_output(['arm-linux-gnueabi-readelf','--version-info',str(library)],text=True)
        required={k:sorted(set(re.findall(k+r'_([0-9.]+)',versions)),key=lambda s:tuple(map(int,s.split('.')))) for k in ('GLIBC','GLIBCXX','CXXABI')}
        for key,limit in {'GLIBC':(2,36),'GLIBCXX':(3,4,30),'CXXABI':(1,3,13)}.items():
            assert all(tuple(map(int,v.split('.')))<=limit for v in required[key]),key
        report={'headless_bridge_sha256':digest(HERE/'mesa/osmesa_frontend.c') if a.osmesa else None,'mesa_version':lock['mesa']['version'],'dependencies_sha256':digest(HERE/'dependencies.lock.json'),'required_versions':required}
    report.update(target=a.target,checkpoint=a.checkpoint,device_action=False,source_sha256={str(f.relative_to(source_root)):digest(f) for f in sorted(source_root.rglob('*')) if f.is_file() and '__pycache__' not in f.parts},outputs={f.name:digest(f) for f in out.iterdir() if f.is_file()})
    (out/'BUILD.json').write_text(json.dumps(report,indent=2)+'\n');print('Build complete:',out)
if __name__=='__main__':main()
