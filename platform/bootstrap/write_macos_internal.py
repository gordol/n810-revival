#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Install a verified kit through Maemo USB mass storage on macOS."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys

from internal_installer import partition_table, verify_local_kit

CAPACITY = 2013265920
OFFSET = 1024 * 1024
BLOCK = 4 * 1024 * 1024


def validate_disk(info, disk, location):
    if not re.fullmatch(r'/dev/disk[0-9]+', disk):
        raise ValueError('Select an explicit whole disk')
    checks = {'DeviceNode': disk, 'MediaName': 'N810', 'BusProtocol': 'USB',
              'Internal': False, 'WholeDisk': True, 'TotalSize': CAPACITY,
              'DeviceBlockSize': 512, 'Writable': True,
              'VirtualOrPhysical': 'Physical'}
    for key, expected in checks.items():
        if info.get(key) != expected:
            raise ValueError('Refusing unexpected disk property: ' + key)
    if not re.search(r'@' + format(location, '08x') + r'(?:/|$)',
                     info.get('DeviceTreePath', ''), re.I):
        raise ValueError('Disk is not on the selected tablet USB port')


def disk_info(disk, location):
    info = plistlib.loads(subprocess.check_output(['diskutil', 'info', '-plist', disk]))
    validate_disk(info, disk, location)
    return info


def image_blocks(manifest, root_image, capacity=CAPACITY):
    yield partition_table(manifest['disk_id'], capacity // 512)
    yield bytes(OFFSET - 512)
    remaining = manifest['root_bytes']
    checksum = hashlib.sha256()
    with gzip.open(root_image, 'rb') as source:
        while remaining:
            chunk = source.read(min(BLOCK, remaining))
            if not chunk or len(chunk) % 512:
                raise ValueError('Root image is truncated or unaligned')
            remaining -= len(chunk)
            checksum.update(chunk)
            yield chunk
        if source.read(1) or checksum.hexdigest() != manifest['root_sha256']:
            raise ValueError('Root image changed during writing')
    remaining = capacity - OFFSET - manifest['root_bytes']
    if remaining < 0:
        raise ValueError('Root image exceeds target capacity')
    while remaining:
        chunk = bytes(min(BLOCK, remaining))
        yield chunk
        remaining -= len(chunk)


def install(kit, disk, location, write=False):
    root, manifest, files = verify_local_kit(kit)
    from storage_target import require_target
    require_target(manifest,'internal')
    root = Path(kit).resolve()
    receipt = root / 'INSTALL-STATE.json'
    if receipt.exists() or receipt.is_symlink():
        raise ValueError('An installation receipt already exists; inspect it before retrying')
    info = disk_info(disk, location)
    print(f'Verified kit and {disk}: N810, {CAPACITY} bytes, USB port {location:08x}', flush=True)
    if not write:
        print('Check only. Nothing written.')
        return
    if os.geteuid() != 0:
        raise ValueError('Run the write with sudo; no disk write started')
    subprocess.run(['diskutil', 'unmountDisk', disk], check=True)
    if disk_info(disk, location).get('DeviceTreePath') != info['DeviceTreePath']:
        raise ValueError('Disk identity changed after unmount')
    raw = '/dev/r' + disk[5:]
    expected = hashlib.sha256()
    done = 0
    print('Writing Debian and clearing the remaining old internal-storage contents...', flush=True)
    with open(raw, 'r+b', buffering=0) as target:
        for chunk in image_blocks(manifest, files['root-filesystem']):
            view = memoryview(chunk)
            while view:
                count = target.write(view)
                if not count:
                    raise OSError('Short disk write')
                view = view[count:]
            expected.update(chunk)
            done += len(chunk)
            if done // (128 * 1024**2) != (done - len(chunk)) // (128 * 1024**2):
                print(f'Written {done // 1024**2} MiB', flush=True)
        os.fsync(target.fileno())
    if done != CAPACITY:
        raise ValueError('Wrong write length')
    subprocess.run(['sync'], check=True)
    print('Reading back all 2 GB...', flush=True)
    actual = hashlib.sha256()
    with open(raw, 'rb', buffering=0) as source:
        remaining = CAPACITY
        while remaining:
            chunk = source.read(min(BLOCK, remaining))
            if not chunk:
                raise OSError('Short disk readback')
            actual.update(chunk)
            remaining -= len(chunk)
    if actual.digest() != expected.digest():
        raise ValueError('Full disk readback mismatch; kernel flash is blocked')
    record = dict(version=1, state='rootfs_written', transport='maemo-usb-mass-storage',
                  device=disk, usb_location=location, root_sha256=manifest['root_sha256'],
                  kernel_sha256=manifest['kernel_sha256'], rootfs_readback_verified=True,
                  whole_disk_sha256=actual.hexdigest(), kernel_flashing_pending=True)
    with receipt.open('x') as output:
        json.dump(record, output, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    if os.environ.get('SUDO_UID') and os.environ.get('SUDO_GID'):
        os.chown(receipt, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
    subprocess.run(['diskutil', 'eject', disk], check=True)
    print('Full disk readback verified. Return ONLY the new tablet to update mode for its matching kernel.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit', type=Path, required=True)
    parser.add_argument('--disk', required=True)
    parser.add_argument('--usb-location', type=lambda value: int(value, 0), required=True)
    parser.add_argument('--write', action='store_true', help='erase and install the selected internal disk')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('This writer requires macOS')
    install(args.kit, args.disk, args.usb_location, args.write)
