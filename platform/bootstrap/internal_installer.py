#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify, boot, and install a Pocket Debian kit on an N810 internal MMC."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import socket
import struct
import subprocess
import sys
import time

REPOSITORY = Path(__file__).resolve().parents[2]
DEFAULT_FLASHER = REPOSITORY / 'dist/flasher/0xFFFF'
REQUIRED_ROLES = {'root-filesystem', 'kernel', 'install-plan',
                  'kernel-build-manifest', 'install-guide'}
RECOVERY_ROLES = {'installer-kernel', 'installer-filesystem',
                  'installer-build-manifest', 'installer-host-key'}
FIRST_BOOT_SERVICES = {
    'n810-setup-touch.service', 'n810-fn-remap.service',
    'n810-keyboard.service', 'n810-backlightd.service',
    'n810-powerd.service', 'n810-ledd.service', 'n810-display-keys.service',
    'pocket-desktop.service',
}


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def _artifact(root, row):
    name = row.get('path')
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('Invalid installation artifact path')
    relative = Path(name)
    if relative.is_absolute() or any(part in ('.', '..') for part in relative.parts):
        raise ValueError('Installation artifact must stay inside the kit')
    path = root
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Installation artifacts cannot be symlinks: ' + name)
    if not path.is_file():
        raise ValueError('Missing installation artifact: ' + name)
    size = row.get('bytes')
    expected = row.get('sha256')
    if type(size) is not int or size <= 0 or path.stat().st_size != size:
        raise ValueError('Installation artifact size differs: ' + name)
    if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected):
        raise ValueError('Invalid installation artifact checksum: ' + name)
    if digest(path) != expected:
        raise ValueError('Installation artifact checksum differs: ' + name)
    return path


def verify_local_kit(kit):
    """Verify every kit file and the expanded root image without contacting USB."""
    requested = Path(kit).expanduser()
    if requested.is_symlink():
        raise ValueError('Internal-install kit folder cannot be a symlink')
    root = requested.resolve()
    if not root.is_dir():
        raise ValueError('Choose an existing internal-install kit folder')
    installation_path = root / 'INSTALLATION.json'
    internal_path = root / 'INTERNAL.json'
    if installation_path.is_symlink() or internal_path.is_symlink():
        raise ValueError('Kit manifests cannot be symlinks')
    installation = json.loads(installation_path.read_text())
    if (type(installation.get('version')) is not int or installation.get('version') != 1 or
            installation.get('kind') != 'n810-internal'):
        raise ValueError('Expected an N810 internal-install kit')
    rows = installation.get('files')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Internal kit has no files')
    files = {}
    paths = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('Invalid installation artifact record')
        role = row.get('role')
        name = row.get('path')
        if (not isinstance(role, str) or role in files or
                not isinstance(name, str) or not name):
            raise ValueError('Missing or duplicate installation artifact role')
        if name in paths:
            raise ValueError('Duplicate installation artifact path')
        files[role] = _artifact(root, row)
        paths.add(name)
    missing = REQUIRED_ROLES - set(files)
    if missing:
        raise ValueError('Internal kit is incomplete: ' + ', '.join(sorted(missing)))
    if set(files) not in (REQUIRED_ROLES, REQUIRED_ROLES | RECOVERY_ROLES):
        raise ValueError('Internal kit has incomplete or unexpected RAM-installer artifacts')
    has_recovery = RECOVERY_ROLES <= set(files)

    manifest = json.loads(internal_path.read_text())
    if manifest.get('kind') != 'n810-internal':
        raise ValueError('Invalid internal-install plan')
    disk_id = manifest.get('disk_id')
    if not isinstance(disk_id, str) or not re.fullmatch(r'[0-9a-f]{8}', disk_id):
        raise ValueError('Invalid install partition identity')
    if files['install-plan'] != internal_path:
        raise ValueError('Installation plan role must name INTERNAL.json')
    image_size = manifest.get('root_bytes')
    image_sha = manifest.get('root_sha256')
    if type(image_size) is not int or not 0 < image_size <= 1900 * 1024 ** 2:
        raise ValueError('Invalid root image size')
    if not isinstance(image_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', image_sha):
        raise ValueError('Invalid root image checksum')
    kernel = files['kernel']
    if kernel != root / 'kernel.bin' or kernel.stat().st_size > 2097152:
        raise ValueError('Unexpected permanent kernel image')
    if digest(kernel) != manifest.get('kernel_sha256'):
        raise ValueError('Permanent kernel checksum differs from install plan')
    if has_recovery:
        if files['installer-kernel'].stat().st_size > 2097152:
            raise ValueError('RAM-installer kernel exceeds the NOLO 2 MiB limit')
        if files['installer-filesystem'].stat().st_size > 4194304:
            raise ValueError('RAM-installer filesystem exceeds the NOLO 4 MiB limit')
        if files['installer-filesystem'].read_bytes()[:6] != b'\xfd7zXZ\x00':
            raise ValueError('RAM-installer filesystem is not an XZ-compressed cpio initramfs')

    kernel_build = json.loads(files['kernel-build-manifest'].read_text())
    if (files['kernel-build-manifest'] != root / 'KERNEL-BUILD.json' or
            kernel_build.get('release') != manifest.get('kernel_release') or
            kernel_build.get('root_device') != 'PARTUUID=' + disk_id + '-01' or
            kernel_build.get('files', {}).get('zImage-omap2420-n810') != digest(kernel)):
        raise ValueError('Permanent kernel build manifest does not match the internal install plan')
    if has_recovery:
        installer_build = json.loads(files['installer-build-manifest'].read_text())
        if (files['installer-build-manifest'] != root / 'INSTALLER-BUILD.json' or
                installer_build.get('kind') != 'n810-ram-installer' or
                installer_build.get('filesystem_format') != 'cpio-xz' or
                installer_build.get('root_device') != 'initramfs:/init' or
                installer_build.get('kernel_release') != manifest.get('installer_kernel_release') or
                installer_build.get('files', {}).get('kernel.bin') != digest(files['installer-kernel']) or
                installer_build.get('files', {}).get('initramfs.cpio.xz') != digest(files['installer-filesystem'])):
            raise ValueError('RAM-installer build manifest does not match the staged installer files')
    if manifest.get('kernel_package_manifest_sha256') != digest(files['kernel-build-manifest']):
        raise ValueError('Source build manifest checksum differs from the internal install plan')
    if has_recovery and manifest.get('ram_installer_manifest_sha256') != digest(files['installer-build-manifest']):
        raise ValueError('RAM installer manifest checksum differs from the internal install plan')
    if not has_recovery and manifest.get('install_transport') != 'maemo-usb-mass-storage':
        raise ValueError('Kit without a RAM installer requires the Maemo USB storage transport')

    root_image = files['root-filesystem']
    expanded = hashlib.sha256()
    count = 0
    opener = gzip.open if root_image.suffix == '.gz' else open
    with opener(root_image, 'rb') as source:
        while block := source.read(1024 * 1024):
            count += len(block)
            if count > image_size:
                raise ValueError('Expanded root exceeds its declared size')
            expanded.update(block)
    if count != image_size or expanded.hexdigest() != image_sha:
        raise ValueError('Expanded root image checksum differs from install plan')
    if root_image.suffix == '.gz' and digest(root_image) != manifest.get('compressed_root_sha256'):
        raise ValueError('Compressed root checksum differs from install plan')

    desktop = manifest.get('desktop')
    if manifest.get('desktop_ready') is not True or not isinstance(desktop, dict):
        raise ValueError('Kit lacks the staged Pocket desktop')
    if desktop.get('desktop_user') != 'nokia' or desktop.get('autostart') is not True:
        raise ValueError('Kit does not autostart Pocket as user nokia')
    first_boot = manifest.get('first_boot')
    if not isinstance(first_boot, dict) or first_boot.get('profile') != 'n810-internal-v3':
        raise ValueError('Kit predates the verified keyboard and power first-boot profile; rebuild it')
    services = first_boot.get('enabled_services')
    if (not isinstance(services, list) or any(not isinstance(name, str) for name in services)
            or len(services) != len(set(services)) or not FIRST_BOOT_SERVICES <= set(services)):
        raise ValueError('Kit lacks required first-boot services')
    for name in ('root_manifest_sha256', 'keyboard_remapper_sha256', 'keyboard_backlight_sha256'):
        if not isinstance(first_boot.get(name), str) or not re.fullmatch(r'[0-9a-f]{64}', first_boot[name]):
            raise ValueError('Kit lacks first-boot source and helper checksums')
    if desktop.get('renderer') != 'native-mbx-gpu' or any(
            not isinstance(desktop.get(name), str) or not re.fullmatch(r'[0-9a-f]{64}', desktop[name])
            for name in ('module_sha256', 'mesa_sha256')):
        raise ValueError('Kit lacks the matching MBX GPU desktop')
    if not isinstance(manifest.get('kernel_release'), str) or not manifest['kernel_release']:
        raise ValueError('Missing matching kernel release')
    return installation, manifest, files


def _flasher_command(flasher, args):
    requested = Path(flasher).expanduser()
    if requested.is_symlink():
        raise ValueError('Host flasher cannot be a symlink')
    binary = requested.resolve()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise ValueError('Build the host flasher first with make flasher')
    record_path = binary.parent / 'BUILD.json'
    if record_path.is_symlink() or not record_path.is_file():
        raise ValueError('Host flasher has no build provenance; rebuild it with make flasher')
    record = json.loads(record_path.read_text())
    identity = record.get('identity', {})
    lock = json.loads((Path(__file__).resolve().parents[1] / 'flasher' / 'source.lock.json').read_text())
    if (identity.get('usb_only') is not True or identity.get('source_revision') != lock['revision'] or
            identity.get('source_sha256') != lock['sha256'] or
            record.get('binary_sha256') != digest(binary)):
        raise ValueError('Host flasher provenance or checksum differs from the pinned USB-only build')
    if platform.system() == 'Darwin' and identity.get('nolo_only') is not True:
        raise ValueError('macOS flasher must be built for Nokia update mode only')
    command = [str(binary), *args]
    # Keep Pocket unprivileged; macOS libusb access needs prior sudo authorization.
    if platform.system() == 'Darwin' and os.geteuid() != 0:
        helper = Path('/Library/PrivilegedHelperTools/org.n810-revival.flasher/helper')
        marker = helper.parent / 'ORIGINAL-SHA256'
        if helper.is_file() and marker.is_file():
            if helper.stat().st_uid != 0 or marker.read_text().strip() != record['binary_sha256']:
                raise ValueError('Installed USB helper differs from this flasher build')
            return ['sudo', '-n', str(helper), *args]
        command = ['sudo', '-n', *command]
    return command


def _run_flasher(flasher, args, timeout, log_path=None):
    command = _flasher_command(flasher, args)
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('0xFFFF timed out; no later installer step was started') from error
    output = (result.stdout or '') + '\n' + (result.stderr or '')
    if log_path is not None:
        log_path = Path(log_path)
        if log_path.is_symlink():
            raise ValueError('USB operation log cannot be a symlink')
        descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, 'a') as stream:
            stream.write('\n=== ' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) +
                         ' ' + ' '.join(args) + ' ===\n')
            stream.write(output)
            if not output.endswith('\n'):
                stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
    # Pinned 0xFFFF has legacy paths that print an Error diagnostic but later
    # reset their process status to zero. Never advance a destructive flow on
    # exit status alone.
    diagnostic_error = re.search(r'(?:^|\n)Error:\s', output) is not None
    if result.returncode or diagnostic_error:
        if 'password is required' in output or 'a password is required' in output:
            raise RuntimeError('Authorize USB access first by running sudo -v in the launching terminal')
        raise RuntimeError('0xFFFF failed (exit ' + str(result.returncode) + '): ' +
                           output[-512:].strip())
    return output


def _update_mode_locations():
    if platform.system() != 'Darwin':
        return []
    result = subprocess.run(['ioreg', '-p', 'IOUSB', '-l', '-w0'], capture_output=True,
                            text=True, check=True)
    pattern = (r'Nokia N810 \(Update mode\)@[0-9A-Fa-f]+[\s\S]*?'
               r'"USB Product Name" = "Nokia N810 _Update mode_"[\s\S]*?'
               r'"locationID" = ([0-9]+)[\s\S]*?"idVendor" = 1057')
    return [int(value) for value in re.findall(pattern, result.stdout)]


def identify_device(flasher=DEFAULT_FLASHER, progress=None, timeout=30):
    """Run the read-only 0xFFFF identity query and admit only an RX-44 N810."""
    if progress:
        progress('Identifying the tablet in Nokia update mode…')
    locations = _update_mode_locations()
    if platform.system() == 'Darwin' and len(locations) != 1:
        raise ValueError('Expected exactly one macOS USB update-mode N810; detected ' + str(len(locations)))
    output = _run_flasher(flasher, ['-I'], timeout)
    models = set(re.findall(r'^(?:Detected USB device|Device):\s*(RX-[0-9]+)\b', output, re.MULTILINE))
    if models != {'RX-44'}:
        raise ValueError('Expected exactly one Nokia N810 RX-44 in update mode; detected: ' +
                         (', '.join(sorted(models)) or 'no supported model'))
    result = {'state': 'device_identified', 'model': 'RX-44'}
    if locations:
        result['usb_location'] = locations[0]
    return result


def boot_installer(kit, flasher=DEFAULT_FLASHER, progress=None):
    root = Path(kit).expanduser().resolve()
    _, manifest, files = verify_local_kit(root)
    if not RECOVERY_ROLES <= set(files):
        raise ValueError('This kit uses Maemo USB storage and contains no RAM installer')
    identity = identify_device(flasher, progress)
    if progress:
        progress('Loading the verified RAM installer; internal storage is unchanged…')
    _run_flasher(flasher, ['-m', 'kernel:' + str(files['installer-kernel']),
                           '-m', 'initfs:' + str(files['installer-filesystem']), '-l', '-b'], 180,
                 root / 'USB-OPERATIONS.log')
    return {'state': 'ram_installer_booted', 'model': 'RX-44',
            'kernel_release': manifest['kernel_release'], 'internal_storage_changed': False,
            **({'usb_location': identity['usb_location']} if 'usb_location' in identity else {})}


def configure_installer_network(previous_interfaces, progress=None, timeout=45):
    """Assign the host end only on the newly appeared macOS USB interface."""
    if platform.system() != 'Darwin':
        return None
    helper = Path('/Library/PrivilegedHelperTools/org.n810-revival.flasher/helper')
    deadline = time.monotonic() + timeout
    while True:
        current = {name for _, name in socket.if_nameindex()}
        candidates = sorted(name for name in current - previous_interfaces
                            if re.fullmatch(r'en[0-9]{1,2}', name))
        if len(candidates) == 1:
            if progress:
                progress('Configuring the new tablet USB network interface…')
            result = subprocess.run(['sudo', '-n', str(helper), '--configure-network', candidates[0]],
                                    stdin=subprocess.DEVNULL, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError('Installed USB helper cannot configure the new interface; reinstall the prepared helper')
            return candidates[0]
        if len(candidates) > 1:
            raise RuntimeError('More than one new host network interface appeared; no internal write was started')
        if time.monotonic() >= deadline:
            raise RuntimeError('The RAM installer did not expose a new USB network interface; no internal write was started')
        time.sleep(1)


INVENTORY = r'''set -eu
test -f /etc/pocket-installer
grep -qi 'N810' /proc/device-tree/model
for disk in /sys/block/mmcblk*; do
 test -f "$disk/device/type" || continue
 printf '%s %s %s %s\n' "$(basename "$disk")" "$(cat "$disk/device/type")" "$(cat "$disk/size")" "$(cat "$disk/device/cid)"
done
'''

RECOVERY_IDENTITY = r'''set -eu
test -f /etc/pocket-installer
printf 'release='; uname -r
printf 'cmdline='; cat /proc/cmdline
printf 'rootfs='; stat -f -c %T /
printf 'pid1='; readlink /proc/1/exe
'''


def internal_target(text, image_bytes):
    if type(image_bytes) is not int or image_bytes <= 0:
        raise ValueError('Invalid root image size')
    rows = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 4:
            raise ValueError('Invalid installer disk inventory')
        name, kind, sectors, cid = fields
        if not re.fullmatch(r'mmcblk[0-9]+', name) or not re.fullmatch(r'[0-9a-fA-F]{32}', cid):
            raise ValueError('Invalid MMC identity')
        if not sectors.isdecimal():
            raise ValueError('Invalid MMC capacity')
        if kind == 'MMC':
            rows.append(dict(device='/dev/' + name, cid=cid, sectors=int(sectors)))
    if len(rows) != 1:
        raise ValueError('Expected exactly one internal MMC; no storage changed')
    target = rows[0]
    if not 1024 ** 3 <= target['sectors'] * 512 <= 4 * 1024 ** 3:
        raise ValueError('Unexpected N810 internal storage capacity')
    if image_bytes > (target['sectors'] - 2048) * 512:
        raise ValueError('Root filesystem does not fit internal storage')
    return target


def partition_table(disk_id, sectors):
    """Return a single-partition DOS MBR spanning the N810 internal MMC."""
    if not re.fullmatch(r'[0-9a-f]{8}', disk_id) or not 4096 <= sectors <= 0xffffffff:
        raise ValueError('Invalid internal MMC partition identity or capacity')
    table = bytearray(512)
    struct.pack_into('<I', table, 440, int(disk_id, 16))
    entry = struct.pack('<B3sB3sII', 0, b'\x20\x21\x00', 0x83, b'\xfe\xff\xff',
                        2048, sectors - 2048)
    table[446:462] = entry
    table[510:512] = b'\x55\xaa'
    return bytes(table)


class Installer:
    def __init__(self, kit, host, key=None):
        self.kit = Path(kit).expanduser().resolve()
        if not re.fullmatch(r'[a-zA-Z0-9.:_-]+', host):
            raise ValueError('Invalid installer host')
        self.ssh = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                    '-o', 'StrictHostKeyChecking=yes',
                    '-o', 'UserKnownHostsFile=' + str(self.kit / 'installer-known-hosts')]
        if key:
            self.ssh += ['-i', str(Path(key).expanduser())]
        self.ssh += ['root@' + host]

    def remote(self, command, **kwargs):
        return subprocess.run([*self.ssh, command], check=True, **kwargs)

    def inspect(self):
        _, manifest, files = verify_local_kit(self.kit)
        if not RECOVERY_ROLES <= set(files):
            raise ValueError('This kit uses Maemo USB storage and contains no RAM installer')
        self._manifest = manifest
        self._files = files
        identity_text = self.remote(RECOVERY_IDENTITY, stdout=subprocess.PIPE, text=True).stdout
        identity = dict(line.split('=', 1) for line in identity_text.splitlines() if '=' in line)
        if (identity.get('release') != manifest.get('installer_kernel_release') or
                'root=/dev/ram0' not in identity.get('cmdline', '') or
                'rdinit=/init' not in identity.get('cmdline', '') or
                identity.get('rootfs') not in ('rootfs', 'ramfs', 'tmpfs') or
                identity.get('pid1') != '/bin/busybox'):
            raise ValueError('SSH peer is not the verified RAM initramfs installer; no storage changed')
        text = self.remote(INVENTORY, stdout=subprocess.PIPE, text=True).stdout
        target = internal_target(text, manifest['root_bytes'])
        return manifest, target

    def install(self):
        manifest, target = self.inspect()
        device = target['device']
        name = device[5:]
        cid = target['cid']
        guard = '\n'.join((
            'set -eu',
            'test -f /etc/pocket-installer',
            f'test \"$(cat /sys/block/{name}/device/cid)\" = {shlex.quote(cid)}',
            f'test \"$(cat /sys/block/{name}/device/type)\" = MMC',
            f"if grep -q '^/dev/{name}' /proc/mounts; then echo 'Internal disk is mounted' >&2; exit 1; fi",
            '',
        ))
        partition = partition_table(manifest['disk_id'], target['sectors'])
        self.remote(guard + 'dd of=' + device + ' bs=512 count=1 conv=fsync; ' +
                    'partprobe ' + device + '; ' +
                    f'for i in 1 2 3 4 5; do test -b {device}p1 && exit 0; sleep 1; done; exit 1',
                    input=partition)
        root_image = self._files['root-filesystem']
        command = (('gzip -dc | ' if root_image.suffix == '.gz' else '') +
                   'dd of=' + device + 'p1 bs=1048576 conv=fsync')
        with root_image.open('rb') as source:
            self.remote(guard + command, stdin=source)
        written = self.remote(guard + f"head -c {manifest['root_bytes']} {device}p1 | sha256sum",
                              stdout=subprocess.PIPE, text=True).stdout.split()[0]
        if written != manifest['root_sha256']:
            raise ValueError('Internal root image readback checksum mismatch')
        self.remote(guard + 'sync')
        return dict(device=device, sectors=target['sectors'], cid=cid,
                    root_sha256=manifest['root_sha256'], kernel_sha256=manifest['kernel_sha256'],
                    rootfs_written=True, kernel_flashing_pending=True)


def install_root(kit, host='169.254.81.1', key=None, progress=None):
    requested = Path(kit).expanduser()
    if requested.is_symlink():
        raise ValueError('Internal-install kit folder cannot be a symlink')
    root = requested.resolve()
    receipt_path = root / 'INSTALL-STATE.json'
    if receipt_path.exists() or receipt_path.is_symlink():
        raise ValueError('This kit already has an internal-write receipt; inspect it before retrying')
    if progress:
        progress('Checking RAM-installer identity and internal MMC; no write has started…')
    result = Installer(kit, host, key).install()
    receipt = dict(version=1, state='rootfs_written', root_sha256=result['root_sha256'],
                   kernel_sha256=result['kernel_sha256'], target_cid=result['cid'],
                   device=result['device'], rootfs_readback_verified=True,
                   kernel_flashing_pending=True)
    temporary = root / '.INSTALL-STATE.json.tmp'
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, receipt_path)
    result.pop('cid', None)
    result.pop('root_sha256', None)
    result.pop('kernel_sha256', None)
    result['state'] = 'rootfs_written'
    return result


def install_device(kit, flasher=DEFAULT_FLASHER, host='169.254.81.1', key=None, progress=None, cancelled=None):
    """Run the permanent installation, waiting for the attended update-mode transition."""
    root = Path(kit).expanduser().resolve()
    def checkpoint():
        if cancelled is not None and cancelled.is_set():
            raise InterruptedError('Install paused between device operations; inspect the saved kit receipt before resuming')
    checkpoint()
    verify_local_kit(root)
    receipt = root / 'INSTALL-STATE.json'
    if not receipt.exists():
        previous_interfaces = {name for _, name in socket.if_nameindex()}
        boot_result = boot_installer(root, flasher, progress)
        configure_installer_network(previous_interfaces, progress)
        if progress:
            progress('Installer booting. Waiting for its pinned USB SSH connection…')
        installer = Installer(root, host, key)
        deadline = time.monotonic() + 240
        while True:
            checkpoint()
            try:
                installer.remote('test -f /etc/pocket-installer', stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                break
            except (subprocess.CalledProcessError, OSError):
                if time.monotonic() >= deadline:
                    raise RuntimeError('RAM installer did not connect over USB; no internal write was started')
                time.sleep(2)
        checkpoint()
        install_root(root, host, key, progress)
        if 'usb_location' in boot_result:
            receipt_data = json.loads(receipt.read_text())
            receipt_data['usb_location'] = boot_result['usb_location']
            temporary = root / '.INSTALL-STATE.json.tmp'
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(descriptor, 'w') as stream:
                json.dump(receipt_data, stream, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, receipt)
        checkpoint()
        if progress:
            progress('Root readback verified. Powering off the new tablet; hold Home while powering it on to enter update mode.')
        try:
            # PID 1 is the recovery shell, so BusyBox must invoke the reboot
            # syscall directly instead of signalling an init daemon.
            installer.remote('sync; poweroff -f', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            pass  # A poweroff may disconnect SSH before its exit status arrives.
    if progress:
        progress('Root verified. Waiting for the same new tablet in update mode: hold Home while powering it on. Keep the original tablet running.')
    deadline = time.monotonic() + 600
    while True:
        checkpoint()
        try:
            identify_device(flasher, timeout=5)
            break
        except (ValueError, RuntimeError):
            if time.monotonic() >= deadline:
                raise RuntimeError('Root is installed and verified; return the new tablet to update mode and resume Install')
            time.sleep(2)
    checkpoint()
    return flash_kernel(root, flasher, progress)


def flash_kernel(kit, flasher=DEFAULT_FLASHER, progress=None):
    _, manifest, files = verify_local_kit(kit)
    root = Path(kit).expanduser().resolve()
    receipt_path = root / 'INSTALL-STATE.json'
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError('Write and verify the internal root before flashing its kernel')
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get('version') != 1 or receipt.get('state') != 'rootfs_written' or
            receipt.get('rootfs_readback_verified') is not True or
            receipt.get('root_sha256') != manifest['root_sha256'] or
            receipt.get('kernel_sha256') != manifest['kernel_sha256'] or
            receipt.get('kernel_flashing_pending') is not True):
        raise ValueError('Internal-write receipt does not match this kit')
    identity = identify_device(flasher, progress)
    if ('usb_location' in receipt and
            identity.get('usb_location') != receipt['usb_location']):
        raise ValueError('Update-mode tablet is on a different USB port than the verified internal write')
    if progress:
        progress('Flashing the matching kernel and rebooting the N810…')
    _run_flasher(flasher, ['-m', 'kernel:' + str(files['kernel']), '-f', '-r'], 180,
                 root / 'USB-OPERATIONS.log')
    receipt.update(state='kernel_flashed_reboot_requested', kernel_flashing_pending=False)
    temporary = root / '.INSTALL-STATE.json.tmp'
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(receipt, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, receipt_path)
    return {'state': 'kernel_flashed_reboot_requested', 'model': 'RX-44',
            'kernel_release': manifest['kernel_release'], 'rootfs_readback_verified': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest='action', required=True)
    check = sub.add_parser('check', help='verify the local install kit without USB access')
    check.add_argument('--kit', required=True, type=Path)
    detect = sub.add_parser('identify', help='identify an N810 in Nokia update mode (read-only)')
    detect.add_argument('--flasher', type=Path, default=DEFAULT_FLASHER)
    boot = sub.add_parser('boot', help='boot the verified installer kernel and initramfs in RAM')
    boot.add_argument('--kit', required=True, type=Path)
    boot.add_argument('--flasher', type=Path, default=DEFAULT_FLASHER)
    write = sub.add_parser('write', help='erase and install the verified Debian root on internal MMC')
    write.add_argument('--kit', required=True, type=Path)
    write.add_argument('--host', default='169.254.81.1')
    write.add_argument('--key', type=Path)
    flash = sub.add_parser('flash-kernel', help='flash the matching kernel and reboot the N810')
    flash.add_argument('--kit', required=True, type=Path)
    flash.add_argument('--flasher', type=Path, default=DEFAULT_FLASHER)
    install = sub.add_parser('install', help='run the complete attended permanent internal installation')
    install.add_argument('--kit', required=True, type=Path)
    install.add_argument('--flasher', type=Path, default=DEFAULT_FLASHER)
    install.add_argument('--host', default='169.254.81.1')
    install.add_argument('--key', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == 'check':
            installation, manifest, files = verify_local_kit(args.kit)
            result = dict(state='files_verified', release=installation['release'],
                          kernel_release=manifest['kernel_release'], roles=sorted(files),
                          root_bytes=manifest['root_bytes'], desktop_user='nokia',
                          autostart=True, device_action=False)
        elif args.action == 'identify':
            result = identify_device(args.flasher)
        elif args.action == 'boot':
            result = boot_installer(args.kit, args.flasher)
        elif args.action == 'write':
            result = install_root(args.kit, args.host, args.key)
        elif args.action == 'install':
            result = install_device(args.kit, args.flasher, args.host, args.key,
                                    progress=lambda message: print(message, flush=True))
        else:
            result = flash_kernel(args.kit, args.flasher)
    except (OSError, ValueError, RuntimeError, gzip.BadGzipFile) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
