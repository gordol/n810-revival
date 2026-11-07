#!/usr/bin/env python3
"""Copy a recovered source-dev checkout and apply the pinned control candidate.

The supplied checkout is never edited. No installation or DSP execution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout',type=Path,help='source-dev produced by the original build.py')
    parser.add_argument('--out',type=Path,required=True,help='new, nonexistent workspace')
    parser.add_argument('--build',action='store_true')
    args = parser.parse_args()
    here,original,out = Path(__file__).resolve().parent,args.checkout.resolve(),args.out.resolve()
    pins = json.loads((here/'control-candidate-pins.json').read_text())
    if out.exists() or out==original or original in out.parents:
        raise SystemExit('output must be a new workspace outside the supplied checkout')
    for name,pin in pins['source_changes'].items():
        if digest(original/name)!=pin['before_sha256']:
            raise SystemExit('source hash mismatch: '+name)
    out.mkdir(parents=True)
    source = out/'source'
    shutil.copytree(original,source,symlinks=True,ignore=shutil.ignore_patterns('CVS'))
    command = ['patch','--batch','-p1','-i',str(here/'control-candidate.patch')]
    result = subprocess.run(command,cwd=source,capture_output=True,text=True,timeout=30)
    (out/'patch.log').write_text(result.stdout+result.stderr)
    if result.returncode:
        raise SystemExit('patch failed; inspect patch.log in the new workspace')
    for name,pin in pins['source_changes'].items():
        if digest(source/name)!=pin['after_sha256']:
            raise SystemExit('patched source hash mismatch: '+name)
    commands = [command]
    if args.build:
        build = out/'build'
        build.mkdir()
        environment = {**os.environ,'CFLAGS':'-O2 -g -std=gnu89 -fcommon -Wno-error=implicit-function-declaration -Wno-error=incompatible-pointer-types'}
        for name,command in [('configure',['sh',str(source/'configure'),'--target=c55x','--disable-nls','--disable-werror','--disable-shared']),
                             ('build',['make','-j4','MAKEINFO=true','all-gas','all-binutils','all-ld'])]:
            with (out/(name+'.log')).open('w') as log:
                result = subprocess.run(command,cwd=build,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=300)
            commands.append(command)
            if result.returncode:
                raise SystemExit(name+' failed; inspect '+name+'.log')
    result = dict(status='BUILT' if args.build else 'PREPARED',hardware_execution=False,
                  original_checkout_modified=False,installation_performed=False,
                  source_changes=pins['source_changes'],commands=commands,
                  patch_sha256=digest(here/'control-candidate.patch'))
    (out/'candidate-preparation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
