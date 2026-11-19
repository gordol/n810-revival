#!/usr/bin/env python3
"""Prepare a verified SD-root kit on a removable card; never writes tablet MMC."""
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
from internal_installer import verify_local_kit,partition_table
from storage_target import require_target

OFFSET=1024*1024
BLOCK=4*1024*1024


def validate_card(info,disk,root_bytes):
    if not re.fullmatch(r'/dev/disk[0-9]+',disk):raise ValueError('Choose a macOS whole disk, /dev/diskN')
    if (info.get('DeviceNode')!=disk or info.get('WholeDisk') is not True or
        info.get('VirtualOrPhysical')!='Physical' or info.get('Writable') is not True or
        info.get('DeviceBlockSize')!=512 or info.get('RemovableMedia') is not True):
        raise ValueError('Refusing a fixed, virtual, read-only or non-removable disk')
    capacity=info.get('TotalSize')
    if type(capacity) is not int or not OFFSET+root_bytes<=capacity<=0xffffffff*512 or capacity%512:
        raise ValueError('Card capacity is unsupported or the root image does not fit')
    if not info.get('DeviceTreePath'):raise ValueError('Card reader has no stable device-tree identity')
    return capacity


def fingerprint(info):
    return {k:info.get(k) for k in ('DeviceNode','DeviceTreePath','TotalSize','MediaName','DeviceBlockSize','RemovableMedia','VirtualOrPhysical')}


def blocks(manifest,image,capacity):
    yield partition_table(manifest['disk_id'],capacity//512)
    yield bytes(OFFSET-512)
    remaining=manifest['root_bytes'];digest=hashlib.sha256()
    with gzip.open(image,'rb') as source:
        while remaining:
            chunk=source.read(min(BLOCK,remaining))
            if not chunk or len(chunk)%512:raise ValueError('Truncated or unaligned root image')
            digest.update(chunk);remaining-=len(chunk);yield chunk
        if source.read(1) or digest.hexdigest()!=manifest['root_sha256']:raise ValueError('Root image changed during writing')


def install(kit,disk,usb_location,write=False,progress=print):
    if sys.platform!='darwin':raise ValueError('The SD card writer currently requires macOS diskutil')
    _,manifest,files=verify_local_kit(kit);require_target(manifest,'sd')
    if type(usb_location) is not int or not 0<usb_location<=0xffffffff:raise ValueError('Pin the target tablet USB location for the later kernel flash')
    root=Path(kit).resolve();receipt=root/'INSTALL-STATE.json'
    if receipt.exists() or receipt.is_symlink():raise ValueError('This kit already has a write receipt; inspect it before writing another card')
    def inspect():
        info=plistlib.loads(subprocess.check_output(['diskutil','info','-plist',disk]))
        validate_card(info,disk,manifest['root_bytes']);return info
    before=inspect();capacity=before['TotalSize']
    progress(f'Checked removable card {disk}: {capacity} bytes; root {manifest["root_bytes"]} bytes')
    if not write:return dict(state='sd_card_checked',storage_target='sd',device=disk,device_action=False)
    if os.geteuid()!=0:raise ValueError('Run the explicit card write with sudo')
    subprocess.run(['diskutil','unmountDisk',disk],check=True)
    if fingerprint(inspect())!=fingerprint(before):raise ValueError('Card identity changed after unmount')
    expected=hashlib.sha256();written=0
    raw='/dev/r'+disk[5:]
    with open(raw,'r+b',buffering=0) as target:
        for chunk in blocks(manifest,files['root-filesystem'],capacity):
            view=memoryview(chunk)
            while view:
                count=target.write(view)
                if not count:raise OSError('Short card write')
                view=view[count:]
            expected.update(chunk);written+=len(chunk)
        os.fsync(target.fileno())
    if written!=OFFSET+manifest['root_bytes']:raise ValueError('Incorrect card write length')
    progress('Reading back the partition table and complete root image…')
    actual=hashlib.sha256()
    with open(raw,'rb',buffering=0) as source:
        remaining=written
        while remaining:
            chunk=source.read(min(BLOCK,remaining))
            if not chunk:raise OSError('Short card readback')
            actual.update(chunk);remaining-=len(chunk)
    if actual.digest()!=expected.digest():raise ValueError('Card readback mismatch; kernel flash is blocked')
    record=dict(version=1,state='rootfs_written',storage_target='sd',transport='sd-card-reader',
        device=disk,usb_location=usb_location,card_identity=fingerprint(before),
        root_sha256=manifest['root_sha256'],kernel_sha256=manifest['kernel_sha256'],
        rootfs_readback_verified=True,written_bytes=written,written_sha256=actual.hexdigest(),kernel_flashing_pending=True)
    fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(record,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    if os.environ.get('SUDO_UID') and os.environ.get('SUDO_GID'):os.chown(receipt,int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
    subprocess.run(['diskutil','eject',disk],check=True)
    progress('Verified. Insert the card into the new N810, then return that tablet to update mode and flash this kit kernel.')
    return dict(state='rootfs_written',storage_target='sd',device=disk,rootfs_readback_verified=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit',type=Path,required=True);parser.add_argument('--disk',required=True)
    parser.add_argument('--usb-location',type=lambda s:int(s,0),required=True)
    parser.add_argument('--write',action='store_true');args=parser.parse_args()
    install(args.kit,args.disk,args.usb_location,args.write)
