#!/usr/bin/env python3
"""Exercise scalar signal handlers during VFPv2 vector windows in ARM1136 QEMU."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def run(argv):
    p = subprocess.run(list(map(str, argv)),capture_output=True,text=True,timeout=30)
    if p.returncode:
        raise RuntimeError(f'{argv[0]} exited {p.returncode}: {p.stdout}{p.stderr}')
    return p.stdout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prefix',default='arm-linux-gnueabi-')
    args = p.parse_args()
    here,out = Path(__file__).resolve().parent,args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    cc = args.prefix+'gcc'
    flags = ['-O2','-std=c11','-Wall','-Wextra','-Werror','-mcpu=arm1136jf-s',
             '-marm','-mfpu=vfpv2','-mfloat-abi=soft','-fno-fast-math']
    sources = ['shortvec.S','shortvec_context.S','shortvec_signal.S','signal_probe.c']
    commands = []
    for name in sources:
        command = [cc,*flags,'-c',here/name,'-o',out/(name+'.o')]
        run(command)
        commands.append(list(map(str,command)))
    command = [cc,'-mfloat-abi=soft','-static',*[out/(n+'.o') for n in sources],
               '-o',out/'vfp-signal-check']
    run(command)
    commands.append(list(map(str,command)))
    attrs = run([args.prefix+'readelf','-h','-A',out/'vfp-signal-check'])
    assert 'soft-float ABI' in attrs and 'VFP registers' not in attrs
    (out/'executable.attributes').write_text(attrs)
    run([args.prefix+'objcopy','-O','binary','-j','.text',out/'shortvec.S.o',out/'shortvec.bin'])
    code = (out/'shortvec.bin').read_bytes()
    code_hash = hashlib.sha256(code).hexdigest()
    assert len(code)==76 and code_hash=='c412d1e4da9ccf15580b0d4c55fc3315a4ec225d32deeae80854b06244a892fc'
    def check(extra):
        process = subprocess.run(['qemu-arm','-cpu','arm1136',str(out/'vfp-signal-check'),*extra],
                                 capture_output=True,text=True,timeout=30)
        record = json.loads(process.stdout)
        record.update(exit_code=process.returncode,stderr=process.stderr)
        return record
    checked = [check([]) for _ in range(2)]
    modeled = [check(['--model-linux-entry']) for _ in range(2)]
    if all(r['status']=='PASS' and r['in_vector_window']>0 for r in checked):
        status = 'PASS'
    elif (all(r['status']=='FAIL' and r['exit_code']==5 and r['bad_handler_mode']>0
             and not r['bad_handler_scalar'] and not r['output_bad']
             and not r['clock_bad'] and r['fpscr_before']==r['fpscr_after'] for r in checked)
        and all(r['status']=='PASS' and r['in_vector_window']>0 for r in modeled)):
        status = 'LIMITED'
    else:
        status = 'FAIL'
    result = {'status':status,'hardware_execution':False,'performance_measured':False,
              'execution':'QEMU user-mode ARM1136; QEMU synthesizes the guest signal frame',
              'actual_n810_kernel_signal_handling_verified':False,'runs':checked,
              'shortvec_code_bytes':len(code),'shortvec_code_sha256':code_hash,
              'linux_entry_mask_modeled_runs':modeled,
              'commands':commands,
              'source_sha256':{n:hashlib.sha256((here/n).read_bytes()).hexdigest()
                               for n in sources+['build_signal_probe.py']}}
    (out/'signal-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('commands','source_sha256')},indent=2))
    if status == 'FAIL':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
