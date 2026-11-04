#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Build a base-ABI ARMv6 shared library and static numerical probe."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

def run(argv):
    p=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=30)
    if p.returncode:raise RuntimeError(str(argv)+'\n'+p.stdout+p.stderr)
    return p.stdout

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prefix',default='arm-linux-gnueabi-')
    args=p.parse_args()
    here=Path(__file__).resolve().parent;out=args.out.resolve();out.mkdir(exist_ok=True,parents=True)
    cc=args.prefix+'gcc'
    base=['-O3','-std=c11','-Wall','-Wextra','-Werror','-mcpu=arm1136jf-s','-marm',
          '-fPIC','-ffp-contract=off','-fno-fast-math','-fno-tree-vectorize']
    commands=[]
    def compile(source,name,flags):
        argv=[cc,*base,*flags,'-c',here/source,'-o',out/name]
        commands.append(list(map(str,argv)));run(argv)
    compile('project.c','soft.o',['-mfloat-abi=soft','-DPROJECT_NAME=n810_project_soft'])
    compile('project.c','vfp.o',['-mfpu=vfpv2','-mfloat-abi=softfp','-DPROJECT_NAME=n810_project_vfp'])
    compile('dispatch.c','dispatch.o',['-mfloat-abi=soft','-DN810_ARM_VFP'])
    compile('fpscr.S','fpscr.o',['-mfpu=vfpv2','-mfloat-abi=softfp'])
    compile('probe.c','probe.o',['-mfloat-abi=soft'])
    objects=[out/n for n in ('soft.o','vfp.o','dispatch.o','fpscr.o')]
    for argv in ([cc,'-mfloat-abi=soft','-shared',*objects,'-o',out/'libn810compute.so'],
                 [cc,'-mfloat-abi=soft','-static',*objects,out/'probe.o','-lm','-o',out/'projection-check']):
        commands.append(list(map(str,argv)));run(argv)
    attributes=run([args.prefix+'readelf','-h','-A',out/'libn810compute.so'])
    assert 'soft-float ABI' in attributes and 'VFP registers' not in attributes
    (out/'elf-attributes.txt').write_text(attributes)
    for n in ('soft','vfp','dispatch','fpscr'):
        (out/(n+'.dis')).write_text(run([args.prefix+'objdump','-dr',out/(n+'.o')]))
    actual=json.loads(run(['qemu-arm','-cpu','arm1136',out/'projection-check']))
    fallback=json.loads(run(['qemu-arm','-cpu','arm1136,vfp=off',out/'projection-check']))
    assert actual['status']==fallback['status']=='PASS'
    assert actual['vfp_used'] and not fallback['vfp_used']
    result=dict(status='PASS',hardware_execution=False,execution='local ARM1136 QEMU',
        vfp=actual,no_vfp=fallback,commands=commands,compiler=run([cc,'--version']).splitlines()[0],
        source_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in here.iterdir() if f.suffix in ('.c','.h','.S','.py') or f.name=='LICENSE'},
        files={n:dict(bytes=(out/n).stat().st_size,sha256=hashlib.sha256((out/n).read_bytes()).hexdigest()) for n in ('libn810compute.so','projection-check')})
    (out/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('commands','source_sha256')},indent=2))
if __name__=='__main__':main()
