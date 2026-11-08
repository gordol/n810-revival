#!/usr/bin/env python3
"""Build a personalized Debian armel root and a raw N810 SD-card image on Linux."""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tarfile
import uuid

PACKAGES = (
    'systemd-sysv,dbus,udev,ifupdown,iproute2,openssh-server,sudo,'
    'ca-certificates,kmod,passwd,python3,python3-venv,make,git,tmux,whiptail,kbd,bluez'
)
SOURCES = (
    'deb https://deb.debian.org/debian bookworm main',
    'deb https://security.debian.org/debian-security bookworm-security main',
    'deb https://deb.debian.org/debian bookworm-updates main',
)
SECTOR = 512
OFFSET = 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def public_key(path: Path) -> str:
    line = path.read_text().strip()
    parts = line.split()
    if len(parts) < 2 or parts[0] != 'ssh-ed25519' or '\n' in line:
        raise ValueError('Supply one Ed25519 OpenSSH public key, such as id_ed25519.pub.')
    try:
        decoded = base64.b64decode(parts[1], validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError('SSH public key is not valid base64.') from error
    if len(decoded) != 51 or decoded[:4] != b'\x00\x00\x00\x0b' or decoded[4:15] != b'ssh-ed25519' \
            or decoded[15:19] != b'\x00\x00\x00\x20':
        raise ValueError('SSH public key is not a valid Ed25519 key record.')
    return line + '\n'


def kernel_inputs(package: Path) -> tuple[str, Path]:
    report = json.loads((package / 'BUILD.json').read_text())
    release = (package / 'KERNELRELEASE').read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9._+-]+', release) or report.get('release') != release:
        raise ValueError('Kernel package release does not match BUILD.json.')
    if report.get('root_device') != '/dev/mmcblk0p1':
        raise ValueError('Build the matching kernel with --root-device /dev/mmcblk0p1.')
    image = package / 'zImage-omap2420-n810'
    modules = package / 'root/lib/modules' / release
    if not image.is_file() or not modules.is_dir() or not list(modules.rglob('*.ko')):
        raise ValueError('Kernel package is missing its combined image or modules.')
    files = report.get('files', {})
    if files.get(image.name) != sha256(image):
        raise ValueError('Kernel image does not match BUILD.json.')
    for module in modules.rglob('*.ko'):
        if files.get(module.relative_to(package).as_posix()) != sha256(module):
            raise ValueError(f'Kernel module does not match BUILD.json: {module.name}')
    return release, modules


def mbr(partition_sectors: int, disk_id: int) -> bytes:
    if not 0 < partition_sectors < 2**32 - OFFSET // SECTOR:
        raise ValueError('SD partition size exceeds MBR limits.')
    record = bytearray(SECTOR)
    struct.pack_into('<I', record, 440, disk_id)
    # One Linux partition, beginning at 1 MiB. NOLO keeps its kernel elsewhere.
    struct.pack_into('<B3sB3sII', record, 446, 0, b'\xfe\xff\xff', 0x83,
                     b'\xfe\xff\xff', OFFSET // SECTOR, partition_sectors)
    record[510:512] = b'\x55\xaa'
    return bytes(record)


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def write_file(root: Path, name: str, contents: str, mode: int = 0o644) -> None:
    target = root / name.lstrip('/')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(contents)
    target.chmod(mode)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True, help='New local output directory; never a device path')
    parser.add_argument('--kernel-package', type=Path, required=True)
    parser.add_argument('--ssh-key', type=Path, required=True, help='Owner public key, not a private key')
    parser.add_argument('--user', default='nokia', help='First local account (default: nokia)')
    parser.add_argument('--size-mib', type=int, default=2048, help='Root partition size in MiB (default: 2048)')
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() != 0:
        parser.error('Run as root on a Linux builder or VM.')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}', args.user):
        parser.error('Invalid local account name.')
    if not 1024 <= args.size_mib <= 8191:
        parser.error('Choose a root partition between 1024 and 8191 MiB.')
    key = public_key(args.ssh_key)
    release, modules = kernel_inputs(args.kernel_package.resolve())
    for tool in ('mmdebstrap', 'chroot', 'mkfs.ext4', 'e2fsck', 'dpkg'):
        if shutil.which(tool) is None:
            parser.error(f'Missing Linux build tool: {tool}')
    native_armel = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip() == 'armel'
    if not native_armel:
        for tool in ('qemu-arm-static', 'arch-test'):
            if shutil.which(tool) is None:
                parser.error(f'Cross-architecture builders need {tool} and ARM binfmt support.')
    work = args.work.absolute()
    if work.exists() or work == Path('/') or str(work).startswith('/dev/'):
        parser.error('Use a new ordinary directory for --work, never a block device.')
    work.mkdir(mode=0o700, parents=True)
    root = work / 'rootfs'
    print('Building Debian Bookworm armel root filesystem', flush=True)
    run('mmdebstrap', '--mode=root', '--architectures=armel', '--variant=minbase',
        f'--include={PACKAGES}', 'bookworm', str(root), *SOURCES)
    # A cross-architecture chroot needs the static emulator inside the new root.
    emulator = root / 'usr/bin/qemu-arm-static'
    if not native_armel:
        shutil.copyfile(shutil.which('qemu-arm-static'), emulator)
    try:
        run('chroot', str(root), '/bin/true')
        run('chroot', str(root), 'useradd', '-m', '-s', '/bin/bash', '-G', 'sudo', args.user)
        print(f'Choose the local console/sudo password for {args.user}; it will not be saved in the manifest.', flush=True)
        run('chroot', str(root), 'passwd', args.user)
        ssh = root / 'home' / args.user / '.ssh'
        ssh.mkdir(mode=0o700)
        write_file(root, f'/home/{args.user}/.ssh/authorized_keys', key, 0o600)
        run('chroot', str(root), 'chown', '-R', f'{args.user}:{args.user}', f'/home/{args.user}/.ssh')
        run('chroot', str(root), 'passwd', '-l', 'root')
    finally:
        emulator.unlink(missing_ok=True)
    write_file(root, '/etc/hostname', 'n810\n')
    write_file(root, '/etc/hosts', '127.0.0.1 localhost\n127.0.1.1 n810\n')
    write_file(root, '/etc/network/interfaces',
               'auto lo\niface lo inet loopback\n\nallow-hotplug usb0\niface usb0 inet static\n'
               '    address 192.168.10.1\n    netmask 255.255.255.0\n')
    fs_uuid = str(uuid.uuid4())
    write_file(root, '/etc/fstab', f'UUID={fs_uuid} / ext4 defaults,noatime 0 1\n')
    write_file(root, '/etc/ssh/sshd_config.d/10-n810-first-install.conf',
               'PermitRootLogin no\nPasswordAuthentication no\nKbdInteractiveAuthentication no\n')
    write_file(root, '/etc/systemd/system/ssh.service.d/10-generate-host-keys.conf',
               '[Service]\nExecStartPre=/usr/bin/ssh-keygen -A\n')
    (root / 'etc/machine-id').write_text('')
    for seed in (root / 'var/lib/systemd/random-seed', root / 'var/lib/dbus/machine-id'):
        seed.unlink(missing_ok=True)
    for host_key in (root / 'etc/ssh').glob('ssh_host_*'):
        host_key.unlink()
    shutil.copytree(modules, root / 'lib/modules' / release, symlinks=True)
    partition = work / 'n810-root.ext4'
    partition_bytes = args.size_mib * 1024 * 1024
    with partition.open('wb') as image:
        image.truncate(partition_bytes)
    partition.chmod(0o600)
    run('mkfs.ext4', '-F', '-d', str(root), '-U', fs_uuid, '-L', 'n810-root',
        '-E', 'lazy_itable_init=0,lazy_journal_init=0', str(partition))
    run('e2fsck', '-fn', str(partition))
    disk_id = secrets.randbits(32)
    card = work / 'n810-sd.img'
    with card.open('wb') as output, partition.open('rb') as source:
        output.write(mbr(partition_bytes // SECTOR, disk_id))
        output.seek(OFFSET)
        shutil.copyfileobj(source, output, 4 * 1024 * 1024)
    card.chmod(0o600)
    boot_image = work / 'n810-kernel-ramboot.bin'
    shutil.copyfile(args.kernel_package / 'zImage-omap2420-n810', boot_image)
    module_archive = work / 'n810-modules.tar.gz'
    with tarfile.open(module_archive, 'w:gz') as archive:
        archive.add(modules, arcname=f'lib/modules/{release}')
    guide = work / 'BOOT.txt'
    guide.write_text(
        'N810 Debian armel first boot\n\n'
        'This kit contains a personal SD image. It has a local password hash and your SSH public key.\n'
        'Keep it private. The tablet is not installed merely by preparing this kit.\n\n'
        '1. Confirm the target is an N810 (RX-44), keep its stock recovery path, and use a card larger than n810-sd.img.\n'
        '2. On Linux, identify the card WHOLE DISK with lsblk. Unmount its partitions.\n'
        '3. Write the image: sudo dd if=n810-sd.img of=/dev/REPLACE_WITH_CARD_DISK bs=4M status=progress conv=fsync\n'
        '4. Reinsert the card and verify its single ext4 partition.\n'
        '5. Put the N810 into update mode. With 0xFFFF on the Linux flasher host, identify it:\n'
        '   sudo 0xFFFF -I\n'
        '6. For a temporary RAM boot, without flashing NAND, run:\n'
        '   sudo 0xFFFF -m kernel:n810-kernel-ramboot.bin -l -b\n'
        '7. Check console login, uname -r, /lib/modules, and USB networking before permanent changes.\n'
        'This generic first boot has not yet been accepted on a second N810.\n'
    )
    manifest = {
        'suite': 'bookworm', 'architecture': 'armel', 'kernel_release': release,
        'builder_sha256': sha256(Path(__file__)),
        'kernel_build_manifest_sha256': sha256(args.kernel_package / 'BUILD.json'),
        'apt_sources': SOURCES, 'packages_requested': PACKAGES.split(','),
        'kernel_image_sha256': sha256(boot_image),
        'root_device': '/dev/mmcblk0p1', 'user': args.user,
        'ssh_public_key_sha256': hashlib.sha256(key.encode()).hexdigest(),
        'password': 'chosen interactively; not recorded', 'ssh_password_login': False,
        'filesystem_uuid': fs_uuid, 'disk_id': f'{disk_id:08x}',
        'partition_start_sector': OFFSET // SECTOR, 'partition_sectors': partition_bytes // SECTOR,
        'debian_package_database_sha256': sha256(root / 'var/lib/dpkg/status'),
        'sd_image_sha256': sha256(card), 'device_action': False,
    }
    (work / 'BUILD.json').write_text(json.dumps(manifest, indent=2) + '\n')
    kit_files = [(card, 'system-image'), (boot_image, 'kernel'),
                 (module_archive, 'modules'), (guide, 'boot-guide')]
    kit_hashes = {'system-image': manifest['sd_image_sha256'],
                  'kernel': manifest['kernel_image_sha256']}
    installation = {
        'version': 1, 'kind': 'n810-system', 'release': f'bookworm-armel-{release}',
        'kernel_release': release,
        'files': [{'role': role, 'path': path.name, 'bytes': path.stat().st_size,
                   'sha256': kit_hashes.get(role) or sha256(path)} for path, role in kit_files],
    }
    (work / 'INSTALLATION.json').write_text(json.dumps(installation, indent=2) + '\n')
    # A sudo caller can inspect and use the kit without giving away the build root.
    if os.environ.get('SUDO_UID') and os.environ.get('SUDO_GID'):
        owner = (int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
        for path in (work, partition, card, boot_image, module_archive, guide,
                     work / 'BUILD.json', work / 'INSTALLATION.json'):
            os.chown(path, *owner)
    print(f'Image ready: {card}\nKernel for temporary NOLO boot: {boot_image}', flush=True)


if __name__ == '__main__':
    main()
