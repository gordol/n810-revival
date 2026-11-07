#!/usr/bin/env python3
"""Fetch pinned source and build the N810 kernel in a new Linux work directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    """Return a file's SHA-256 without loading the full archive into memory."""
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    """Build from repository inputs and emit a manifest with verification results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True, help='New directory for source, build, logs, and package')
    parser.add_argument('--archive', type=Path, help='Optional previously downloaded, checksum-matched upstream archive')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--root-device', default='/dev/mmcblk0p2', help='Root device or PARTUUID= value for the intended filesystem')
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Run this build in Linux with the ARM cross-toolchain installed.')
    if args.jobs < 1 or not re.fullmatch(r'(?:/dev/[A-Za-z0-9/_-]+|PARTUUID=[A-Za-z0-9-]+)', args.root_device):
        parser.error('Use positive jobs and a /dev/... or PARTUUID=... root device.')
    lock = json.loads((HERE / 'source.lock.json').read_text())
    for name, expected in lock['inputs'].items():
        if digest(HERE / name) != expected:
            raise RuntimeError(f'Repository input changed: {name}; review and update source.lock.json.')
    for tool in ['curl', 'tar', 'xz', 'patch', 'make', 'gcc', 'flex', 'bison', 'bc',
                 'arm-linux-gnueabihf-gcc', 'arm-linux-gnueabihf-readelf', 'modprobe', 'modinfo', 'depmod']:
        if shutil.which(tool) is None:
            raise RuntimeError(f'Required build tool is missing: {tool}')
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    logs = work / 'logs'; logs.mkdir()
    package = work / 'package'; package.mkdir()
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('KBUILD_', 'KCONFIG_')) or key in ('MAKEFLAGS', 'MFLAGS', 'ARCH', 'CROSS_COMPILE', 'CC', 'HOSTCC', 'LOCALVERSION'):
            env.pop(key)
    env.update(LC_ALL='C', TZ='UTC', KBUILD_BUILD_USER='builder', KBUILD_BUILD_HOST='n810-build',
               KBUILD_BUILD_VERSION='1', KBUILD_BUILD_TIMESTAMP='Wed Nov 4 00:00:00 UTC 2026',
               SOURCE_DATE_EPOCH='1793750400')

    def run(command: list[str], label: str, cwd: Path | None = None) -> None:
        print(label, flush=True)
        with (logs / (label + '.log')).open('wb') as output:
            result = subprocess.run(command, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'{label} failed; inspect {logs / (label + ".log")}')

    archive = args.archive.resolve() if args.archive else work / 'linux.tar.xz'
    if args.archive is None:
        run(['curl', '--fail', '--location', '--proto', '=https', '--tlsv1.2', '--retry', '3',
             '--output', str(archive), lock['url']], 'download')
    if digest(archive) != lock['sha256']:
        raise RuntimeError('Upstream source archive checksum mismatch.')
    run(['tar', '-xJf', str(archive), '-C', str(work)], 'extract')
    source = work / ('linux-' + lock['version'])
    run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(HERE / 'n810-5.15.224.patch')], 'patch', source)
    expected_files = json.loads((HERE / 'source-files.json').read_text())
    for name, expected in expected_files.items():
        if digest(source / name) != expected:
            raise RuntimeError(f'Reconstructed source differs from maintained revision: {name}')
    build = work / 'build'; build.mkdir()
    shutil.copyfile(HERE / 'n810.config', build / '.config')
    cmdline = f'root={args.root_device} rootfstype=ext4 rw rootwait console=ttyS2,115200 console=tty0 omap2fb.auto_update=y loglevel=4 vt.rgb=1'
    run([str(source / 'scripts/config'), '--file', str(build / '.config'),
         '--set-str', 'UNUSED_KSYMS_WHITELIST', str(HERE / 'binding-api-whitelist.txt'),
         '--set-str', 'CMDLINE', cmdline], 'configure')
    base = ['make', '-C', str(source), 'O=' + str(build), 'ARCH=arm',
            'CROSS_COMPILE=arm-linux-gnueabihf-', 'CC=arm-linux-gnueabihf-gcc', 'HOSTCC=gcc', 'LOCALVERSION=']
    run(base + ['olddefconfig'], 'olddefconfig')
    run(base + [f'-j{args.jobs}', 'zImage', 'modules', 'omap2420-n810.dtb'], 'kernel-and-modules')
    release = (build / 'include/config/kernel.release').read_text().strip()
    if release != lock['release']:
        raise RuntimeError(f'Unexpected release: {release}')
    module = work / 'clock-module'; shutil.copytree(HERE / 'clock-module', module)
    run(base + ['M=' + str(module), 'modules'], 'clock-module')
    exports = {line.split()[1]: line.split()[0] for line in (build / 'Module.symvers').read_text().splitlines()}
    required = set((HERE / 'binding-api-whitelist.txt').read_text().splitlines())
    if not required <= exports.keys():
        raise RuntimeError('Required external-module exports are missing.')
    ko = module / 'n810_mbx_clock_trial.ko'
    versions = subprocess.check_output(['modprobe', '--dump-modversions', str(ko)], env=env, text=True)
    crcs = {line.split()[1]: line.split()[0] for line in versions.splitlines()}
    if not crcs or any(exports.get(name) != crc for name, crc in crcs.items()):
        raise RuntimeError('External module symbol versions differ from this build.')
    info = subprocess.check_output(['modinfo', '-F', 'vermagic', str(ko)], env=env, text=True).strip()
    if not info.startswith(release + ' '):
        raise RuntimeError('External module release mismatch.')
    run(base + ['INSTALL_MOD_PATH=' + str(package / 'root'), 'modules_install'], 'stage-modules')
    # Kbuild creates development symlinks; the package retains relocatable files.
    for name in ['build', 'source']:
        link = package / 'root/lib/modules' / release / name
        if link.is_symlink():
            link.unlink()
    modules = list((package / 'root').rglob('*.ko'))
    if len(modules) != lock['expected_modules']:
        raise RuntimeError(f'Expected {lock["expected_modules"]} configured modules; got {len(modules)}.')
    for relative, name in [('arch/arm/boot/zImage', 'zImage'),
                           ('arch/arm/boot/dts/omap2420-n810.dtb', 'omap2420-n810.dtb'),
                           ('Module.symvers', 'Module.symvers'), ('.config', 'kernel.config')]:
        shutil.copyfile(build / relative, package / name)
    image = package / 'zImage-omap2420-n810'
    image.write_bytes((package / 'zImage').read_bytes() + (package / 'omap2420-n810.dtb').read_bytes())
    if image.stat().st_size > lock['image_limit']:
        raise RuntimeError('Combined image exceeds the recorded NOLO image budget.')
    shutil.copyfile(ko, package / ko.name)
    (package / 'module-version-crcs.txt').write_text(versions)
    (package / 'KERNELRELEASE').write_text(release + '\n')
    compiler = subprocess.check_output(['arm-linux-gnueabihf-gcc', '--version'], text=True, env=env).splitlines()[0]
    report = {'release': release, 'maintained_commit': lock['maintained_commit'],
              'upstream_sha256': lock['sha256'], 'source_lock_sha256': digest(HERE / 'source.lock.json'),
              'build_script_sha256': digest(Path(__file__)), 'verified_source_files': len(expected_files),
              'compiler': compiler, 'build_timestamp': env['KBUILD_BUILD_TIMESTAMP'],
              'root_device': args.root_device, 'kernel_modules': len(modules),
              'external_module_crc_checks': len(crcs), 'external_module_vermagic': info,
              'image_bytes': image.stat().st_size, 'image_limit': lock['image_limit'],
              'device_action': False,
              'files': {p.relative_to(package).as_posix(): digest(p) for p in sorted(package.rglob('*')) if p.is_file()}}
    (package / 'BUILD.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['release', 'kernel_modules', 'external_module_crc_checks', 'image_bytes', 'device_action']}, indent=2))
    print(f'Build complete: {package}')


if __name__ == '__main__':
    main()
