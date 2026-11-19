#!/usr/bin/env python3
"""Fail before compilation when required host tools or free space are missing."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

GIB = 1024 ** 3
DOCKER_FREE = 30 * GIB
BASE = 'python:3.13-bookworm@sha256:cc55e4ded9c95f6ce2133b3d096db43f214d280c2a8af65d83e246c8fa7d168c'


def check(output, size_mib):
    if sys.version_info < (3, 11): raise ValueError('Use Python 3.11 or newer')
    for tool in ('git', 'bash', 'tar', 'docker'):
        if not shutil.which(tool): raise ValueError('Missing host command: ' + tool)
    parent = output.absolute().parent
    if not parent.is_dir(): raise ValueError('Create the kit output parent first: ' + str(parent))
    if output.exists(): raise ValueError('Choose a new kit output directory')
    output_required = max(4 * GIB, 2 * size_mib * 1024 ** 2 + 2 * GIB)
    free = shutil.disk_usage(parent).free
    if free < output_required:
        raise ValueError(f'Output filesystem needs {output_required/GIB:.1f} GiB free; has {free/GIB:.1f} GiB')
    engine = json.loads(subprocess.check_output(['docker', 'info', '--format', '{{json .}}'], text=True))
    if engine['OSType'] != 'linux': raise ValueError('Select a Docker Linux engine')
    if engine.get('MemTotal', 0) < 4 * GIB:
        raise ValueError('Assign at least 4 GiB RAM to the Docker Linux engine; 8 GiB is recommended')
    if 'Docker Desktop' in engine.get('OperatingSystem', '') and free < 40 * GIB:
        raise ValueError('Reserve 40 GiB host free space for Docker Desktop image growth and kit output')
    probe = 'import shutil,json; print(json.dumps(dict(free=shutil.disk_usage("/").free)))'
    result = subprocess.check_output(['docker', 'run', '--rm', '--entrypoint', 'python3', BASE, '-c', probe], text=True)
    engine_free = json.loads(result)['free']
    if engine_free < DOCKER_FREE:
        raise ValueError(f'Docker Linux storage needs 30 GiB free; has {engine_free/GIB:.1f} GiB')
    print(f'Free space: output {free/GIB:.1f} GiB (required {output_required/GIB:.1f}), Docker {engine_free/GIB:.1f} GiB (required 30).', flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--size-mib', type=int, default=1536)
    args=parser.parse_args()
    check(args.output, args.size_mib)
