#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Install internal recovery from the SD bootstrap, then flash its matching kernel."""
import argparse
import hashlib
import gzip
import json
from pathlib import Path
import re
import shlex
import struct
import socket
import sys
import subprocess
from ab_media import verify,MIB
from ab_runtime import atomic,digest
from internal_installer import identify_device,_run_flasher,configure_installer_network


def ram(kit):
    root=kit/'ram-installer';report=json.loads((root/'BUILD.json').read_text())
    if report.get('kind')!='n810-ram-installer':raise ValueError('Missing verified RAM installer')
    for name,h in report['files'].items():
        if Path(name).name!=name or digest(root/name)!=h:raise ValueError('RAM installer checksum mismatch')
    return root



def sd_bootstrap(kit):
    """Verify a supplementary bootstrap without invalidating the SD write receipt."""
    manifest=json.loads((kit/'AB.json').read_text())
    report=json.loads((kit/'SD-BOOTSTRAP.json').read_text())
    receipt=json.loads((kit/'SD-INSTALL.json').read_text())
    if (report.get('kind')!='n810-sd-bootstrap' or report.get('kit_sha256')!=digest(kit/'AB.json')
            or receipt.get('kit_sha256')!=report['kit_sha256'] or not receipt.get('readback_verified')
            or report.get('sd_disk_id')!=manifest['sd_disk_id']):
        raise ValueError('SD bootstrap does not match the verified card kit')
    kernel=kit/'sd-bootstrap-kernel.bin'
    if kernel.is_symlink() or kernel.stat().st_size>2097152 or digest(kernel)!=report['kernel_sha256']:
        raise ValueError('SD bootstrap kernel checksum or NOLO size check failed')
    return kernel


def ssh(kit,key,host):
    known = kit/'slot-known-hosts' if (kit/'SD-BOOT.json').exists() else ram(kit)/'installer-known-hosts'
    bind=['-b','169.254.81.2'] if sys.platform in ('darwin','linux') and host=='169.254.81.1' else []
    return ['ssh',*bind,'-i',str(key),'-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
            '-o','UserKnownHostsFile='+str(known),'root@'+host]


def environment_guard(kit):
    if (kit/'SD-BOOT.json').exists():
        m=json.loads((kit/'AB.json').read_text())
        disk=m['sd_disk_id']
        if not re.fullmatch('[0-9a-f]{8}',disk):raise ValueError('Invalid SD identity')
        return ("test -f /run/n810-sd-installer\n"
                "case $(uname -r) in *-n810-sd-installer) :;; *) exit 1;; esac\n"
                "test \"$(findmnt -n -o PARTUUID /)\" = "+disk+"-02\n"
                "findmnt -n -o OPTIONS / | tr ',' '\\n' | grep -qx ro\n")
    return ('test -f /etc/pocket-installer\n'
            'test "$(findmnt -n -o FSTYPE / 2>/dev/null || awk \'$2=="/" {print $3;exit}\' /proc/mounts)" != ext4\n')


def probe(kit,key,host):
    command="set -eu\n"+environment_guard(kit)+"""
 for d in /sys/block/mmcblk*; do
  test "$(cat "$d/device/type")" = MMC || continue
  echo "$(basename "$d") $(cat "$d/size") $(cat "$d/device/cid")"
 done
"""
    out=subprocess.check_output(ssh(kit,key,host)+[command],text=True).splitlines()
    if len(out)!=1:raise ValueError('Expected exactly one internal MMC in the RAM installer')
    node,sectors,cid=out[0].split()
    if not re.fullmatch(r'mmcblk[0-9]+',node) or int(sectors)*512!=2013265920 or not re.fullmatch('[0-9a-f]{32}',cid):
        raise ValueError('Unexpected internal storage identity')
    return dict(node=node,sectors=int(sectors),cid=cid)


def write_recovery(kit,m,key,host,expected_cid,erase):
    identity=probe(kit,key,host)
    if identity['cid']!=expected_cid:raise ValueError('Internal MMC identity differs from selected tablet')
    if not erase:return dict(state='recovery_checked',identity=identity,device_action=False)
    record=json.loads((kit/('SD-BOOT.json' if (kit/'SD-BOOT.json').exists() else 'RAM-BOOT.json')).read_text())
    if record['kit_sha256']!=digest(kit/'AB.json'):raise ValueError('RAM boot belongs to another kit')
    node=identity['node'];sectors=identity['sectors']
    mbr=bytearray(MIB);struct.pack_into('<I',mbr,440,int(m['recovery_disk_id'],16))
    struct.pack_into('<B3sB3sII',mbr,446,0,b'\xfe\xff\xff',0x83,b'\xfe\xff\xff',2048,sectors-2048);mbr[510:512]=b'\x55\xaa'
    image=kit/'recovery.ext4';length=MIB+image.stat().st_size
    # Repeat all admission checks inside the same remote command that opens the disk.
    script='set -eu\n'+environment_guard(kit)+'''

 test "$(cat /sys/block/NODE/device/type)" = MMC
 test "$(cat /sys/block/NODE/device/cid)" = CID
 test "$(cat /sys/block/NODE/size)" = SECTORS
 for path in /sys/block/NODE /sys/block/NODE/NODE*; do
  test -f "$path/dev" || continue
  number=$(cat "$path/dev")
  ! awk -v number="$number" '$3==number {found=1} END {exit !found}' /proc/self/mountinfo
 done
 ! grep -q '/dev/NODE' /proc/mounts
 ! grep -q '/dev/NODE' /proc/swaps
 gzip -dc | dd of=/dev/NODE bs=1048576
 sync
 head -c LENGTH /dev/NODE | sha256sum
'''
    for a,b in [('NODE',node),('CID',expected_cid),('SECTORS',str(sectors)),('LENGTH',str(length))]:script=script.replace(a,b)
    p=subprocess.Popen(ssh(kit,key,host)+[script],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=kit.joinpath('recovery-write.log').open('wb'))
    h=hashlib.sha256();h.update(mbr)
    try:
        with gzip.GzipFile(fileobj=p.stdin, mode='wb', compresslevel=1) as transport:
            transport.write(mbr)
            with image.open('rb') as f:
                for block in iter(lambda:f.read(4*MIB),b''):
                    transport.write(block);h.update(block)
        p.stdin.close();result=p.stdout.read().decode();code=p.wait()
    except BaseException:
        p.terminate();p.wait();raise
    if code or result.split()[0]!=h.hexdigest():raise ValueError('Recovery readback failed; kernel flash blocked')
    receipt=dict(record,state='recovery_written',identity=identity,readback_verified=True)
    atomic(kit/'RECOVERY-INSTALL.json',receipt)
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['boot-ram','boot-sd','inspect','write-recovery','flash-recovery'])
    p.add_argument('--kit',type=Path,required=True);p.add_argument('--flasher',type=Path)
    p.add_argument('--key',type=Path);p.add_argument('--host',default='169.254.81.1')
    p.add_argument('--expected-cid');p.add_argument('--erase',action='store_true')
    a=p.parse_args();kit,m=verify(a.kit)
    if a.action=='boot-sd':
        if not a.flasher:p.error('--flasher required')
        kernel=sd_bootstrap(kit)
        identity=identify_device(a.flasher)
        prior=kit/'RAM-BOOT.json'
        if prior.exists():
            previous=json.loads(prior.read_text())
            for field in ('usb_location','usb_port'):
                if field in previous and previous[field]!=identity.get(field):raise ValueError('Target USB port changed')
        interfaces={name for _,name in socket.if_nameindex()}
        _run_flasher(a.flasher,['-m','kernel:'+str(kernel),'-l','-b'],180,kit/'USB-OPERATIONS.log')
        result=dict(identity,state='sd_boot_requested',kit_sha256=digest(kit/'AB.json'),kernel_sha256=digest(kernel),kernel_flashed=False)
        atomic(kit/'SD-BOOT.json',result)
        result['host_interface']=configure_installer_network(interfaces,usb_port=identity.get('usb_port'))
    elif a.action=='boot-ram':
        if not a.flasher:p.error('--flasher required')
        identity=identify_device(a.flasher);r=ram(kit)
        atomic(kit/'RAM-BOOT.json',dict(identity,kit_sha256=digest(kit/'AB.json')))
        _run_flasher(a.flasher,['-m','kernel:'+str(r/'kernel.bin'),'-m','initfs:'+str(r/'initramfs.cpio.xz'),'-l','-b'],180,kit/'USB-OPERATIONS.log')
        result={'state':'ram_installer_booted','device_storage_changed':False}
    elif a.action=='inspect':result=probe(kit,a.key,a.host)
    elif a.action=='write-recovery':result=write_recovery(kit,m,a.key,a.host,a.expected_cid,a.erase)
    else:
        receipt=json.loads((kit/'RECOVERY-INSTALL.json').read_text())
        sd=json.loads((kit/'SD-INSTALL.json').read_text())
        if receipt.get('state')!='recovery_written':raise ValueError('Recovery kernel flash was already attempted; inspect its receipt')
        if not receipt.get('readback_verified') or not sd.get('readback_verified') or any(v['kit_sha256']!=digest(kit/'AB.json') for v in (receipt,sd)):
            raise ValueError('Both SD and recovery must have verified write receipts')
        identity=identify_device(a.flasher)
        for field in ('usb_location','usb_port'):
            if field in receipt and receipt[field]!=identity.get(field):raise ValueError('Target USB port changed')
        try:
            _run_flasher(a.flasher,['-m','kernel:'+str(kit/'recovery-kernel.bin'),'-f','-r'],180,kit/'USB-OPERATIONS.log')
        except RuntimeError as error:
            output=str(error)
            if (re.search(r'Flashing image\.\.\.\s+Done\s+Rebooting device\.\.\.',output) and
                    re.findall(r'Error:[^\r\n]*',output)==['Error: NOLO_REBOOT failed']):
                atomic(kit/'RECOVERY-INSTALL.json',dict(receipt,state='kernel_flashed_reboot_unconfirmed'))
                raise RuntimeError('Kernel flash completed; reboot acknowledgement failed. Verify live boot; do not flash again.') from error
            raise
        result=dict(receipt,state='recovery_kernel_flashed');atomic(kit/'RECOVERY-INSTALL.json',result)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
