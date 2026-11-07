#!/usr/bin/env python3
"""Cross-compile tablet helpers into a new directory; no installation or boot."""
import argparse,hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--prefix',default='arm-linux-gnueabi-')
a=p.parse_args();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=False)
root=Path(__file__).resolve().parent
names=['n810-wake','n810-backlightd','n810-input-remap','n810-fn-remap','n810-touch-calibrate']
results={}
for name in names+['n810-merged-usr-rescue-r14-init']:
    source=root/'scripts'/(name+'.c');target=a.out/name
    flags=['-Os','-static','-march=armv6','-marm','-mfloat-abi=soft','-Wall','-Wextra']
    if name.endswith('-init'):flags+=['-nostdlib','-fno-stack-protector','-fno-builtin','-Wl,--build-id=none','-Wl,-e,_start']
    subprocess.run([a.prefix+'gcc',*flags,str(source),*(['-lm'] if name=='n810-touch-calibrate' else []),'-o',str(target)],check=True)
    subprocess.run([a.prefix+'strip',str(target)],check=True)
    results[name]={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'binary_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
(a.out/'BUILD.json').write_text(json.dumps({'compiler':subprocess.check_output([a.prefix+'gcc','--version'],text=True).splitlines()[0],'outputs':results},indent=2)+'\n')
print('Built',len(results),'ARM helpers in',a.out)
