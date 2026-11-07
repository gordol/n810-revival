#!/usr/bin/env python3
"""Build HTIT firmware in a new local directory and record the exact source inputs."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target',choices=['executor','hub'])
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--pio',default='pio')
    args=parser.parse_args()
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=False)
    os.chmod(work,0o700)
    name,environment=('microreticulum','htit-tb-executor-rfcomm') if args.target=='executor' else ('rfcomm-ble-hub','htit_tb')
    source=ROOT/name
    ignore=shutil.ignore_patterns('.pio','__pycache__','*.pyc','HTITPrivate.h','.venv')
    shutil.copytree(source,work/'source',ignore=ignore)
    if args.target=='executor':
        subprocess.run([sys.executable,str(work/'source/generate_private_pin.py')],check=True)
    command=[args.pio,'run','-d',str(work/'source'),'-e',environment]
    with (work/'build.log').open('wb') as log:
        result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        raise SystemExit('Build failed; inspect '+str(work/'build.log'))
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    files={str(p.relative_to(source)):sha(p) for p in sorted(source.rglob('*')) if p.is_file() and '.pio' not in p.parts and '__pycache__' not in p.parts and p.name!='HTITPrivate.h' and p.suffix!='.pyc'}
    build=work/'source/.pio/build'/environment
    outputs={p.name:sha(p) for p in build.iterdir() if p.suffix in ('.bin','.elf')}
    report={'target':args.target,'environment':environment,'platformio':subprocess.check_output([args.pio,'--version'],text=True).strip(),'source_sha256':files,'output_sha256':outputs,'pairing_pin':'generated locally' if args.target=='executor' else 'configured by hub firmware','uploaded':False}
    (work/'BUILD.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Build complete:',work)
    if args.target=='executor':print('Pairing PIN is in the private build directory: source/HTITPrivate.h')
if __name__=='__main__':main()
