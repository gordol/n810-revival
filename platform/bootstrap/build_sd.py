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

BASE_PACKAGES = (
    'dbus,udev,ifupdown,iproute2,openssh-server,sudo,chrony,ntpsec-ntpdate,psmisc,procps,rsync,usbutils,python3-serial,python3-dbus,python3-gi,python3-msgpack,python3-cryptography,python3-pycryptodome,python3-bleak,'
    'dropbear-bin,kexec-tools,busybox,ca-certificates,kmod,passwd,python3,python3-venv,make,git,tmux,whiptail,kbd,bluez,wpasupplicant,iw,wireless-regdb,isc-dhcp-client,util-linux,mount,libusb-0.1-4,libbz2-1.0'
)
PACKAGES = 'systemd-sysv,' + BASE_PACKAGES
INTERNAL_PACKAGES = 'sysvinit-core,initscripts,sysvinit-utils,' + BASE_PACKAGES
SOURCES = tuple(Path(__file__).with_name('debian.sources.list').read_text().splitlines())

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


def kernel_inputs(package: Path, *, root_only: bool = False) -> tuple[str, Path]:
    report = json.loads((package / 'BUILD.json').read_text())
    release = (package / 'KERNELRELEASE').read_text().strip()
    if not re.fullmatch(r'[A-Za-z0-9._+-]+', release) or report.get('release') != release:
        raise ValueError('Kernel package release does not match BUILD.json.')
    expected = (r'PARTUUID=[0-9a-f]{8}-01' if root_only else r'/dev/mmcblk0p1')
    if not re.fullmatch(expected, report.get('root_device', '')):
        raise ValueError('Kernel root-device does not match the selected image layout.')
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
    parser.add_argument('--firmware', type=Path, required=True, help='Validated local firmware directory')
    parser.add_argument('--touch-tools', type=Path, default=Path('/opt/n810-touch'))
    parser.add_argument('--user', default='nokia', help='First local account (default: nokia)')
    parser.add_argument('--size-mib', type=int, default=2048, help='Root partition size in MiB (default: 2048)')
    parser.add_argument('--root-only', action='store_true',
                        help='Stage a Debian root for an internal PARTUUID image; skip the SD filesystem and card')
    parser.add_argument('--password-stdin', action='store_true',
                        help='Read the local user password from stdin for a guided non-TTY build')
    args = parser.parse_args()
    if sys.platform != 'linux' or os.geteuid() != 0:
        parser.error('Run as root on a Linux builder or VM.')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}', args.user):
        parser.error('Invalid local account name.')
    if not 1024 <= args.size_mib <= 8191:
        parser.error('Choose a root partition between 1024 and 8191 MiB.')
    key = public_key(args.ssh_key)
    release, modules = kernel_inputs(args.kernel_package.resolve(), root_only=args.root_only)
    for tool in ('mmdebstrap', 'chroot', 'mkfs.ext4', 'e2fsck', 'dpkg'):
        if shutil.which(tool) is None:
            parser.error(f'Missing Linux build tool: {tool}')
    native_armel = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip() == 'armel'
    if not native_armel:
        for tool in ('qemu-arm-static', 'arch-test'):
            if shutil.which(tool) is None:
                parser.error(f'Cross-architecture builders need {tool} and ARM binfmt support.')
    for name in ('n810-touch-calibrate', 'n810-fn-remap', 'n810-backlightd',
                 'n810-touch-fit.py', 'touch-runtime/touch_evdev.py'):
        if not (args.touch_tools / name).is_file():
            parser.error('Missing touch tools; use make sd-image or supply --touch-tools.')
    if args.root_only and not (args.touch_tools / 'n810-wake').is_file():
        parser.error('Internal root needs the ARM n810-wake lock-slider helper.')
    from firmware import validate
    firmware_lock = json.loads(Path(__file__).with_name('firmware.lock.json').read_text())['files']
    for name, record in firmware_lock.items():
        validate((args.firmware / name).read_bytes(), record)
    work = args.work.absolute()
    if work.exists() or work == Path('/') or str(work).startswith('/dev/'):
        parser.error('Use a new ordinary directory for --work, never a block device.')
    work.mkdir(mode=0o700, parents=True)
    root = work / 'rootfs'
    print('Building Debian Bookworm armel root filesystem', flush=True)
    packages = INTERNAL_PACKAGES if args.root_only else PACKAGES
    run('mmdebstrap', '--mode=root', '--architectures=armel', '--variant=minbase',
        f'--include={packages}', 'bookworm', str(root), *SOURCES)
    # A cross-architecture chroot needs the static emulator inside the new root.
    emulator = root / 'usr/bin/qemu-arm-static'
    if not native_armel:
        shutil.copyfile(shutil.which('qemu-arm-static'), emulator)
    try:
        run('chroot', str(root), '/bin/true')
        run('chroot', str(root), 'useradd', '-m', '-s', '/bin/bash', '-G', 'sudo', args.user)
        if args.password_stdin or args.root_only:
            password = sys.stdin.readline().rstrip('\n') if args.password_stdin else 'nokia'
            if not password or '\r' in password:
                parser.error('Supply a nonempty local password on stdin')
            subprocess.run(['chroot', str(root), 'chpasswd'], input=f'{args.user}:{password}\n',
                           text=True, check=True)
            del password
        else:
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
               'auto lo\niface lo inet loopback\n\nauto usb0\niface usb0 inet static\n'
               '    address 192.168.10.1\n    netmask 255.255.255.0\n')
    fs_uuid = str(uuid.uuid4())
    write_file(root, '/etc/fstab', f'UUID={fs_uuid} / ext4 defaults,noatime 0 1\n')
    write_file(root, '/etc/ssh/sshd_config.d/10-n810-first-install.conf',
               'PermitRootLogin no\nPasswordAuthentication no\nKbdInteractiveAuthentication no\n')
    (root / 'etc/machine-id').write_text('')
    for seed in (root / 'var/lib/systemd/random-seed', root / 'var/lib/dbus/machine-id'):
        seed.unlink(missing_ok=True)
    for host_key in (root / 'etc/ssh').glob('ssh_host_*'):
        host_key.unlink()
    shutil.copytree(modules, root / 'lib/modules' / release, symlinks=True)
    # Public or owner-supplied firmware remains part of this private image only.
    for name,destination in [('3826.arm','usr/lib/firmware/3826.arm'),('bc4fw.bin','usr/lib/firmware/nokia/bc4fw.bin')]:
        target=root/destination;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(args.firmware/name,target);target.chmod(0o644)
    shutil.copyfile(args.firmware/'FIRMWARE.json',work/'FIRMWARE.json')
    (root/'usr/local/sbin').mkdir(parents=True,exist_ok=True)
    platform=Path(__file__).resolve().parents[1]
    for name in ('n810-bluetooth-address','n810-wifi-service'):
        shutil.copyfile(platform/'scripts'/name,root/'usr/local/sbin'/name)
        (root/'usr/local/sbin'/name).chmod(0o755)
    write_file(root,'/etc/systemd/system/n810-bluetooth-address.service',
               (platform/'device/n810-bluetooth-address.service').read_text())
    write_file(root,'/etc/systemd/system/bluetooth.service.d/10-n810-address.conf',
               (platform/'device/10-n810-address.conf').read_text())
    write_file(root,'/etc/systemd/system/n810-wifi.service',
               (platform/'device/n810-wifi.service').read_text().replace('[Unit]',
               '[Unit]\nConditionPathExists=/etc/wpa_supplicant/wpa_supplicant-wlan0.conf'))
    shutil.copyfile(platform/'device/n810-zram.init', root/'usr/local/sbin/n810-zram')
    (root/'usr/local/sbin/n810-zram').chmod(0o755)
    write_file(root, '/etc/default/n810-zram', (platform/'device/n810-zram.defaults').read_text())
    write_file(root, '/etc/systemd/system/n810-zram.service',
               (platform/'device/n810-zram.service').read_text())
    write_file(root,'/etc/modules-load.d/n810-wifi.conf','p54spi\n')
    write_file(root,'/etc/modules-load.d/n810-bluetooth.conf','hci_uart\nhci_nokia\n')
    # First-boot setup uses the same collector and fit tool as the bring-up work.
    write_file(root, '/etc/modules-load.d/n810-touch.conf', 'tsc2005\n')
    touch_source = args.touch_tools
    shutil.copytree(touch_source, root / 'usr/local/lib/n810-touch')
    shutil.copyfile(Path(__file__).with_name('setup_touch.py'), root / 'usr/local/lib/n810-touch/setup_touch.py')
    write_file(root, '/usr/local/sbin/n810-setup-touch',
               '#!/bin/sh\nexec python3 /usr/local/lib/n810-touch/setup_touch.py "$@"\n', 0o755)
    write_file(root, '/etc/systemd/system/n810-setup-touch.service',
               Path(__file__).with_name('n810-setup-touch.service').read_text())
    wants = root / 'etc/systemd/system/multi-user.target.wants'
    wants.mkdir(parents=True, exist_ok=True)
    (wants / 'n810-setup-touch.service').symlink_to('../n810-setup-touch.service')
    (wants / 'n810-zram.service').symlink_to('../n810-zram.service')
    from first_boot import configure_first_boot
    configure_first_boot(root, args.touch_tools / 'n810-fn-remap',
                         args.touch_tools / 'n810-backlightd',
                         args.touch_tools / 'n810-wake' if args.root_only else None)
    state = root / 'home' / args.user / '.local/state/current-world'
    state.mkdir(parents=True, exist_ok=True)
    (state / 'touch-calibration.json').symlink_to('/etc/n810/touch-calibration.json')
    owner = (root / 'home' / args.user).stat()
    for directory in (state.parent.parent, state.parent, state):
        os.chown(directory, owner.st_uid, owner.st_gid)
    if args.root_only:
        report = {
            'kind': 'n810-debian-root', 'suite': 'bookworm', 'architecture': 'armel',
            'kernel_release': release,
            'kernel_build_manifest_sha256': sha256(args.kernel_package / 'BUILD.json'),
            'root_device': json.loads((args.kernel_package / 'BUILD.json').read_text())['root_device'],
            'init_system': 'sysvinit', 'packages_requested': packages.split(','),
            'user': args.user, 'ssh_public_key_sha256': hashlib.sha256(key.encode()).hexdigest(),
            'firmware': json.loads((work / 'FIRMWARE.json').read_text()),
            'debian_package_database_sha256': sha256(root / 'var/lib/dpkg/status'),
            'device_action': False,
        }
        (work / 'BUILD.json').write_text(json.dumps(report, indent=2) + '\n')
        print(f'Internal-image Debian root ready: {root}', flush=True)
        return
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
        'apt_sources': SOURCES, 'packages_requested': packages.split(','),
        'kernel_image_sha256': sha256(boot_image),
        'firmware': json.loads((work/'FIRMWARE.json').read_text()),
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
