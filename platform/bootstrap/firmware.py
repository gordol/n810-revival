#!/usr/bin/env python3
"""Acquire pinned radio firmware from public sources or an owner's backup."""
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import urllib.request

HERE=Path(__file__).resolve().parent
LIMIT=2*1024*1024
PATHS={
 '3826.arm':['usr/lib/hotplug/firmware/3826.arm','lib/firmware/3826.arm','usr/lib/firmware/3826.arm','3826.arm'],
 'bc4fw.bin':['usr/lib/hotplug/firmware/bc4fw.bin','lib/firmware/nokia/bc4fw.bin','usr/lib/firmware/nokia/bc4fw.bin','bc4fw.bin'],
}

def digest(data):return hashlib.sha256(data).hexdigest()

def validate(data,record):
 if not data or len(data)>LIMIT or digest(data)!=record['sha256']:
  raise ValueError('Firmware does not match the pinned complete image')
 if 'bytes' in record and len(data)!=record['bytes']:raise ValueError('Firmware length mismatch')
 return data

def bounded_file(path,root):
 resolved=path.resolve()
 if not resolved.is_relative_to(root.resolve()):raise ValueError('Backup symlink escapes its directory')
 if not resolved.is_file() or resolved.stat().st_size>LIMIT:raise ValueError('Invalid firmware file')
 return resolved.read_bytes()

def reader():
 spec=importlib.util.spec_from_file_location('n810_jffs',HERE.parent/'scripts/n810-jffs2-extract.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def from_jffs(image,names):
 if image.is_symlink() or not 0<image.stat().st_size<=256*1024*1024:raise ValueError('Use a data-only JFFS2 partition up to 256 MiB')
 jffs=reader();dirents,inodes,_,_,_=jffs.scan(image)
 found={}
 for name in names:
  for path in PATHS[name]:
   ino=1
   for index,part in enumerate(path.split('/')):
    entry=dirents.get((ino,part.encode()))
    expected=8 if index==len(path.split('/'))-1 else 4
    if entry is None or entry[1]==0 or entry[2]!=expected:break
    ino=entry[1]
   else:
    nodes=inodes.get(ino,[])
    if not nodes:raise ValueError('Firmware inode has no CRC-valid data')
    size=max(nodes,key=lambda n:(n['version'],n['physical']))['isize']
    if not 0<size<=LIMIT:raise ValueError('Firmware inode size is invalid')
    coverage=bytearray(size)
    for n in nodes:
     if n['dsize']>LIMIT:raise ValueError('Firmware fragment is too large')
     start=min(n['offset'],size);end=min(n['offset']+n['dsize'],size)
     coverage[start:end]=b'\1'*(end-start)
    if not all(coverage):raise ValueError('Firmware has missing or corrupt fragments')
    data=jffs.reconstruct(nodes)
    if name in found and found[name]!=data:raise ValueError('Conflicting firmware records')
    found[name]=data
 return found

def backup_files(backup):
 if backup is None:return {}
 if not backup.is_dir() or backup.is_symlink():raise ValueError('MAEMO_BACKUP must be an ordinary directory')
 found={}
 for prefix in ('','initfs','rootfs'):
  for name,paths in PATHS.items():
   for suffix in paths:
    path=backup/prefix/suffix
    if path.exists() or path.is_symlink():
     data=bounded_file(path,backup)
     if name in found and found[name]!=data:raise ValueError('Conflicting firmware copies in backup')
     found[name]=data
 for name in ('initfs.jffs2','rootfs.jffs2'):
  path=backup/name
  if path.exists():
   for key,data in from_jffs(path,PATHS).items():
    if key in found and found[key]!=data:raise ValueError('Conflicting firmware copies in backup')
    found[key]=data
 return found

def acquire(output,cache,backup=None,offline=False,records=None):
 records=records or json.loads((HERE/'firmware.lock.json').read_text())['files']
 owner=backup_files(backup)
 output.mkdir(parents=True,exist_ok=True);cache.mkdir(parents=True,exist_ok=True)
 report={}
 for name,record in records.items():
  source='owner-backup'
  if name in owner:
   data=validate(owner[name],record)
  else:
   cached=cache/record['sha256']
   if cached.exists():data=validate(bounded_file(cached,cache),record);source='verified-cache'
   elif offline:raise ValueError('Backup/cache lacks required firmware: '+name)
   else:
    url=record['url']
    if not url.startswith('https://'):raise ValueError('Firmware downloads require HTTPS')
    with urllib.request.urlopen(url,timeout=60) as response:
     if not response.geturl().startswith('https://'):raise ValueError('Insecure firmware redirect')
     data=validate(response.read(LIMIT+1),record)
    with tempfile.NamedTemporaryFile(dir=cache,delete=False) as f:temporary=Path(f.name);f.write(data)
    temporary.replace(cached);source='download'
   if offline:source='verified-cache'
  (output/name).write_bytes(data)
  report[name]=dict(sha256=digest(data),bytes=len(data),acquired_from=source,upstream=record['url'],license_status=record.get('license_status','owner-supplied test fixture'))
 (output/'FIRMWARE.json').write_text(json.dumps(report,indent=2)+'\n')
 return report

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--backup',type=Path);p.add_argument('--offline',action='store_true');a=p.parse_args()
 try:acquire(a.output,a.cache,a.backup,a.offline)
 except (OSError,ValueError) as e:p.exit(1,str(e)+'\n')
