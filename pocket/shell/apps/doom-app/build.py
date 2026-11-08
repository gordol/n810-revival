#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the bundled DoomGeneric source; acquire Freedoom only on explicit request."""
from pathlib import Path
import argparse,hashlib,json,os,re,shlex,shutil,subprocess,urllib.request,zipfile
HERE=Path(__file__).resolve().parent
DATA_URL='https://github.com/freedoom/freedoom/releases/download/v0.13.0/freedoom-0.13.0.zip'
DATA_SHA='3f9b264f3e3ce503b4fb7f6bdcb1f419d93c7b546f4df3e874dd878db9688f59'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--cc',default=os.environ.get('CC','cc'))
 p.add_argument('--wad',type=Path,help='reuse an existing Freedoom1 WAD, without downloading or copying it')
 p.add_argument('--no-download',action='store_true')
 p.add_argument('--engine-only',action='store_true',help='compile source without acquiring or selecting game data')
 p.add_argument('--cache',type=Path,default=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'pocket/freedoom-0.13.0')
 a=p.parse_args();cc=shlex.split(a.cc);source=HERE/'vendor/doomgeneric/doomgeneric';build=HERE/'build';build.mkdir(parents=True,exist_ok=True)
 objects=re.search(r'^SRC_DOOM\s*=\s*(.+)$',(source/'Makefile').read_text(),re.M)[1].split()
 files=[source/(n[:-2]+'.c') for n in objects if n!='doomgeneric_xlib.o']
 flags=['-O2','-DNORMALUNIX','-D_DEFAULT_SOURCE','-DDOOMGENERIC_RESX=320','-DDOOMGENERIC_RESY=200','-Wno-incompatible-pointer-types','-Wno-int-conversion']
 subprocess.run([*cc,*flags,'-DENGINE','-I'+str(source),*map(str,files),str(HERE/'bridge.c'),'-lm','-o',str(build/'doom-engine')],check=True)
 subprocess.run([*cc,'-O3','-std=c11','-shared','-fPIC',str(HERE/'bridge.c'),'-o',str(build/'bridge.so')],check=True)
 record={'engine_source':json.loads((source.parent/'SOURCE.json').read_text())['archive_sha256'],'bridge_source':sha(HERE/'bridge.c'),'engine':sha(build/'doom-engine'),'bridge':sha(build/'bridge.so'),'compiler':cc,'flags':flags}
 if a.engine_only:
  (build/'BUILD.json').write_text(json.dumps(record,indent=2)+'\n');print('Doom engine built; game data was not acquired.');return
 if a.wad:
  wad=a.wad.expanduser().resolve()
  if not wad.is_file():p.error('WAD does not exist')
 else:
  a.cache.mkdir(parents=True,exist_ok=True);wad=a.cache/'freedoom1.wad'
  if not wad.exists():
   if a.no_download:p.error('Freedoom is not cached; supply --wad or allow the explicit download')
   archive=a.cache/'freedoom-0.13.0.zip'
   if not archive.exists():
    temporary=archive.with_suffix('.part')
    with urllib.request.urlopen(DATA_URL,timeout=180) as response,temporary.open('wb') as output:shutil.copyfileobj(response,output)
    if sha(temporary)!=DATA_SHA:temporary.unlink();raise SystemExit('Freedoom archive checksum mismatch')
    temporary.replace(archive)
   if sha(archive)!=DATA_SHA:raise SystemExit('Cached Freedoom archive checksum mismatch')
   with zipfile.ZipFile(archive) as z:
    for name in ('freedoom1.wad','COPYING.txt','CREDITS.txt','CREDITS-MUSIC.txt'):
     with z.open('freedoom-0.13.0/'+name) as inp,(a.cache/name).open('wb') as out:shutil.copyfileobj(inp,out)
   wad=wad.resolve()
 target=HERE/'vendor/freedoom-0.13.0/freedoom1.wad';target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists() or target.is_symlink():
  if target.resolve()!=wad:target.unlink();target.symlink_to(wad)
 else:target.symlink_to(wad)
 record['wad']=sha(wad)
 (build/'BUILD.json').write_text(json.dumps(record,indent=2)+'\n');print('Doom ready. Open Doom / Freedoom in Pocket; no data is downloaded at app launch.')
if __name__=='__main__':main()
