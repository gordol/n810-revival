#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Linux whole-device inspection and guarded internal/SD installation."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from internal_installer import verify_local_kit
from write_sd_card import blocks, OFFSET, BLOCK

SYS = Path('/sys')
INTERNAL_BYTES = 2013265920


def usb_parent(path):
    for parent in (path, *path.parents):
        if (parent/'idVendor').is_file() and (parent/'idProduct').is_file():
            return parent
    return None


def nokia_ports():
    return sorted(p.name for p in (SYS/'bus/usb/devices').glob('*')
                  if (p/'idVendor').is_file() and (p/'idVendor').read_text().strip().lower() == '0421')


def validate(info, storage, root_bytes, usb_port):
    if not re.fullmatch(r'[0-9]+-[0-9]+(?:\.[0-9]+)*', usb_port):
        raise ValueError('Choose the tablet USB topology port, for example 1-2.3')
    if storage not in ('sd', 'internal'):
        raise ValueError('Unknown storage target')
    if info['partition'] or info['readonly'] or info['sector_size'] != 512:
        raise ValueError('Select a writable whole disk with 512-byte logical sectors')
    if info['busy']:
        raise ValueError('Disk or a descendant is mounted, swap, or held by another block device; unmount it first')
    size = info['bytes']
    if not OFFSET + root_bytes <= size <= 0xffffffff * 512 or size % 512:
        raise ValueError('Unsupported disk size or root image does not fit')
    if storage == 'internal':
        if (size != INTERNAL_BYTES or info['usb_port'] != usb_port or
                info['usb_vendor'] != '0421' or info['model'] != 'N810'):
            raise ValueError('Internal target must be the selected N810 Maemo USB export, exactly 2 GB')
    elif not (info['usb_vendor'] != '0421' and info['removable'] and (info['usb_port'] or info['mmc_type'] == 'SD')):
        raise ValueError('SD target must be a removable USB-reader disk or an SD card')
    return info


def inspect(disk):
    path = Path(disk)
    if not re.fullmatch(r'/dev/(sd[a-z]+|mmcblk[0-9]+)', str(path)):
        raise ValueError('Select an explicit whole disk: /dev/sdX or /dev/mmcblkN')
    st = path.lstat()
    if not stat.S_ISBLK(st.st_mode):
        raise ValueError('Target must be a block device, not a file or symlink')
    node = (SYS/'class/block'/path.name).resolve(strict=True)
    def value(name, default=''):
        p = node/name
        return p.read_text().strip() if p.is_file() else default
    members = [node, *(p.parent for p in node.glob('*/partition'))]
    numbers = {p.joinpath('dev').read_text().strip() for p in members}
    busy = any(list((p/'holders').iterdir()) for p in members)
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        if line.split()[2] in numbers: busy = True
    for line in Path('/proc/swaps').read_text().splitlines()[1:]:
        try:
            swap = os.stat(line.split()[0])
            if stat.S_ISBLK(swap.st_mode) and f'{os.major(swap.st_rdev)}:{os.minor(swap.st_rdev)}' in numbers:
                busy = True
        except FileNotFoundError:
            raise ValueError('Swap topology changed; retry inspection')
    usb = usb_parent(node)
    return dict(device=str(path), sysfs=str(node), dev=value('dev'),
                bytes=int(value('size'))*512, sector_size=int(value('queue/logical_block_size')),
                readonly=value('ro') != '0', removable=value('removable') == '1',
                partition=(node/'partition').exists(), busy=busy,
                model=value('device/model'), serial=value('device/serial'), mmc_type=value('device/type'),
                usb_port=usb.name if usb else '',
                usb_vendor=(usb/'idVendor').read_text().strip().lower() if usb else '',
                usb_serial=(usb/'serial').read_text().strip() if usb and (usb/'serial').exists() else '')


def transfer(fd, manifest, image, capacity, progress):
    expected = hashlib.sha256(); written = 0
    for chunk in blocks(manifest, image, capacity):
        view = memoryview(chunk)
        while view:
            count = os.write(fd, view)
            if not count: raise OSError('Short disk write')
            view = view[count:]
        expected.update(chunk); written += len(chunk)
    os.fsync(fd)
    # Flush Linux block buffers before verifying through the same exclusively held descriptor.
    fcntl.ioctl(fd, 0x1261)  # BLKFLSBUF
    os.lseek(fd, 0, os.SEEK_SET)
    progress('Reading back the partition table and complete root filesystem…')
    actual = hashlib.sha256(); remaining = written
    while remaining:
        chunk = os.read(fd, min(BLOCK, remaining))
        if not chunk: raise OSError('Short disk readback')
        actual.update(chunk); remaining -= len(chunk)
    if actual.digest() != expected.digest():
        raise ValueError('Disk readback mismatch; no flash receipt will be created')
    return written, actual.hexdigest()


def install(kit, disk, usb_port, write=False, progress=print):
    if not sys.platform.startswith('linux'):
        raise ValueError('This writer requires a native Linux host')
    _, manifest, files = verify_local_kit(kit)
    storage = manifest.get('storage_target', 'internal')
    root = Path(kit).resolve(); receipt = root/'INSTALL-STATE.json'
    if receipt.exists() or receipt.is_symlink():
        raise ValueError('Kit already has a write receipt; inspect it before reusing')
    before = validate(inspect(disk), storage, manifest['root_bytes'], usb_port)
    progress(f'Checked {storage}: {disk}, {before["bytes"]} bytes, tablet port {usb_port}')
    if not write:
        return dict(state='linux_disk_checked', storage_target=storage, identity=before, device_action=False)
    if os.geteuid() != 0:
        raise ValueError('Run the explicit write with sudo')
    # O_EXCL refuses devices mounted/claimed between inspection and open. O_NOFOLLOW
    # prevents a replacement symlink; fstat and sysfs rechecks bind the descriptor.
    fd = os.open(disk, os.O_RDWR | os.O_EXCL | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISBLK(st.st_mode) or f'{os.major(st.st_rdev)}:{os.minor(st.st_rdev)}' != before['dev']:
            raise ValueError('Block device identity changed while opening')
        if validate(inspect(disk), storage, manifest['root_bytes'], usb_port) != before:
            raise ValueError('Disk identity changed while opening')
        written, digest = transfer(fd, manifest, files['root-filesystem'], before['bytes'], progress)
        if inspect(disk) != before:
            raise ValueError('Disk identity changed during writing')
        record = dict(version=1, state='rootfs_written', storage_target=storage,
                      transport='linux-block-device', device=disk, usb_port=usb_port,
                      disk_identity=before, root_sha256=manifest['root_sha256'],
                      kernel_sha256=manifest['kernel_sha256'], rootfs_readback_verified=True,
                      written_bytes=written, written_sha256=digest, kernel_flashing_pending=True)
        out = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(out, 'w') as stream:
            json.dump(record, stream, indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        if os.environ.get('SUDO_UID') and os.environ.get('SUDO_GID'):
            os.chown(receipt, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
    finally:
        os.close(fd)
    progress('Write verified. Disconnect the storage, insert the SD card if applicable, and put the target tablet in update mode on the selected USB port.')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit', type=Path, required=True)
    parser.add_argument('--disk', required=True)
    parser.add_argument('--usb-port', required=True)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    install(args.kit, args.disk, args.usb_port, args.write)


if __name__ == '__main__': main()
