#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build a fresh SD A/B kit and matching internal recovery from a staged root."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid
from ab_runtime import atomic, digest
from ab_stage import stage, recovery

MIB = 1024 * 1024


def image(root, path, size, label):
    with path.open('wb') as f: f.truncate(size * MIB)
    subprocess.run(['mkfs.ext4','-F','-d',str(root),'-L',label,'-U',str(uuid.uuid4()),
                    '-E','lazy_itable_init=0,lazy_journal_init=0',str(path)],check=True)
    subprocess.run(['e2fsck','-fn',str(path)],check=True)
    return {'bytes':path.stat().st_size,'sha256':digest(path)}


def build(root, kernel, output, sd_id, recovery_id, slot_mib=1536, recovery_kernel=None):
    if os.geteuid() or os.uname().sysname != 'Linux': raise ValueError('Build inside the pinned Linux container as root')
    if any(not re.fullmatch('[0-9a-f]{8}',v) for v in (sd_id,recovery_id)) or sd_id==recovery_id: raise ValueError('Distinct eight-digit disk IDs required')
    if not 1024 <= slot_mib <= 8191: raise ValueError('Slot size must be 1024–8191 MiB')
    root,kernel,output=map(Path,(root,kernel,output))
    report=json.loads((kernel/'BUILD.json').read_text())
    if not report.get('ab_boot') or report['root_device'] != 'PARTUUID='+recovery_id+'-01':
        raise ValueError('Kernel must accept slot arguments and default to this recovery disk')
    output.mkdir(mode=0o700,exist_ok=False)
    # Device nodes and Linux ownership must never be staged on a macOS bind mount.
    work=Path(tempfile.mkdtemp(prefix='n810-ab-',dir='/work'))
    recovery_root=work/'recovery';subprocess.run(['cp','-a',str(root),str(recovery_root)],check=True)
    c={'version':1,'sd_disk_id':sd_id,'recovery_disk_id':recovery_id,'data_schema':1}
    recovery_package=Path(recovery_kernel or '/build/recovery-kernel/package')
    rec_report=json.loads((recovery_package/'BUILD.json').read_text())
    if rec_report.get('ab_boot') or rec_report['root_device']!='PARTUUID='+recovery_id+'-01':
        raise ValueError('Internal recovery must have a fixed root command line')
    shutil.rmtree(recovery_root/'lib/modules')
    shutil.copytree(recovery_package/'root/lib/modules',recovery_root/'lib/modules',symlinks=True)
    recovery(recovery_root,c)
    (recovery_root/'etc/fstab').write_text('PARTUUID='+recovery_id+'-01 / ext4 defaults,noatime 0 1\n')
    subprocess.run(['chroot',str(recovery_root),'/usr/bin/ssh-keygen','-q','-t','ed25519','-N','','-f','/etc/ssh/ssh_host_ed25519_key'],check=True)
    recovery_pub=(recovery_root/'etc/ssh/ssh_host_ed25519_key.pub').read_text().strip()
    rec=image(recovery_root,output/'recovery.ext4',1536,'n810-recovery')
    seed=work/'data';seed.mkdir();stage(root,seed,kernel,c)
    # Avoid checkroot remounting the immutable root. Slot init already mounts its writable views.
    for base in (root,root/'usr/lib/n810-ab'):
        check=base/'etc/init.d/checkroot.sh'
        if check.exists():
            text=check.read_text();lines=text.splitlines(True)
            lines.insert(1,'case " $(cat /proc/cmdline) " in *" n810.slot="*) exit 0;; esac\n')
            check.write_text(''.join(lines))
    from stage_sd_installer import stage as stage_installer
    bootstrap_package=Path('/build/sd-installer-kernel/package')
    if json.loads((bootstrap_package/'BUILD.json').read_text())['root_device']!='PARTUUID='+sd_id+'-02':
        raise ValueError('Bootstrap kernel belongs to a different SD card kit')
    bootstrap=stage_installer(root,bootstrap_package)
    slot_pub=(seed/'etc/ssh/ssh_host_ed25519_key.pub').read_text().strip()
    (output/'recovery-known-hosts').write_text('169.254.81.1 '+recovery_pub+'\n')
    (output/'slot-known-hosts').write_text('169.254.81.1 '+slot_pub+'\n')
    slot=image(root,output/'slot.ext4',slot_mib,'n810-slot')
    data=image(seed,output/'data.ext4',256,'n810-data')
    control=work/'control';control.mkdir()
    atomic(control/'state.json',{'version':1,'active':'A','pending':None,'tries':0})
    ctrl=image(control,output/'control.ext4',32,'n810-boot')
    shutil.copy2(recovery_package/'zImage-omap2420-n810',output/'recovery-kernel.bin')
    shutil.copy2(kernel/'BUILD.json',output/'KERNEL-BUILD.json')
    manifest=dict(c,kind='n810-ab-kit',slot_mib=slot_mib,minimum_card_bytes=(1+32+2*slot_mib+256)*MIB,
        files={'control.ext4':ctrl,'slot.ext4':slot,'data.ext4':data,'recovery.ext4':rec,
               'recovery-kernel.bin':{'bytes':(output/'recovery-kernel.bin').stat().st_size,'sha256':digest(output/'recovery-kernel.bin')}},
        source_commit=os.environ.get('INSTALLER_SOURCE_COMMIT') or json.loads((root/'usr/local/share/pocket/INSTALL.json').read_text())['source_commit'],
        pocket_source_commit=json.loads((root/'usr/local/share/pocket/INSTALL.json').read_text())['source_commit'],
        installer_runtime_sha256=digest(Path(__file__).with_name('ab_runtime.py')),
        hardware_acceptance=False)
    shutil.copy2(bootstrap_package/'zImage-omap2420-n810',output/'sd-bootstrap-kernel.bin')
    manifest['files']['sd-bootstrap-kernel.bin']={'bytes':(output/'sd-bootstrap-kernel.bin').stat().st_size,'sha256':bootstrap['kernel_sha256']}
    atomic(output/'AB.json',manifest)
    atomic(output/'SD-BOOTSTRAP.json',dict(bootstrap,kind='n810-sd-bootstrap',sd_disk_id=sd_id,kit_sha256=digest(output/'AB.json')))
    atomic(output/'UPDATE.json',dict(slot,data_schema=1))
    shutil.rmtree(work)
    # The output is private because its data seed includes the supplied setup choices.
    from build_internal_image import restore_owner
    restore_owner(output)
    print(json.dumps({'state':'ab_kit_built','output':str(output),'device_action':False}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','kernel','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--sd-id',required=True);p.add_argument('--recovery-id',required=True)
    p.add_argument('--slot-mib',type=int,default=1536)
    a=p.parse_args();build(a.root,a.kernel,a.output,a.sd_id,a.recovery_id,a.slot_mib)
