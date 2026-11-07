#!/usr/bin/env python3
"""Cross-build and check an isolated ARMv6 soft/softfp probe under QEMU only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def run(argv):
    result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f'{argv[0]} exited {result.returncode}: {result.stdout}{result.stderr}')
    return result.stdout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--prefix', default='arm-linux-gnueabi-')
    args = p.parse_args()
    here = Path(__file__).resolve().parent
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cc = args.prefix + 'gcc'
    common = ['-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-mcpu=arm1136jf-s',
              '-marm', '-mfpu=vfpv2', '-ffp-contract=off', '-fno-fast-math',
              '-fno-tree-vectorize']
    commands = []
    attributes = {}
    for variant, abi in (('soft', 'soft'), ('vfp', 'softfp')):
        obj = out / f'kernel-{variant}.o'
        command = [cc, *common, '-mfloat-abi='+abi,
                   '-DTRANSFORM_NAME=transform_'+variant, '-DAFFINE_NAME=affine_'+variant,
                   '-DDOUBLE_AFFINE_NAME=affine64_'+variant,
                   '-c', here/'kernel.c', '-o', obj]
        run(command)
        commands.append(list(map(str, command)))
        dis = run([args.prefix+'objdump', '-dr', obj])
        (out/f'kernel-{variant}.dis').write_text(dis)
        attrs = run([args.prefix+'readelf', '-h', '-A', obj])
        attributes[variant] = attrs
        (out/f'kernel-{variant}.attributes').write_text(attrs)
        assert 'VFP registers' not in attrs
        if variant == 'vfp':
            assert 'Tag_FP_arch: VFPv2' in attrs
            assert re.search(r'\bvmul\.f32\b', dis) and re.search(r'\bv(?:add|mla)\.f32\b', dis)
            assert re.search(r'\bv(?:mul|mla)\.f64\b', dis)
            assert '__aeabi_fmul' not in dis and '__aeabi_fadd' not in dis
            assert '__aeabi_dmul' not in dis and '__aeabi_dadd' not in dis
        else:
            assert '__aeabi_fmul' in dis and '__aeabi_fadd' in dis
            assert '__aeabi_dmul' in dis and '__aeabi_dadd' in dis
    caller = out/'caller.o'
    command = [cc, *common, '-mfloat-abi=soft', '-c', here/'probe.c', '-o', caller]
    run(command)
    commands.append(list(map(str, command)))
    dis = run([args.prefix+'objdump', '-dr', caller])
    (out/'caller.dis').write_text(dis)
    assert 'R_ARM_CALL\taffine_vfp' in dis
    assert 'R_ARM_CALL\taffine64_vfp' in dis
    assert not re.search(r'\bv(?:add|mul|mov|ldr|str)\.', dis)
    command = [cc, '-mfloat-abi=soft', '-static', caller,
               out/'kernel-soft.o', out/'kernel-vfp.o', '-o', out/'vfp-probe']
    run(command)
    commands.append(list(map(str, command)))
    elf = run([args.prefix+'readelf', '-h', '-A', out/'vfp-probe'])
    (out/'executable.attributes').write_text(elf)
    assert 'soft-float ABI' in elf and 'VFP registers' not in elf
    hard = out/'kernel-hard-negative.o'
    run([cc,*common,'-mfloat-abi=hard','-DTRANSFORM_NAME=transform_vfp',
         '-DAFFINE_NAME=affine_vfp','-DDOUBLE_AFFINE_NAME=affine64_vfp',
         '-c',here/'kernel.c','-o',hard])
    hard_attrs = run([args.prefix+'readelf','-A',hard])
    assert 'Tag_ABI_VFP_args: VFP registers' in hard_attrs
    negative = subprocess.run([cc,'-static','-mfloat-abi=soft',str(caller),
                              str(out/'kernel-soft.o'),str(hard),
                              '-o',str(out/'incompatible-hard')],
                              capture_output=True,text=True,timeout=30)
    assert negative.returncode and 'uses VFP register arguments' in negative.stderr
    (out/'hard-abi-negative.txt').write_text(negative.stderr)
    checked = json.loads(run(['qemu-arm', '-cpu', 'arm1136', out/'vfp-probe']))
    fallback = json.loads(run(['qemu-arm', '-cpu', 'arm1136', out/'vfp-probe', '--force-soft']))
    assert checked['status'] == 'PASS'
    assert fallback['status'] == 'SOFT_ONLY' and not fallback['vfp_functions_called']
    result = {'status':'PASS', 'hardware_execution':False, 'execution':'QEMU user-mode ARM1136',
              'performance_measured':False, 'compiler':run([cc,'--version']).splitlines()[0],
              'qemu':run(['qemu-arm','--version']).splitlines()[0],
              'soft_caller_to_softfp_callee':checked, 'forced_soft_path':fallback,
              'hard_float_link_mismatch_rejected':True,
              'commands':commands,
              'source_sha256':{n:hashlib.sha256((here/n).read_bytes()).hexdigest()
                               for n in ('kernel.c','probe.c','build_probe.py')}}
    (out/'validation.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='commands'}, indent=2))


if __name__ == '__main__':
    main()
