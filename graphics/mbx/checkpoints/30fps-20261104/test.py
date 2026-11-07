#!/usr/bin/env python3
"""Run the frozen checkpoint's offline regression tests with sanitizers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

from verify import ROOT, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--mesa-archive', type=Path, required=True,
                        help='Checksum-pinned Mesa 22.3.6 tar.xz from the graphics build downloads')
    args = parser.parse_args()
    verify()
    lock = json.loads((ROOT.parents[1] / 'dependencies.lock.json').read_text())['mesa']
    if hashlib.sha256(args.mesa_archive.read_bytes()).hexdigest() != lock['sha256']:
        raise ValueError('Mesa archive checksum mismatch')
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    upstream = work / 'upstream'
    upstream.mkdir()
    with tarfile.open(args.mesa_archive) as archive:
        for relative in ('src/gallium/auxiliary/draw/draw_decompose_tmp.h',
                         'src/gallium/drivers/softpipe/sp_state_derived.c'):
            member = archive.getmember('mesa-' + lock['version'] + '/' + relative)
            if not member.isfile():
                raise ValueError('Expected an ordinary upstream file: ' + relative)
            (upstream / Path(relative).name).write_bytes(archive.extractfile(member).read())
    fixture = work / 'gears-frame.vgp'
    fixture.write_bytes(bytes.fromhex((ROOT / 'fixtures/gears-frame.vgp.hex').read_text()))
    results = []
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'

    def run(name, commands):
        code = 0
        with (work / (name + '.log')).open('wb') as log:
            for command in commands:
                try:
                    result = subprocess.run(list(map(str, command)), cwd=work, env=env,
                                            stdout=log, stderr=subprocess.STDOUT, timeout=180)
                    code = result.returncode
                except subprocess.TimeoutExpired:
                    code = 124
                if code:
                    break
        results.append({'test': name, 'exit_code': code})
        (work / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(name, 'PASS' if code == 0 else f'FAIL ({code})', flush=True)

    def c_test(test, sources, arguments=(), extra_include=None):
        executable = work / test.stem
        common = test.parent / 'common' if test.parent.name != 'tests' else ROOT / 'common'
        includes = [common, ROOT / 'mesa', upstream]
        if extra_include:
            includes.append(extra_include)
        command = ['cc', '-O1', '-g', '-ffp-contract=off', '-fsanitize=address,undefined',
                   '-fno-sanitize-recover=all', *['-I' + str(path) for path in includes],
                   test, *sources, '-lm', '-o', executable]
        run(test.stem, [command, [executable, *arguments]])

    for test in sorted((ROOT / 'tests').glob('*.c')):
        c_test(test, sorted((ROOT / 'common').glob('*.c')))
    service = ROOT / 'experiments/vgp-service-20261104'
    source_names = {
        'test_color_dependency': [],
        'test_gears_batch': ['mbx_vgp_batch.c'],
        'test_stream_batch': ['mbx_vgp_stream.c'],
        'test_strip_stream': [],
        'test_strip_wire': [],
        'test_wire_replay': ['mbx_vgp_wire.c', 'mbx_vgp_draw.c', 'mbx_vgp_isa.c',
                             'mbx_vgp_topology.c', 'mbx_vgp_transform.c'],
    }
    for name, sources in source_names.items():
        c_test(service / (name + '.c'), [service / 'common' / name for name in sources],
               [fixture] if name == 'test_wire_replay' else [])
    run('test_frame_allocation', [[sys.executable, service / 'test_frame_allocation.py']])
    run('test_sampler_scan', [[sys.executable, ROOT / 'tests/test_sampler_scan.py',
                              upstream / 'sp_state_derived.c']])
    return int(any(row['exit_code'] for row in results))


if __name__ == '__main__':
    raise SystemExit(main())
