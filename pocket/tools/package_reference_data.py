"""Package prepared offline reference snapshots, excluding user state and raw imports."""
import argparse,gzip,hashlib,json,tarfile,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SELECTED=('map-geography.json.gz','geography','hydrography','elevation-fine','uls.sqlite','shoreline-puget.json.gz','repeaters/repeaters.json')
def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()
def package(output):
    files={}
    for name in SELECTED:
        source=ROOT/'data'/name
        if not source.exists():continue
        if source.is_dir():
            files.update((str(p.relative_to(ROOT/'data')),p) for p in source.rglob('*') if p.is_file())
        else:files[name]=source
    for name in ('elevation-western-wa','elevation-lakewood'):
        source=ROOT/'shell/data'/name
        files.update((str(p.relative_to(ROOT/'shell/data')),p) for p in source.rglob('*') if p.is_file())
    if not all(name in files for name in ('geography/index.json','hydrography/index.json','uls.sqlite','repeaters/repeaters.json')):
        raise ValueError('Complete prepared map, FCC and repeater snapshots required')
    if any(p.is_symlink() for p in files.values()):raise ValueError('Reference snapshots must be regular files')
    manifest=dict(schema_version=1,product_version=(ROOT/'VERSION').read_text().strip(),files={n:dict(sha256=digest(p),size=p.stat().st_size) for n,p in sorted(files.items())})
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as raw,gzip.GzipFile(fileobj=raw,mode='wb',filename='',mtime=0,compresslevel=1) as zipped,tarfile.open(fileobj=zipped,mode='w|') as tar:
        for name,path in sorted(files.items()):
            info=tarfile.TarInfo('data/'+name);info.size=path.stat().st_size;info.mode=0o644
            with path.open('rb') as source:tar.addfile(info,source)
        payload=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
        info=tarfile.TarInfo('data/MANIFEST.json');info.size=len(payload);info.mode=0o644;tar.addfile(info,io.BytesIO(payload))
    receipt=dict(archive=output.name,sha256=digest(output),size=output.stat().st_size,files=len(files),unpacked_bytes=sum(row['size'] for row in manifest['files'].values()))
    output.with_suffix(output.suffix+'.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    package(parser.parse_args().output)
