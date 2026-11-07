# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Local N810 installation-kit preparation. Never opens a device or runs an installer.

A reviewed manifest supplies the system image and matching boot inputs. Hashes
check that local bytes match that manifest; they do not authenticate its publisher.
Preparing a kit copies ordinary files into a new directory, not onto a tablet.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile

KINDS={'n810-system':('system-image','kernel','modules','boot-guide'),
       'pocket-update':('payload','installer','install-guide')}
MAX_MANIFEST=65536
MAX_FILES=64


def regular(path):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode):raise ValueError('Expected a regular local file: '+str(path))
    return info


def digest(path,progress=None,cancelled=None):
    regular(path);value=hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            if cancelled is not None and cancelled.is_set():raise InterruptedError('Preparation cancelled')
            block=stream.read(1024*1024)
            if not block:break
            value.update(block)
    if progress:progress('Verified '+path.name)
    return value.hexdigest()


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate manifest key: '+key)
        result[key]=value
    return result


def inspect(manifest,progress=None,cancelled=None):
    """Return a detached verified plan, or fail without changing any files."""
    manifest=Path(manifest).expanduser().absolute()
    info=regular(manifest)
    if info.st_size>MAX_MANIFEST:raise ValueError('Manifest exceeds 64 KiB')
    data=json.loads(manifest.read_text(),object_pairs_hook=unique_object)
    if not isinstance(data,dict) or data.get('version')!=1 or type(data.get('version')) is not int:raise ValueError('Expected installation manifest version 1')
    kind=data.get('kind');release=data.get('release')
    if kind not in KINDS:raise ValueError('Choose an n810-system or pocket-update manifest')
    if not isinstance(release,str) or not release.strip() or len(release)>100 or not release.isprintable():raise ValueError('Manifest needs a readable release name')
    files=data.get('files')
    if not isinstance(files,list) or not 1<=len(files)<=MAX_FILES:raise ValueError('Manifest needs 1–64 files')
    root=manifest.parent.resolve();seen=set();roles=set();verified=[]
    for row in files:
        if not isinstance(row,dict):raise ValueError('Invalid manifest file')
        name=row.get('path');role=row.get('role');size=row.get('bytes');sha=row.get('sha256')
        if not isinstance(name,str) or not name or '\\' in name or Path(name).is_absolute() or any(p in ('.','..') for p in name.split('/')):raise ValueError('File paths must stay inside the kit')
        if name in seen or name in ('INSTALLATION.json','SETUP-PLAN.json','README.txt'):raise ValueError('Duplicate or reserved kit file: '+name)
        if not isinstance(role,str) or not role or len(role)>64:raise ValueError('Every file needs a role')
        if role in roles:raise ValueError('Duplicate artifact role: '+role)
        if type(size) is not int or not 0<size<=8*1024**3:raise ValueError('Invalid artifact size: '+name)
        if not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):raise ValueError('Invalid SHA-256: '+name)
        path=root/name
        # Refuse symlinks at every level, including directories under the root.
        current=root
        for part in Path(name).parts:
            current=current/part
            if current.is_symlink():raise ValueError('Kit files cannot use symlinks: '+name)
        before=regular(path)
        if before.st_size!=size:raise ValueError('Artifact size mismatch: '+name)
        actual=digest(path,progress,cancelled)
        after=regular(path)
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('Artifact changed while checking: '+name)
        if actual!=sha:raise ValueError('Artifact checksum mismatch: '+name)
        seen.add(name);roles.add(role);verified.append(dict(path=name,role=role,bytes=size,sha256=sha))
    missing=set(KINDS[kind])-roles
    if missing:raise ValueError('Missing required artifacts: '+', '.join(sorted(missing)))
    if kind=='n810-system':
        kernel=data.get('kernel_release')
        if not isinstance(kernel,str) or not kernel or len(kernel)>100 or not kernel.isprintable():raise ValueError('System kit needs its matching kernel release')
    return dict(version=1,kind=kind,release=release,kernel_release=data.get('kernel_release'),
                manifest=str(manifest),manifest_sha256=digest(manifest),files=verified,
                total_bytes=sum(row['bytes'] for row in verified),state='files_verified',tablet_installed=False)


def prepare(manifest,destination,progress=None,cancelled=None):
    """Atomically publish a new local kit; keep existing paths untouched."""
    plan=inspect(manifest,progress,cancelled)
    destination=Path(destination).expanduser().absolute()
    destination=destination.parent.resolve()/destination.name
    if str(destination).startswith(('/dev/','/proc/','/sys/')):raise ValueError('Choose a new ordinary local folder, not a device path')
    if destination.exists() or destination.is_symlink():raise ValueError('Destination already exists; choose a new kit folder')
    parent=destination.parent
    if not parent.is_dir() or parent.is_symlink():raise ValueError('The destination parent folder must already exist')
    if shutil.disk_usage(parent).free<plan['total_bytes']+1024*1024:raise ValueError('Not enough free space for the local kit')
    stage=Path(tempfile.mkdtemp(prefix='.n810-setup-',dir=parent))
    root=Path(plan['manifest']).parent.resolve()
    try:
        for row in plan['files']:
            source=root/row['path'];target=stage/row['path'];target.parent.mkdir(parents=True,exist_ok=True)
            # Hash the bytes actually copied, detecting replacements after inspect.
            value=hashlib.sha256();regular(source)
            with source.open('rb') as incoming,target.open('xb') as outgoing:
                while True:
                    if cancelled is not None and cancelled.is_set():raise InterruptedError('Preparation cancelled')
                    block=incoming.read(1024*1024)
                    if not block:break
                    outgoing.write(block);value.update(block)
                outgoing.flush();os.fsync(outgoing.fileno())
            if target.stat().st_size!=row['bytes'] or value.hexdigest()!=row['sha256']:raise ValueError('Artifact changed during copy: '+row['path'])
            if progress:progress('Copied '+row['path'])
        description=dict(version=1,kind=plan['kind'],release=plan['release'],files=plan['files'])
        if plan['kernel_release']:description['kernel_release']=plan['kernel_release']
        (stage/'INSTALLATION.json').write_text(json.dumps(description,indent=2)+'\n')
        (stage/'SETUP-PLAN.json').write_text(json.dumps(dict(plan,manifest='INSTALLATION.json',state='kit_prepared'),indent=2)+'\n')
        guide=next(row['path'] for row in plan['files'] if row['role'] in ('boot-guide','install-guide'))
        (stage/'README.txt').write_text('N810 installation kit: '+plan['release']+'\n\nFiles verified and copied. The tablet is not installed.\nRead '+guide+' before taking any device action.\nNo partition, NAND, bootloader, radio, network identity or credentials were changed.\n')
        if cancelled is not None and cancelled.is_set():raise InterruptedError('Preparation cancelled')
        if destination.exists() or destination.is_symlink():raise ValueError('Destination appeared during preparation; retained')
        os.rename(stage,destination)
        return dict(plan,state='kit_prepared',destination=str(destination))
    finally:
        if stage.exists():shutil.rmtree(stage)


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    check=sub.add_parser('check');check.add_argument('manifest',type=Path)
    kit=sub.add_parser('prepare');kit.add_argument('manifest',type=Path);kit.add_argument('destination',type=Path)
    args=parser.parse_args(argv)
    try:result=inspect(args.manifest) if args.action=='check' else prepare(args.manifest,args.destination)
    except (OSError,ValueError) as error:parser.exit(1,str(error)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
