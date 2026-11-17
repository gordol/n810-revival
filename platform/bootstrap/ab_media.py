#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check or explicitly erase a removable card for an N810 A/B installation."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import struct
import subprocess
import sys
import hashlib
from ab_runtime import atomic,digest
MIB=1024*1024


def layout(m, capacity):
    sizes=[32*MIB,m['slot_mib']*MIB,m['slot_mib']*MIB]
    starts=[MIB]
    for size in sizes: starts.append(starts[-1]+size)
    if capacity-starts[-1] < m['files']['data.ext4']['bytes'] or capacity%512 or capacity//512 > 0xffffffff:
        raise ValueError('Card does not fit the A/B layout')
    sizes.append(capacity-starts[-1])
    table=bytearray(MIB);struct.pack_into('<I',table,440,int(m['sd_disk_id'],16))
    for i,(start,size) in enumerate(zip(starts,sizes)):
        struct.pack_into('<B3sB3sII',table,446+i*16,0,b'\xfe\xff\xff',0x83,b'\xfe\xff\xff',start//512,size//512)
    table[510:512]=b'\x55\xaa'
    return bytes(table), list(zip(starts,('control.ext4','slot.ext4','slot.ext4','data.ext4')))


def verify(kit):
    kit=Path(kit).resolve();m=json.loads((kit/'AB.json').read_text())
    if m.get('kind')!='n810-ab-kit' or m.get('data_schema')!=1:raise ValueError('Unsupported kit')
    expected={'control.ext4','slot.ext4','data.ext4','recovery.ext4','recovery-kernel.bin'}
    if set(m['files'])!=expected:raise ValueError('Unexpected image list')
    for name,v in m['files'].items():
        if (kit/name).is_symlink() or (kit/name).stat().st_size!=v['bytes'] or digest(kit/name)!=v['sha256']:
            raise ValueError('Kit checksum mismatch: '+name)
    return kit,m


def inspect(disk):
    if sys.platform=='darwin':
        from write_sd_card import validate_card,fingerprint
        info=plistlib.loads(subprocess.check_output(['diskutil','info','-plist',disk]))
        capacity=validate_card(info,disk,0)
        return capacity,fingerprint(info)
    if sys.platform=='linux':
        from linux_storage import inspect as linux_inspect
        info=linux_inspect(disk)
        if info['partition'] or info['readonly'] or info['busy'] or info['sector_size']!=512 or not info['removable']:
            raise ValueError('Choose an unmounted removable whole disk')
        return info['bytes'],info
    raise ValueError('Use native Linux or macOS for raw card writes')


def write(kit,disk,erase=False):
    kit,m=verify(kit);capacity,identity=inspect(disk);table,parts=layout(m,capacity)
    receipt=kit/'SD-INSTALL.json'
    if receipt.exists():raise ValueError('Kit already has an install receipt; preserve it')
    if not erase:return {'state':'card_checked','bytes':capacity,'identity':identity,'device_action':False}
    if os.geteuid():raise ValueError('Explicit erase requires root')
    if sys.platform=='darwin':subprocess.run(['diskutil','unmountDisk',disk],check=True)
    if inspect(disk)!=(capacity,identity):raise ValueError('Card identity changed')
    path='/dev/r'+disk[5:] if sys.platform=='darwin' else disk
    with open(path,'r+b',buffering=0) as dst:
        def transfer(offset,source,count):
            dst.seek(offset)
            remaining=count;expected=hashlib.sha256()
            while remaining:
                block=source.read(min(4*MIB,remaining))
                if not block:raise ValueError('Short image')
                view=memoryview(block)
                while view:
                    n=dst.write(view)
                    if not n:raise OSError('Short card write')
                    view=view[n:]
                expected.update(block);remaining-=len(block)
            os.fsync(dst.fileno());dst.seek(offset);actual=hashlib.sha256();remaining=count
            while remaining:
                block=dst.read(min(4*MIB,remaining))
                if not block:raise ValueError('Short card readback')
                actual.update(block);remaining-=len(block)
            if actual.digest()!=expected.digest():raise ValueError('Card readback mismatch')
        import io
        transfer(0,io.BytesIO(table),len(table))
        for offset,name in parts:
            print('Writing and verifying '+name,flush=True)
            with (kit/name).open('rb') as source:transfer(offset,source,m['files'][name]['bytes'])
    result={'state':'sd_ab_written','identity':identity,'sd_disk_id':m['sd_disk_id'],
            'kit_sha256':digest(kit/'AB.json'),'readback_verified':True}
    atomic(receipt,result)
    if os.environ.get('SUDO_UID'):os.chown(receipt,int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
    if sys.platform=='darwin':subprocess.run(['diskutil','eject',disk],check=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kit',type=Path,required=True)
    p.add_argument('--disk');p.add_argument('--erase',action='store_true');a=p.parse_args()
    print(json.dumps(write(a.kit,a.disk,a.erase) if a.disk else {'state':'kit_verified','source':verify(a.kit)[1]['source_commit']},indent=2))
