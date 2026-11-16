#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Install a verified USB-only ARM 0xFFFF build into a separate Debian root."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def stage(root, build):
    if root.resolve() == Path('/'):
        raise ValueError('Use a separate image root')
    record = json.loads((build / 'BUILD.json').read_text())
    identity = record['identity']
    if identity.get('target') != 'armel' or identity.get('usb_only') is not True:
        raise ValueError('The Nokia image requires the USB-only ARM build')
    files = {'0xFFFF': record['binary_sha256'],
             'source.tar.gz': identity['source_sha256'],
             'usb-host.patch': identity['usb_host_patch_sha256']}
    for name, expected in files.items():
        path = build / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Flasher checksum differs: ' + name)
    header = (build / '0xFFFF').read_bytes()[:20]
    if header[:5] != b'\x7fELF\x01' or header[18:20] != b'\x28\x00':
        raise ValueError('The flasher must be ARM ELF32')
    if not (build / 'COPYING').is_file():
        raise ValueError('Missing upstream license')
    binary = root / 'usr/local/bin/0xFFFF'
    docs = root / 'usr/local/share/doc/0xffff'
    binary.parent.mkdir(parents=True, exist_ok=True)
    docs.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(build / '0xFFFF', binary)
    binary.chmod(0o755)
    for name in ('BUILD.json', 'source.tar.gz', 'usb-host.patch', 'COPYING'):
        shutil.copyfile(build / name, docs / name)
        (docs / name).chmod(0o644)
    # Standalone Linux provisioning CLI, usable on the N810 without a compiler.
    bundle = root / 'usr/local/lib/n810-installer'
    (bundle/'bootstrap').mkdir(parents=True, exist_ok=True)
    (bundle/'flasher').mkdir(exist_ok=True)
    for name in ('internal_installer.py', 'linux_storage.py', 'write_sd_card.py',
                 'storage_target.py', 'provision.py'):
        shutil.copyfile(Path(__file__).with_name(name), bundle/'bootstrap'/name)
        (bundle/'bootstrap'/name).chmod(0o644)
    for name in ('0xFFFF', 'BUILD.json'):
        shutil.copyfile(build/name, bundle/'flasher'/name)
    shutil.copyfile(Path(__file__).resolve().parents[1]/'flasher/source.lock.json',
                    bundle/'flasher/source.lock.json')
    for path in (bundle, *bundle.rglob('*')):
        path.chmod(0o755 if path.is_dir() else 0o644)
    (bundle/'flasher/0xFFFF').chmod(0o755)
    launcher = root/'usr/local/sbin/n810-provision'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text('#!/bin/sh\nexec /usr/bin/python3 /usr/local/lib/n810-installer/bootstrap/provision.py "$@"\n')
    launcher.chmod(0o755)
    return {'binary_sha256': record['binary_sha256'], 'source_revision': identity['source_revision']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--build', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(stage(args.root, args.build)))


if __name__ == '__main__':
    main()
