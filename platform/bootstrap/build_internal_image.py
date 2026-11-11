#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build a private internal-MMC install kit from staged Debian and ARM Pocket roots."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from build_sd import sha256


def checked_package(package):
    report=json.loads((package/'BUILD.json').read_text())
    match=re.fullmatch(r'PARTUUID=([0-9a-f]{8})-01',report['root_device'])
    if not match:raise ValueError('Internal kernel must boot its stable PARTUUID partition')
    for name,digest in report['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid kernel package path')
        if sha256(package/relative)!=digest:raise ValueError('Kernel package checksum differs: '+name)
    return report,match[1]


def build(root,package,recovery,output,size_mib):
    if root.resolve()==Path('/') or not 1024<=size_mib<=1900:
        raise ValueError('Use a separate Debian build root and 1024–1900 MiB filesystem')
    report,disk_id=checked_package(package)
    install=json.loads((root/'usr/local/share/pocket/INSTALL.json').read_text())
    if install.get('autostart') is not True:raise ValueError('Pocket desktop autostart is not staged')
    runtime=root/'usr/local/share/pocket'
    payload=json.loads((runtime/'runtime-profile.json').read_text())
    for name,digest in payload['files'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts:raise ValueError('Invalid runtime path')
        if sha256(runtime/path)!=digest:raise ValueError('Staged runtime checksum differs: '+name)
    flasher=root/'usr/local/bin/0xFFFF'
    flasher_record=json.loads((root/'usr/local/share/doc/0xffff/BUILD.json').read_text())
    if flasher_record['identity'].get('usb_only') is not True or flasher_record['identity'].get('target')!='armel':
        raise ValueError('Stage the USB-only ARM flasher before building the image')
    if sha256(flasher)!=flasher_record['binary_sha256']:
        raise ValueError('Staged flasher checksum differs')
    recovery_report=json.loads((recovery/'BUILD.json').read_text())
    for name,digest in recovery_report['files'].items():
        if Path(name).name!=name or sha256(recovery/name)!=digest:raise ValueError('RAM-installer checksum differs')
    if not (root/'etc/systemd/system/multi-user.target.wants/pocket-desktop.service').is_symlink():
        raise ValueError('Desktop service is not enabled')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    release=report['release']
    destination=root/'lib/modules'/release
    if destination.exists():shutil.rmtree(destination)
    shutil.copytree(package/'root/lib/modules'/release,destination,symlinks=True)
    filesystem_uuid=str(uuid.uuid4())
    fstab=root/'etc/fstab'
    lines=[line for line in fstab.read_text().splitlines() if not (len(line.split())>=2 and line.split()[1]=='/')]
    fstab.write_text('\n'.join([f'UUID={filesystem_uuid} / ext4 defaults,noatime 0 1',*lines])+'\n')
    image=output/'root.ext4'
    with image.open('wb') as stream:stream.truncate(size_mib*1024*1024)
    image.chmod(0o600)
    subprocess.run(['mkfs.ext4','-F','-d',str(root),'-U',filesystem_uuid,'-L','n810-root',
                    '-E','lazy_itable_init=0,lazy_journal_init=0',str(image)],check=True)
    subprocess.run(['e2fsck','-fn',str(image)],check=True)
    compressed=output/'root.ext4.gz'
    with image.open('rb') as source,compressed.open('wb') as target:
        with gzip.GzipFile(fileobj=target,mode='wb',compresslevel=1,mtime=0,filename='') as archive:
            shutil.copyfileobj(source,archive,4*1024*1024)
    compressed.chmod(0o600)
    shutil.copyfile(package/'zImage-omap2420-n810',output/'kernel.bin')
    for source,target in (('kernel.bin','installer-kernel.bin'),('initramfs.cpio.xz','installer-initramfs.cpio.xz'),
                          ('installer-known-hosts','installer-known-hosts')):
        shutil.copyfile(recovery/source,output/target)
    manifest=dict(kind='n810-internal',disk_id=disk_id,filesystem_uuid=filesystem_uuid,
                  kernel_release=release,kernel_sha256=sha256(output/'kernel.bin'),
                  root_bytes=image.stat().st_size,root_sha256=sha256(image),
                  compressed_root_sha256=sha256(compressed),desktop_ready=True,desktop=install,
                  kernel_package_manifest_sha256=sha256(package/'BUILD.json'),
                  ram_installer_manifest_sha256=sha256(recovery/'BUILD.json'),
                  device_action=False,hardware_acceptance=False)
    (output/'INTERNAL.json').write_text(json.dumps(manifest,indent=2)+'\n')
    guide=output/'INSTALL.txt'
    guide.write_text('Pocket internal installation integration kit\n\n'
        'This private kit replaces the target N810 internal MMC; no SD card is required.\n'
        'The installer kernel and filesystem run temporarily in RAM while internal storage is replaced.\n'
        'The root includes the Pocket release runtime and GUI autostart as the local account.\n'
        'The first-install renderer is native CPU framebuffer; GPU service installation is separate.\n'
        'This is WIP: device boot, internal erase/write, kernel installation and GUI acceptance are not completed by building or checking this kit.\n'
        'The internal-installer backend currently writes and verifies the root, then reports kernel_flashing_pending.\n'
        'Do not treat rootfs_written as a complete installation or reboot before the matching permanent kernel is installed.\n'
        'Keep the kit private: its filesystem contains the local account password hash.\n')
    roles={'root-filesystem':'root.ext4.gz','kernel':'kernel.bin','installer-kernel':'installer-kernel.bin',
           'installer-filesystem':'installer-initramfs.cpio.xz','install-plan':'INTERNAL.json',
           'installer-host-key':'installer-known-hosts','install-guide':'INSTALL.txt'}
    (output/'INSTALLATION.json').write_text(json.dumps(dict(version=1,kind='n810-internal',
        release='bookworm-internal-'+release,kernel_release=release,
        files=[dict(role=role,path=name,bytes=(output/name).stat().st_size,sha256=sha256(output/name))
               for role,name in roles.items()]),indent=2)+'\n')
    print(json.dumps(dict(state='internal_kit_built',output=str(output),root_bytes=image.stat().st_size,
                          compressed_bytes=compressed.stat().st_size,device_action=False)))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','kernel-package','recovery','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--size-mib',type=int,default=1536);a=p.parse_args()
    if os.geteuid()!=0:p.error('Run on the Linux builder as root')
    os.umask(0o077)
    build(a.root.resolve(),a.kernel_package.resolve(),a.recovery.resolve(),a.output.resolve(),a.size_mib)

if __name__=='__main__':main()
