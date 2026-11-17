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


def package_hashes(package: Path) -> dict[str, str]:
    """Hash packaged outputs, excluding the manifest left by a resumed build."""
    return {p.relative_to(package).as_posix(): digest(p)
            for p in sorted(package.rglob('*')) if p.is_file() and p != package / 'BUILD.json'}


def check_toolchain(lock, env):
    gcc = subprocess.check_output(['arm-linux-gnueabihf-gcc', '-dumpfullversion'], text=True, env=env).strip()
    ld = subprocess.check_output(['arm-linux-gnueabihf-ld', '--version'], text=True, env=env).splitlines()[0]
    want = lock['toolchain']
    if gcc != want['gcc_version'] or not ld.endswith(' ' + want['binutils_version']):
        raise RuntimeError(f"Use the OG toolchain: GCC {want['gcc_version']} and binutils {want['binutils_version']}; found GCC {gcc}, {ld}")


def main() -> None:
    """Build from repository inputs and emit a manifest with verification results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True, help='New directory for source, build, logs, and package')
    parser.add_argument('--archive', type=Path, help='Optional previously downloaded, checksum-matched upstream archive')
    parser.add_argument('--resume', action='store_true', help='Revalidate inputs and resume an existing interrupted build')
    parser.add_argument('--ram-installer', action='store_true', help='build the temporary NOLO initramfs installer kernel')
    parser.add_argument('--ab-boot', action='store_true', help='accept bootloader slot arguments; default to internal recovery')
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
                 'arm-linux-gnueabihf-gcc', 'arm-linux-gnueabihf-ld', 'arm-linux-gnueabihf-readelf', 'modprobe', 'modinfo', 'depmod']:
        if shutil.which(tool) is None:
            raise RuntimeError(f'Required build tool is missing: {tool}')
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=args.resume)
    logs = work / 'logs'; logs.mkdir(exist_ok=args.resume)
    package = work / 'package'; package.mkdir(exist_ok=args.resume)
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(('KBUILD_', 'KCONFIG_')) or key in ('MAKEFLAGS', 'MFLAGS', 'ARCH', 'CROSS_COMPILE', 'CC', 'HOSTCC', 'LOCALVERSION'):
            env.pop(key)
    env.update(LC_ALL='C', TZ='UTC', KBUILD_BUILD_USER='builder', KBUILD_BUILD_HOST='n810-build',
               KBUILD_BUILD_VERSION='1', KBUILD_BUILD_TIMESTAMP='Wed Nov 4 00:00:00 UTC 2026',
               SOURCE_DATE_EPOCH='1793750400')

    check_toolchain(lock, env)

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
    source = work / ('linux-' + lock['version'])
    if not args.resume:
        run(['tar', '-xJf', str(archive), '-C', str(work)], 'extract')
        run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(HERE / 'n810-5.15.224.patch')], 'patch', source)
    expected_files = json.loads((HERE / 'source-files.json').read_text())
    if not args.resume:
        for name, expected in expected_files.items():
            if digest(source / name) != expected:
                raise RuntimeError(f'Reconstructed maintained source differs: {name}')
        run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(HERE / 'n810-480mhz.patch')],
            'cpu-480mhz-patch', source)
    expected_files.update(json.loads((HERE / 'cpu-source-files.json').read_text()))
    if not args.resume:
        for name, expected in expected_files.items():
            if digest(source / name) != expected:
                raise RuntimeError(f'Reconstructed CPU profile differs: {name}')
        run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(HERE / 'n810-device-fixes.patch')],
            'device-fixes-patch', source)
    expected_files.update(json.loads((HERE / 'device-source-files.json').read_text()))
    for name, expected in expected_files.items():
        if digest(source / name) != expected:
            raise RuntimeError(f'Reconstructed source differs from maintained revision: {name}')
    build = work / 'build'; build.mkdir(exist_ok=args.resume)
    shutil.copyfile(HERE / 'n810.config', build / '.config')
    cmdline = (f'root={args.root_device} rootfstype=ext4 rw rootwait' if not args.ram_installer else
               'root=/dev/ram0 rw rdinit=/init') + \
              ' console=ttyS2,115200 console=tty0 omap2fb.auto_update=y loglevel=4 vt.rgb=1'
    config = [str(source / 'scripts/config'), '--file', str(build / '.config'),
              '--set-str', 'UNUSED_KSYMS_WHITELIST', str(HERE / 'binding-api-whitelist.txt'),
              '--set-str', 'CMDLINE', cmdline]
    if args.ab_boot:
        if args.ram_installer: raise ValueError('A/B recovery uses an ext4 internal root')
        config += ['--disable', 'CMDLINE_FORCE', '--enable', 'CMDLINE_FROM_BOOTLOADER',
                   '--enable', 'EXT4_FS_POSIX_ACL', '--enable', 'EXT4_FS_SECURITY']
    if args.ram_installer:
        config += ['--set-str', 'LOCALVERSION', '-n810-installer2', '--enable', 'BLK_DEV_INITRD',
                   '--enable', 'RD_XZ',
                   '--disable', 'EXT4_FS', '--disable', 'PM_DEBUG', '--disable', 'PM_SLEEP_DEBUG',
                   '--disable', 'DEBUG_BUGVERBOSE']
    run(config, 'configure')
    base = ['make', '-C', str(source), 'O=' + str(build), 'ARCH=arm',
            'CROSS_COMPILE=arm-linux-gnueabihf-', 'CC=arm-linux-gnueabihf-gcc', 'HOSTCC=gcc', 'LOCALVERSION=']
    run(base + ['olddefconfig'], 'olddefconfig')
    effective_config = (build / '.config').read_text().splitlines()
    if not {'CONFIG_CPU_FREQ_DEFAULT_GOV_POWERSAVE=y', 'CONFIG_CPU_FREQ_GOV_POWERSAVE=y'} <= set(effective_config):
        raise RuntimeError('Kernel must boot with the OG built-in powersave governor.')
    run(base + [f'-j{args.jobs}', 'zImage', 'modules', 'omap2420-n810.dtb'], 'kernel-and-modules')
    release = (build / 'include/config/kernel.release').read_text().strip()
    expected_release = lock['version'] + '-n810-installer2' if args.ram_installer else lock['release']
    if release != expected_release:
        raise RuntimeError(f'Unexpected release: {release}')
    module = work / 'clock-module'; shutil.copytree(HERE / 'clock-module', module, dirs_exist_ok=args.resume)
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
    module_root = package / 'root/lib/modules'
    if module_root.exists():
        shutil.rmtree(module_root)
    run(base + ['INSTALL_MOD_PATH=' + str(package / 'root'), 'modules_install'], 'stage-modules')
    # Kbuild creates development symlinks; the package retains relocatable files.
    for name in ['build', 'source']:
        link = package / 'root/lib/modules' / release / name
        if link.is_symlink():
            link.unlink()
    modules = list((package / 'root').rglob('*.ko'))
    # External initramfs decompression links five compression helpers into the
    # recovery kernel that are modules in the permanent build.
    expected_modules = lock['expected_modules'] - 5 if args.ram_installer else lock['expected_modules']
    if len(modules) != expected_modules:
        raise RuntimeError(f'Expected {expected_modules} configured modules; got {len(modules)}.')
    for relative, name in [('arch/arm/boot/zImage', 'zImage'),
                           ('arch/arm/boot/dts/omap2420-n810.dtb', 'omap2420-n810.dtb'),
                           ('Module.symvers', 'Module.symvers'), ('.config', 'kernel.config')]:
        shutil.copyfile(build / relative, package / name)
    # Preserve the running-kernel identity exposed by /sys/kernel/notes.
    # A release string or installed module tree can belong to another build.
    run(['arm-linux-gnueabihf-objcopy', '--dump-section',
         '.notes=' + str(package / 'kernel.notes'), str(build / 'vmlinux'), '/dev/null'],
        'kernel-notes')
    image = package / 'zImage-omap2420-n810'
    image.write_bytes((package / 'zImage').read_bytes() + (package / 'omap2420-n810.dtb').read_bytes())
    if not args.ab_boot and image.stat().st_size > lock['image_limit']:
        raise RuntimeError('Combined image exceeds the recorded NOLO image budget.')
    shutil.copyfile(ko, package / ko.name)
    (package / 'module-version-crcs.txt').write_text(versions)
    (package / 'KERNELRELEASE').write_text(release + '\n')
    compiler = subprocess.check_output(['arm-linux-gnueabihf-gcc', '--version'], text=True, env=env).splitlines()[0]
    report = {'release': release, 'kind': 'n810-ram-installer-kernel' if args.ram_installer else 'n810-permanent-kernel',
              'maintained_commit': lock['maintained_commit'],
              'cpu_profile': 'n810-330-480mhz', 'cpu_boot_governor': 'powersave',
              'cpu_patch_sha256': digest(HERE / 'n810-480mhz.patch'),
              'device_patch_sha256': digest(HERE / 'n810-device-fixes.patch'),
              'upstream_sha256': lock['sha256'], 'source_lock_sha256': digest(HERE / 'source.lock.json'),
              'build_script_sha256': digest(Path(__file__)), 'verified_source_files': len(expected_files),
              'compiler': compiler, 'build_timestamp': env['KBUILD_BUILD_TIMESTAMP'],
              'root_device': 'initramfs:/init' if args.ram_installer else args.root_device,
              'ab_boot': args.ab_boot,
              'vmlinux_sha256': digest(build / 'vmlinux'),
              'kernel_modules': len(modules),
              'external_module_crc_checks': len(crcs), 'external_module_vermagic': info,
              'image_bytes': image.stat().st_size, 'image_limit': None if args.ab_boot else lock['image_limit'],
              'device_action': False,
              'files': package_hashes(package)}
    (package / 'BUILD.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['release', 'kernel_modules', 'external_module_crc_checks', 'image_bytes', 'device_action']}, indent=2))
    print(f'Build complete: {package}')


if __name__ == '__main__':
    main()
