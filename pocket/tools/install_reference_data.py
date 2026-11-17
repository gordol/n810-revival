#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate and install prepared map/LOS data without raw downloads or user state."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def relative(name):
    p=Path(name)
    if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('Invalid data path')
    return p


def inventory(source, maps=None):
    source=Path(source);files={}
    def add(name,path,expected=None):
        path=Path(path)
        if not path.is_file() or path.is_symlink():raise ValueError('Missing regular data file: '+str(path))
        actual=digest(path)
        if expected and actual!=expected:raise ValueError('Data checksum differs: '+str(path))
        files[str(relative(name))]=(path,dict(size=path.stat().st_size,sha256=actual))
    def tree(name):
        root=source/name
        if root.is_dir():
            for path in sorted(root.rglob('*')):
                if path.is_file():add(str(path.relative_to(source)),path)
    for name in ('geography','hydrography','repeaters'):tree(name)
    for name in ('map-geography.json.gz','shoreline-puget.json.gz'):
        if (source/name).is_file():add(name,source/name)
    catalogue=json.loads((source/'elevation.json').read_text())
    if catalogue.get('version')!=1 or not catalogue.get('packs'):raise ValueError('Selected elevation catalogue required')
    add('elevation.json',source/'elevation.json')
    for name in catalogue['packs']:
        index=source/relative(name)
        metadata=json.loads(index.read_text())
        indices=[index]+[index.parent/relative(row['index']) for row in metadata.get('overviews',())]
        for item in indices:
            add(str(item.relative_to(source)),item)
            data=json.loads(item.read_text())
            if data.get('units')!='meters' or data.get('tile_size')!=256:raise ValueError('Unsupported elevation index')
            for row in data['tiles'].values():
                path=item.parent/relative(row['file'])
                add(str(path.relative_to(source)),path,row['sha256'])
    maps=Path(maps) if maps else source/'maps'
    if not (maps/'walk-layers.n8w').is_file():raise ValueError('Prepared map views required (--maps or SOURCE/maps)')
    for path in sorted(maps.iterdir()):
        if path.is_file() and path.name.endswith(('.n8w','.n8t','.json','.gz','.md')):add('maps/'+path.name,path)
    # Check indexed geography too; a copied manifest alone is not usable data.
    for name in ('geography','hydrography'):
        index=source/name/'index.json'
        if not index.is_file():raise ValueError('Missing '+name+' index')
        for row in json.loads(index.read_text()).get('tiles',{}).values():
            path=index.parent/relative(row['file'])
            add(str(path.relative_to(source)),path,row['sha256'])
    return files


def manifest(files):
    return dict(version=1,files={n:row for n,(_,row) in sorted(files.items())})


def verify(target):
    target=Path(target);record=json.loads((target/'REFERENCE.json').read_text())
    if record.get('version')!=1:raise ValueError('Unsupported reference manifest')
    for name,row in record['files'].items():
        p=target/relative(name)
        if p.is_symlink() or p.stat().st_size!=row['size'] or digest(p)!=row['sha256']:raise ValueError('Reference data differs: '+name)
    return dict(files=len(record['files']),bytes=sum(r['size'] for r in record['files'].values()))


def install(files,target):
    target=Path(target);target.mkdir(parents=True,exist_ok=True)
    for name,(source,row) in files.items():
        p=target/name
        if not p.resolve().is_relative_to(target.resolve()):raise ValueError('Reference destination escapes target')
        p.parent.mkdir(parents=True,exist_ok=True)
        if p.is_symlink():raise ValueError('Refusing symlink destination: '+name)
        if p.is_file() and p.stat().st_size==row['size'] and digest(p)==row['sha256']:continue
        temporary=p.with_name(p.name+'.installing')
        with source.open('rb') as src,temporary.open('wb') as dst:shutil.copyfileobj(src,dst)
        temporary.chmod(0o644);temporary.replace(p)
    (target/'REFERENCE.json').write_text(json.dumps(manifest(files),sort_keys=True)+'\n')
    return verify(target)


def stream(files,output):
    with tarfile.open(fileobj=output,mode='w|') as tar:
        for name,(path,row) in sorted(files.items()):
            entry=tarfile.TarInfo(name);entry.size=row['size'];entry.mode=0o644
            with path.open('rb') as src:tar.addfile(entry,src)
        raw=(json.dumps(manifest(files),sort_keys=True)+'\n').encode()
        entry=tarfile.TarInfo('REFERENCE.json');entry.size=len(raw);entry.mode=0o644;tar.addfile(entry,io.BytesIO(raw))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path);p.add_argument('--maps',type=Path)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--target',type=Path);group.add_argument('--verify',type=Path);group.add_argument('--stream',action='store_true');group.add_argument('--plan',action='store_true')
    a=p.parse_args()
    if a.verify:print(json.dumps(verify(a.verify)))
    else:
        if not a.source:p.error('--source is required')
        files=inventory(a.source,a.maps)
        if a.stream:stream(files,sys.stdout.buffer)
        elif a.target:print(json.dumps(install(files,a.target)))
        else:print(json.dumps(dict(files=len(files),bytes=sum(r['size'] for _,r in files.values()))))
