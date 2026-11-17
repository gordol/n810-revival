#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build a private A/B kit with optional interactive Wi-Fi and account setup."""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tarfile
from build_preflight import check
from setup_profile import validate


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--ssh-key',type=Path,required=True)
    p.add_argument('--configure',action='store_true');p.add_argument('--slot-mib',type=int,default=1536)
    a=p.parse_args();a.output=a.output.expanduser().absolute();a.ssh_key=a.ssh_key.expanduser().resolve(strict=True)
    check(a.output,a.slot_mib)
    if shutil.disk_usage(a.output.parent).free < (2*a.slot_mib+1536+1024)*1024**2:
        raise ValueError('Reserve at least 6 GiB output space for a default A/B kit')
    repo=Path(__file__).resolve().parents[2]
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=normal'],cwd=repo).strip():
        raise ValueError('Commit source changes before building an identified kit')
    profile={};password=None
    if a.configure:
        ssid=input('Wi-Fi network name (blank to set up later): ')
        if ssid:profile['wifi']={'ssid':ssid,'passphrase':getpass.getpass('Wi-Fi password: '),'country':input('Country code [US]: ').strip().upper() or 'US'}
        profile['startup']={name:input('Start '+label+' by default? [y/N]: ').strip().lower()=='y'
                            for name,label in [('receive','UV-PRO APRS reception'),('meshcore','MeshCore'),('reticulum','Reticulum')]}
        password=getpass.getpass('New nokia login password: ')
        if not password or password!=getpass.getpass('Repeat nokia password: '):raise ValueError('Passwords must match and be nonempty')
    profile=validate(profile)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    work=a.output.parent/(a.output.name+'-build');work.mkdir(mode=0o700,exist_ok=False)
    recovery_id=secrets.token_hex(4);sd_id=secrets.token_hex(4)
    if recovery_id==sd_id:raise ValueError('Retry disk identity generation')
    context=work/'context.tar'
    files=subprocess.check_output(['python3','tools/package-source.py','--list-context'],cwd=repo).split(b'\0')
    with tarfile.open(context,'w',format=tarfile.GNU_FORMAT) as archive:
        for raw in files:
            if raw:archive.add(repo/os.fsdecode(raw),arcname=os.fsdecode(raw),recursive=False)
    image='n810-ab-builder:'+commit[:12]
    with context.open('rb') as source,(work/'builder.log').open('wb') as log:
        subprocess.run(['docker','build','--progress=plain','--build-arg','DISK_ID='+recovery_id,'--build-arg','AB_BOOT=1',
                        '--build-arg','SOURCE_COMMIT='+commit,'-t',image,'-f','containers/internal-image.Dockerfile','-'],
                       stdin=source,stdout=log,stderr=subprocess.STDOUT,check=True,cwd=repo)
    context.unlink()
    command=['docker','run','--rm','-i','--mount','type=bind,src='+str(a.ssh_key)+',dst=/run/owner.pub,readonly',
             '--mount','type=bind,src='+str(a.output.parent)+',dst=/output',
             '--mount','type=volume,src=n810-internal-firmware,dst=/cache/firmware',
             '-e','SUDO_UID='+str(os.getuid()),'-e','SUDO_GID='+str(os.getgid()),image,
             'python3','platform/bootstrap/build_internal_sources.py','--output','/work/base-kit',
             '--ssh-key','/run/owner.pub','--firmware-cache','/cache/firmware','--size-mib',str(a.slot_mib),
             '--storage-target','sd','--ab-output','/output/'+a.output.name,'--ab-sd-id',sd_id,'--setup-stdin']
    private_input=json.dumps(profile)+'\n'
    if password is not None:command+=['--password-stdin'];private_input=password+'\n'+private_input
    with (work/'export.log').open('w') as log:
        subprocess.run(command,input=private_input,text=True,stdout=log,stderr=subprocess.STDOUT,check=True,cwd=repo)
    print('Built '+str(a.output)+'; logs: '+str(work))

if __name__=='__main__':main()
