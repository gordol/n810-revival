"""Private, replaceable cache for the valley's static GPU buffers."""
from array import array
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import zipfile
import zlib


def source_key():
    here=Path(__file__).resolve().parent
    shell=here.parent/'shell'
    inputs=[here/(name+'.py') for name in (
        'rainier_pixels','river_scene_cache','river_walk','river_channel','river_camp','river_explore',
        'river_detail','rainier_habitat','forest_floor','wildlife_models','pnw_mesh','pnw_species')]
    inputs.extend(shell/path for path in ('geometry.py','vegetation.py','apps/landscape-lab/marmot_art.py'))
    inputs.extend(sorted(here.glob('*.mesh.gz')))
    inputs.extend(sorted((here/'assets/ohanapecosh').glob('*')))
    digest=hashlib.sha256(f'{sys.implementation.cache_tag}/{sys.byteorder}'.encode())
    for path in inputs:
        digest.update(path.name.encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def read_array(archive,name,kind,max_bytes):
    size=archive.getinfo(name).file_size
    values=array(kind)
    if not 0<size<=max_bytes or size%values.itemsize:raise ValueError('invalid buffer size')
    with archive.open(name) as stream:
        while chunk:=stream.read(1024*1024):values.frombytes(chunk)
    return values


def load(path,key,species_count):
    with zipfile.ZipFile(path) as archive:
        if archive.getinfo('scene').file_size>256*1024:raise ValueError('oversized scene metadata')
        meta=json.loads(archive.read('scene'))
        if meta['key']!=key:raise ValueError('scene changed')
        vertices=read_array(archive,'vertices','f',2_000_000*28)
        indices=read_array(archive,'indices','I',2_000_000*4)
        if archive.getinfo('canopy').file_size!=1024**2:raise ValueError('invalid canopy size')
        canopy=bytearray(archive.read('canopy'))
    base,terrain=meta['base'],meta['terrain']
    n=len(vertices)//7
    if len(vertices)%7 or not 0<base<=terrain<=n or base%3 or terrain%3:raise ValueError('invalid terrain')
    spans=meta['spans']
    if len(spans)!=species_count:raise ValueError('invalid species count')
    for first,stride,frames,start,count in spans:
        if min(stride,frames,count)<=0 or first<terrain or first+frames*stride>n or start<0 or start+count>len(indices):
            raise ValueError('invalid wildlife span')
    plants=[(str(kind),float(x),float(z)) for kind,x,z in meta['plants']]
    return vertices,terrain,indices,spans,base,canopy,plants


def store(path,key,world,plants):
    _,_,vertices,terrain,indices,spans,base,canopy=world
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as output:
            temp=Path(output.name)
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
                archive.writestr('scene',json.dumps(dict(key=key,terrain=terrain,base=base,spans=spans,plants=plants)))
                for name,values in (('vertices',vertices),('indices',indices)):
                    data=memoryview(values).cast('B')
                    with archive.open(name,'w') as stream:
                        for offset in range(0,len(data),1024*1024):stream.write(data[offset:offset+1024*1024])
                archive.writestr('canopy',canopy)
        os.replace(temp,path)
    finally:
        if temp is not None:temp.unlink(missing_ok=True)


def valley_world(high,plant_sites):
    from geometry import Vec
    from rainier_pixels import build_world,ENCOUNTERS,surface,valley_floor
    folder=Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'pocket/rainier-walk'
    path=folder/('valley-high.zip' if high else 'valley-low.zip')
    try:
        key=source_key()
    except OSError:return build_world(high,plant_sites)
    try:
        vertices,terrain,indices,spans,base,canopy,plants=load(path,key,len(ENCOUNTERS))
    except (OSError,ValueError,TypeError,KeyError,EOFError,zipfile.BadZipFile,zlib.error):
        world=build_world(high,plant_sites)
        try:store(path,key,world,plant_sites)
        except OSError:pass
        return world
    field,_=valley_floor()
    plant_sites[:]=plants
    return field,Vec(0,surface(field,0,0),0),vertices,terrain,indices,spans,base,canopy
