#!/usr/bin/env python3
"""Check VFPv2 short-vector arithmetic and preserved context under ARM1136 QEMU."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def run(argv):
    p = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=60)
    if p.returncode:
        raise RuntimeError(f'{argv[0]} exited {p.returncode}: {p.stdout}{p.stderr}')
    return p.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prefix', default='arm-linux-gnueabi-')
    args = parser.parse_args()
    here, out = Path(__file__).resolve().parent, args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cc = args.prefix+'gcc'
    flags = ['-O2','-std=c11','-Wall','-Wextra','-Werror','-mcpu=arm1136jf-s',
             '-marm','-mfpu=vfpv2','-ffp-contract=off','-fno-fast-math','-fno-tree-vectorize']
    commands = []

    def compile(source, name, abi='soft', extra=()):
        command = [cc,*flags,'-mfloat-abi='+abi,*extra,'-c',source,'-o',out/name]
        run(command)
        commands.append(list(map(str,command)))

    compile(here/'add.c','add-soft.o',extra=['-DADD_NAME=add_soft'])
    compile(here/'add.c','add-vfp.o',abi='softfp',extra=['-DADD_NAME=add_vfp'])
    compile(here/'shortvec_context.S','context.o')
    compile(here/'shortvec_probe.c','caller.o')
    compile(here/'shortvec_probe.c','negative-caller.o',extra=['-DEXPECT_CONTEXT_FAILURE=1'])
    source = (here/'shortvec.S').read_text()
    versions = {'correct':source,
                'missing-fpscr-restore':source.replace('    vmsr fpscr, r4\n','    nop\n'),
                'missing-register-restore':source.replace('    vpop {d8-d15}\n','    add sp, sp, #64\n')}
    assert all(versions[k] != source for k in versions if k != 'correct')
    results = {}
    for name,text in versions.items():
        asm = out/(name+'.S')
        asm.write_text(text)
        compile(asm,name+'.o')
        dis = run([args.prefix+'objdump','-dr',out/(name+'.o')])
        (out/(name+'.dis')).write_text(dis)
        if name == 'correct':
            assert dis.count('vadd.f32') == 1 and 'fpscr' in dis
        caller = out/('caller.o' if name == 'correct' else 'negative-caller.o')
        executable = out/name
        command = [cc,'-mfloat-abi=soft','-static',caller,out/(name+'.o'),
                   out/'context.o',out/'add-soft.o','-o',executable]
        run(command)
        commands.append(list(map(str,command)))
        result = json.loads(run(['qemu-arm','-cpu','arm1136',executable]))
        assert result['status'] == ('PASS' if name == 'correct' else 'DETECTED'),result
        results[name] = result
    assert results['missing-fpscr-restore']['fpscr_mismatch']
    assert results['missing-register-restore']['register_mismatch']
    for precision,typ in (('f32','float'),('f64','double')):
        for variant,abi in (('soft','soft'),('vfp','softfp')):
            compile(here/'batch.c',f'batch-{precision}-{variant}.o',abi=abi,
                    extra=['-DREAL_TYPE='+typ,'-DBATCH_NAME=batch_'+precision+'_'+variant])
            dis = run([args.prefix+'objdump','-dr',out/f'batch-{precision}-{variant}.o'])
            (out/f'batch-{precision}-{variant}.dis').write_text(dis)
    compile(here/'benchmark.c','benchmark.o')
    command = [cc,'-mfloat-abi=soft','-static',out/'benchmark.o',out/'correct.o',out/'context.o',
               out/'add-soft.o',out/'add-vfp.o',
               *[out/f'batch-{p}-{v}.o' for p in ('f32','f64') for v in ('soft','vfp')],
               '-o',out/'vfp-benchmark']
    run(command)
    commands.append(list(map(str,command)))
    raw = run(['qemu-arm','-cpu','arm1136',out/'vfp-benchmark','--run'])
    (out/'benchmark-qemu.jsonl').write_text(raw)
    rows = [json.loads(line) for line in raw.splitlines()]
    assert rows[-1]['status'] == 'PASS' and rows[-1]['records'] == 72
    groups = {}
    for row in rows[:-1]:
        assert row['elapsed_ns'] >= 0 and row['clock_resolution_ns'] > 0
        groups.setdefault((row['operation'],row['count']),set()).add(row['checksum'])
    assert len(groups) == 10 and all(len(hashes) == 1 for hashes in groups.values())
    run([args.prefix+'objcopy','-O','binary','-j','.text',out/'correct.o',out/'shortvec.bin'])
    code = (out/'shortvec.bin').read_bytes()
    attrs = run([args.prefix+'readelf','-h','-A',out/'correct'])
    (out/'executable.attributes').write_text(attrs)
    assert 'soft-float ABI' in attrs and 'VFP registers' not in attrs
    result = {'status':'PASS','hardware_execution':False,'performance_measured':False,
              'execution':'QEMU user-mode ARM1136','results':results,'commands':commands,
              'shortvec_code_bytes':len(code),'shortvec_code_sha256':hashlib.sha256(code).hexdigest(),
              'benchmark_schema_checked_records':72,'benchmark_checksum_groups':len(groups),
              'benchmark_hardware_performance_measured':False,
              'source_sha256':{n:hashlib.sha256((here/n).read_bytes()).hexdigest() for n in
                ('shortvec.S','shortvec_context.S','shortvec_probe.c','add.c','batch.c',
                 'benchmark.c','build_shortvec.py')}}
    (out/'shortvec-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('commands','source_sha256')},indent=2))


if __name__ == '__main__':
    main()
