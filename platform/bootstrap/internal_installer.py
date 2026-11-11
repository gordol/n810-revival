#!/usr/bin/env python3
"""Install a verified Pocket root to an N810 internal MMC from its RAM installer."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

INVENTORY = r'''set -eu
 test -f /etc/pocket-installer
 grep -qi 'N810' /proc/device-tree/model
 for disk in /sys/block/mmcblk*; do
  test -f "$disk/device/type" || continue
  printf '%s %s %s %s\n' "${disk##*/}" "$(cat "$disk/device/type")" "$(cat "$disk/size")" "$(cat "$disk/device/cid")"
 done
'''


def internal_target(text, image_bytes):
    if type(image_bytes) is not int or image_bytes<=0:raise ValueError('Invalid root image size')
    rows=[]
    for line in text.splitlines():
        fields=line.split()
        if len(fields)!=4:raise ValueError('Invalid installer disk inventory')
        name,kind,sectors,cid=fields
        if not re.fullmatch(r'mmcblk[0-9]+',name) or not re.fullmatch(r'[0-9a-fA-F]{32}',cid):
            raise ValueError('Invalid MMC identity')
        if not sectors.isdecimal():raise ValueError('Invalid MMC capacity')
        if kind=='MMC':rows.append(dict(device='/dev/'+name,cid=cid,sectors=int(sectors)))
    if len(rows)!=1:raise ValueError('Expected exactly one internal MMC; no storage changed')
    target=rows[0]
    if not 1024**3 <= target['sectors']*512 <= 4*1024**3:
        raise ValueError('Unexpected N810 internal storage capacity')
    if image_bytes > (target['sectors']-2048)*512:
        raise ValueError('Root filesystem does not fit internal storage')
    return target


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


class Installer:
    def __init__(self, kit, host, key=None):
        self.kit=Path(kit).resolve()
        if not re.fullmatch(r'[a-zA-Z0-9.:_-]+',host):raise ValueError('Invalid installer host')
        self.ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes',
                  '-o','UserKnownHostsFile='+str(self.kit/'installer-known-hosts')]
        if key:self.ssh+=['-i',str(key)]
        self.ssh+=['root@'+host]
    def remote(self, command, **kwargs):
        return subprocess.run([*self.ssh,command],check=True,**kwargs)
    def inspect(self):
        manifest=json.loads((self.kit/'INTERNAL.json').read_text())
        if manifest.get('kind')!='n810-internal':raise ValueError('Not an internal-install kit')
        size=manifest.get('root_bytes');expected=manifest.get('root_sha256')
        if type(size) is not int or not 0<size<=1900*1024**2:raise ValueError('Invalid root image size')
        if not isinstance(expected,str) or not re.fullmatch(r'[0-9a-f]{64}',expected):raise ValueError('Invalid root checksum')
        root=self.kit/'root.ext4';compressed=self.kit/'root.ext4.gz'
        if root.is_symlink() or compressed.is_symlink():raise ValueError('Installer images must be regular kit files')
        if compressed.exists() and digest(compressed)!=manifest.get('compressed_root_sha256'):
            raise ValueError('Compressed root checksum mismatch')
        if root.exists():
            if root.stat().st_size!=size or digest(root)!=expected:raise ValueError('Internal root image checksum mismatch')
        elif compressed.exists():
            value=hashlib.sha256();count=0
            with gzip.open(compressed,'rb') as source:
                while block:=source.read(1024*1024):
                    count+=len(block)
                    if count>size:raise ValueError('Expanded root exceeds declared size')
                    value.update(block)
            if count!=size or value.hexdigest()!=expected:raise ValueError('Expanded root checksum mismatch')
        else:raise ValueError('Missing internal root image')
        kernel=self.kit/'kernel.bin'
        if kernel.is_symlink() or kernel.stat().st_size>2097152 or digest(kernel)!=manifest.get('kernel_sha256'):
            raise ValueError('Internal boot kernel checksum or size mismatch')
        text=self.remote(INVENTORY,stdout=subprocess.PIPE,text=True).stdout
        return manifest,internal_target(text,size)
    def install(self):
        manifest,target=self.inspect()
        if manifest.get('desktop_ready') is not True:raise ValueError('Kit lacks installed Pocket desktop; refusing incomplete installation')
        disk_id=manifest['disk_id']
        if not re.fullmatch(r'[0-9a-f]{8}',disk_id):raise ValueError('Invalid partition identity')
        device=target['device'];name=device[5:];cid=target['cid']
        # Recheck the physical identity and mounted state immediately before erase.
        guard=f'''set -eu
 test -f /etc/pocket-installer
 test "$(cat /sys/block/{name}/device/cid)" = {shlex.quote(cid)}
 test "$(cat /sys/block/{name}/device/type)" = MMC
 if grep -q '^/dev/{name}' /proc/mounts; then echo 'Internal disk is mounted' >&2; exit 1; fi
'''
        partition=f'label: dos\nlabel-id: 0x{disk_id}\nunit: sectors\n\nstart=2048, type=83\n'
        self.remote(guard+'sfdisk --wipe always '+device,input=partition.encode())
        compressed=self.kit/'root.ext4.gz'
        image=compressed if compressed.exists() else self.kit/'root.ext4'
        command=('set -o pipefail; gzip -dc | ' if compressed.exists() else '')+'dd of='+device+'p1 bs=1048576 conv=fsync'
        with image.open('rb') as source:
            self.remote(guard+command,stdin=source)
        written=self.remote(guard+f"head -c {manifest['root_bytes']} {device}p1 | sha256sum",stdout=subprocess.PIPE,text=True).stdout.split()[0]
        if written!=manifest['root_sha256']:raise ValueError('Internal root readback checksum mismatch')
        self.remote(guard+f'e2fsck -fy {device}p1 || test $? -eq 1; resize2fs {device}p1; sync')
        return dict(target,rootfs_written=True,kernel_flashing_pending=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('kit',type=Path);p.add_argument('--host',default='192.168.11.1')
    p.add_argument('--key',type=Path);p.add_argument('--install',action='store_true',help='Erase internal MMC and install the verified complete root')
    a=p.parse_args();installer=Installer(a.kit,a.host,a.key)
    if a.install:print(json.dumps(installer.install()))
    else:print(json.dumps(installer.inspect()[1]))

if __name__=='__main__':main()
