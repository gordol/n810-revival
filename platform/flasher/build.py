#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build pinned upstream 0xFFFF for the local host or an ARM cross-toolchain."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

HERE=Path(__file__).resolve().parent


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def extract(archive,destination):
    with tarfile.open(archive) as source:
        for entry in source:
            parts=Path(entry.name).parts
            if not parts or entry.name.startswith('/') or '..' in parts or not (entry.isfile() or entry.isdir()):
                raise ValueError('Unexpected upstream archive member')
            target=destination.joinpath(*parts[1:])
            if entry.isdir():target.mkdir(parents=True,exist_ok=True)
            else:
                target.parent.mkdir(parents=True,exist_ok=True)
                with source.extractfile(entry) as incoming,target.open('wb') as output:shutil.copyfileobj(incoming,output)
                target.chmod(entry.mode&0o777)


def build(output,archive=None,cc='cc',usb_flags=None,target='native'):
    lock=json.loads((HERE/'source.lock.json').read_text())
    mac=platform.system()=='Darwin' and target=='native'
    compiler=shlex.split(cc)
    if not compiler or not shutil.which(compiler[0]):raise ValueError('Install a C compiler or set FLASHER_CC')
    if usb_flags is None:
        if not shutil.which('pkg-config'):raise ValueError('Install pkg-config and libusb development files')
        usb_flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','libusb'],text=True))
    else:usb_flags=shlex.split(usb_flags)
    identity=dict(source_revision=lock['revision'],source_sha256=lock['sha256'],target=target,
                  compiler=compiler,compiler_version=subprocess.check_output([*compiler,'--version'],text=True).splitlines()[0],
                  usb_flags=usb_flags,usb_only=True,usb_host_patch_sha256=digest(HERE/'usb-host.patch'),nolo_only=mac,patch_sha256=digest(HERE/'macos-nolo.patch') if mac else None)
    stamp=output/'BUILD.json';binary=output/'0xFFFF'
    if stamp.exists():
        old=json.loads(stamp.read_text())
        if old.get('identity')==identity and binary.is_file() and old.get('binary_sha256')==digest(binary):
            return dict(old,state='cached',binary=str(binary))
        raise ValueError('Build output already exists with different inputs; choose a new FLASHER_OUTPUT')
    if output.exists():raise ValueError('Use a new output directory')
    output.parent.mkdir(parents=True,exist_ok=True)
    final=output
    with tempfile.TemporaryDirectory(prefix='.flasher-build-',dir=output.parent) as folder:
        output=Path(folder);stamp=output/'BUILD.json';binary=output/'0xFFFF'
        cached=output/'source.tar.gz'
        if archive:shutil.copyfile(archive,cached)
        else:
            with urllib.request.urlopen(lock['url'],timeout=60) as source,cached.open('wb') as target_file:
                shutil.copyfileobj(source,target_file)
        if digest(cached)!=lock['sha256']:raise ValueError('Upstream flasher checksum mismatch')
        source=output/'source';source.mkdir();extract(cached,source)
        subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(HERE/'usb-host.patch')],cwd=source,check=True)
        if mac:subprocess.run(['patch','--batch','--fuzz=0','-p1','-i',str(HERE/'macos-nolo.patch')],cwd=source,check=True)
        includes=[flag for flag in usb_flags if flag.startswith(('-I','-D'))]
        libraries=[flag for flag in usb_flags if flag not in includes]
        version=lock['version']+('-pocket-usb-nolo' if mac else '-pocket-usb')
        cpp=['-DPOCKET_USB_ONLY','-D_POSIX_C_SOURCE=200809L','-D_FILE_OFFSET_BITS=64','-DVERSION=\\"'+version+'\\"','-DBUILD_DATE=\\"pinned\\"',*includes]
        if mac:cpp+=['-D_DARWIN_C_SOURCE','-DPOCKET_NOLO_ONLY']
        subprocess.run(['make','-C',str(source/'src'),'0xFFFF','CROSS_CC='+shlex.join(compiler),
                        'CPPFLAGS='+' '.join(cpp),'LIBS='+' '.join(libraries+['-ldl'])],check=True)
        shutil.copy2(source/'src/0xFFFF',binary);binary.chmod(0o755)
        for name in ('usb-host.patch','macos-nolo.patch','source.lock.json'):
            shutil.copyfile(HERE/name,output/name)
        for name in ('COPYING','LICENSE'):
            if (source/name).is_file():shutil.copy2(source/name,output/'COPYING');break
        if target=='armel':
            header=binary.read_bytes()[:20]
            if header[:5]!=b'\x7fELF\x01' or header[18:20]!=b'\x28\x00':raise ValueError('Cross compiler did not produce ARM ELF32')
        else:subprocess.run([str(binary),'-h'],stdout=subprocess.DEVNULL,check=True)
        record=dict(identity=identity,binary_sha256=digest(binary),license=lock['license'],device_action=False)
        stamp.write_text(json.dumps(record,indent=2)+'\n')
        if final.exists():raise ValueError('Build destination appeared during compilation')
        output.rename(final)
        return dict(record,state='built',binary=str(final/'0xFFFF'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--archive',type=Path)
    p.add_argument('--cc',default=os.environ.get('FLASHER_CC','cc'));p.add_argument('--usb-flags',default=os.environ.get('FLASHER_USB_FLAGS') or None)
    p.add_argument('--target',choices=('native','armel'),default='native')
    a=p.parse_args();print(json.dumps(build(a.output.resolve(),a.archive,a.cc,a.usb_flags,a.target)))

if __name__=='__main__':main()
