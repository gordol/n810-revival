#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Finish one internal kit from the source-built container's component packages."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent


def build(output, ssh_key, cache, backup=None, offline=False, size_mib=1536,
          password_stdin=False):
    if os.geteuid() != 0 or not 1024 <= size_mib <= 1900:
        raise ValueError('Use the root Linux builder and a 1024–1900 MiB root')
    if output.exists() or not output.parent.is_dir():
        raise ValueError('The kit must be a new directory below an existing output folder')
    password = None
    if password_stdin:
        password = sys.stdin.readline()
        if not password.endswith('\n') or not password.strip():
            raise ValueError('Supply the local nokia password on stdin')
    for path in (Path('/build/kernel/package'), Path('/build/module/package'),
                 Path('/build/mesa/package'), Path('/build/flasher'), Path('/build/runtime')):
        if not path.is_dir():
            raise ValueError('Missing source-built input: ' + str(path))
    work = Path('/work/internal')
    work.mkdir(parents=True, exist_ok=False)
    firmware = work / 'firmware'
    command = [sys.executable, str(HERE / 'firmware.py'), '--output', str(firmware),
               '--cache', str(cache)]
    if backup is not None:
        command += ['--backup', str(backup)]
    if offline:
        command.append('--offline')
    subprocess.run(command, check=True)
    debian = work / 'debian'
    command = [sys.executable, str(HERE / 'build_sd.py'), '--work', str(debian),
               '--kernel-package', '/build/kernel/package', '--ssh-key', str(ssh_key),
               '--firmware', str(firmware), '--user', 'nokia', '--root-only']
    if password_stdin:
        command.append('--password-stdin')
    subprocess.run(command, input=password, text=True, check=True)
    del password
    subprocess.run([sys.executable, str(HERE / 'stage_flasher.py'), '--root', str(debian / 'rootfs'),
                    '--build', '/build/flasher'], check=True)
    plan = {'root': str(debian / 'rootfs'), 'kernel_package': '/build/kernel/package',
            'gpu_runtime': '/build/runtime', 'gpu_module_package': '/build/module/package',
            'gpu_mesa_package': '/build/mesa/package', 'size_mib': size_mib}
    plan_path = work / 'plan.json'
    plan_path.write_text(json.dumps(plan) + '\n')
    subprocess.run([sys.executable, str(HERE / 'build_internal_image.py'),
                    '--plan', str(plan_path), '--output', str(output)], check=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ssh-key', type=Path, required=True)
    parser.add_argument('--firmware-cache', type=Path, required=True)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--size-mib', type=int, default=1536)
    parser.add_argument('--password-stdin', action='store_true')
    args = parser.parse_args()
    build(args.output, args.ssh_key, args.firmware_cache, args.backup, args.offline,
          args.size_mib, args.password_stdin)


if __name__ == '__main__':
    main()
