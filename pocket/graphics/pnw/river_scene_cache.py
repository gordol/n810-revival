"""Private, replaceable cache for static terrain and wildlife GPU buffers."""
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
    graphics=here.parent
    shell=graphics.parent/'shell'
    inputs=[here/(name+'.py') for name in (
        'scene','river_scene_cache','river_walk','river_channel','river_camp','river_explore',
        'river_detail','rainier_habitat','forest_floor','wildlife_models','mesh','species')]
    inputs.extend(shell/path for path in ('geometry.py','vegetation.py','apps/landscape-lab/marmot_art.py'))
    inputs.extend(sorted(graphics.glob('*.mesh.gz')))
    inputs.extend(sorted((graphics/'assets/ohanapecosh').glob('*')))
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


def load(path,key,species_count,*,summit=False,prepare=False):
    with zipfile.ZipFile(path) as archive:
        if archive.getinfo('scene').file_size>256*1024:raise ValueError('oversized scene metadata')
        meta=json.loads(archive.read('scene'))
        if meta['key']!=key:raise ValueError('scene changed')
        nv=archive.getinfo('vertices').file_size
        ni=archive.getinfo('indices').file_size
        if not 0<nv<=3_000_000*28 or nv%28 or not 0<ni<=2_000_000*4 or ni%4:
            raise ValueError('invalid scene buffers')
        if not summit and archive.getinfo('canopy').file_size!=1024**2:
            raise ValueError('invalid canopy size')
        base,terrain=meta['base'],meta['terrain']
        n=nv//28
        if not 0<base<=terrain<=n or base%3 or terrain%3:raise ValueError('invalid terrain')
        if not prepare:
            vertices=read_array(archive,'vertices','f',nv)
            indices=read_array(archive,'indices','I',ni)
            canopy=None if summit else bytearray(archive.read('canopy'))
    spans=meta['spans']
    if species_count is not None and len(spans)!=species_count:raise ValueError('invalid species count')
    for first,stride,frames,start,count in spans:
        if min(stride,frames,count)<=0 or first<terrain or first+frames*stride>n or start<0 or start+count>ni//4:
            raise ValueError('invalid wildlife span')
    plants=[(str(kind),float(x),float(z)) for kind,x,z in meta['plants']]
    if prepare:
        print(f'{path.name} already prepared',flush=True)
        return
    return vertices,terrain,indices,spans,base,canopy,plants,meta.get('panorama',False)


def store(path,key,world,plants):
    field,_,vertices,terrain,indices,spans,base,canopy=world
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as output:
            temp=Path(output.name)
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
                archive.writestr('scene',json.dumps(dict(key=key,terrain=terrain,base=base,spans=spans,plants=plants,panorama=getattr(field,'panorama',False))))
                for name,values in (('vertices',vertices),('indices',indices)):
                    data=memoryview(values).cast('B')
                    with archive.open(name,'w') as stream:
                        for offset in range(0,len(data),1024*1024):stream.write(data[offset:offset+1024*1024])
                if canopy is not None:archive.writestr('canopy',canopy)
        os.replace(temp,path)
    finally:
        if temp is not None:temp.unlink(missing_ok=True)


def valley_world(high,plant_sites,*,prepare=False):
    from geometry import Vec
    from pnw.scene import build_world,ENCOUNTERS,surface,valley_floor
    folder=Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'pocket/rainier-walk'
    path=folder/('valley-high.zip' if high else 'valley-low.zip')
    try:
        key=source_key()
    except OSError:
        if prepare:raise
        return build_world(high,plant_sites)
    try:
        cached=load(path,key,len(ENCOUNTERS),prepare=prepare)
    except (OSError,ValueError,TypeError,KeyError,EOFError,zipfile.BadZipFile,zlib.error):
        world=build_world(high,plant_sites)
        try:store(path,key,world,plant_sites)
        except OSError:
            if prepare:raise
        return world
    if prepare:return
    vertices,terrain,indices,spans,base,canopy,plants,_=cached
    field,_=valley_floor()
    plant_sites[:]=plants
    return field,Vec(0,surface(field,0,0),0),vertices,terrain,indices,spans,base,canopy


def summit_world(*,prepare=False):
    from dataclasses import replace
    from data_paths import rainier_cache,rainier_root
    from geometry import Vec
    from pnw.scene import build_world,region_field,surface,SUMMIT_DANCERS
    from rainier_data import download,FILES
    download()
    here=Path(__file__).resolve().parent
    inputs=[rainier_root()/name for name in FILES]
    inputs.extend(here/(name+'.py') for name in ('hiking','summit_detail','summit_approach',
                  'summit_horizon','summit_ski','paradise_meadow','fremont_lookout'))
    inputs.extend((here.parent/'assets/summit/elevation.i16.zlib',
                   here.parents[1]/'shell/terrain_elevation.py'))
    inputs.extend((rainier_cache()/name) for name in ('summit-approach-v1.f32.zlib','horizon-terrarium-v2.i16.zlib'))
    def identity():
        digest=hashlib.sha256(source_key().encode())
        for path in inputs:
            digest.update(path.read_bytes() if path.is_file() else b'missing')
        return digest.hexdigest()
    key=identity()
    folder=Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'pocket/rainier-walk'
    path=folder/'rainier-summit.zip'
    field=None if prepare else region_field()
    dancers=None if prepare else len(SUMMIT_DANCERS) if getattr(field,'inset',None) else 0
    try:
        cached=load(path,key,dancers,summit=True,prepare=prepare)
    except (OSError,ValueError,TypeError,KeyError,EOFError,zipfile.BadZipFile,zlib.error):
        if field is None:field=region_field()
        world=build_world(False,None,True,field=field)
        # Missing remote detail can be retried on a later visit.
        if getattr(field,'inset',None) and (not getattr(field.inset,'inset',None)
                or not getattr(world[0],'panorama',False) or not inputs[-1].is_file()):
            if prepare:raise ValueError('Summit detail incomplete. Retry terrain preparation.')
            return world
        try:store(path,identity(),world,[])
        except OSError:
            if prepare:raise
        return world
    if prepare:return
    vertices,terrain,indices,spans,base,canopy,_,panorama=cached
    if panorama:field=replace(field,panorama=True)
    return field,Vec(0,surface(field,0,0),0),vertices,terrain,indices,spans,base,canopy


def regional_mesh(region,elevation,textured,build,*,require_cache=False,prepare=False):
    """Keep one validated, atomically replaceable vertex buffer per region."""
    here=Path(__file__).resolve().parent
    graphics=here.parent
    sources=('outings','terrain','scene','pike_market','market_visit','seattle_places','forest_floor')
    digest=hashlib.sha256(f'{sys.byteorder}/{region}/{textured}'.encode())
    digest.update(elevation)
    inputs=[here/(name+'.py') for name in sources]
    inputs.extend(graphics.parent/'shell'/name for name in ('geometry.py','vegetation.py'))
    if region!='hoh':
        inputs.extend(sorted((graphics/'assets/seattle').glob('*.json')))
        inputs.extend(sorted((graphics/'assets/seattle').glob('*.csv')))
    for path in inputs:digest.update(hashlib.sha256(path.read_bytes()).digest())
    key=digest.digest()
    folder=Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'pocket/rainier-walk'
    target=folder/(region+'-mesh.zip')
    try:
        with zipfile.ZipFile(target) as archive:
            if archive.comment==key:
                size=archive.getinfo('vertices').file_size
                if prepare and 0<size<=3_000_000*28 and size%84==0:
                    print(f'{target.name} already prepared',flush=True)
                    return None
                mesh=read_array(archive,'vertices','f',3_000_000*28)
                if len(mesh)%21==0:return mesh
    except (OSError,ValueError,KeyError,EOFError,zipfile.BadZipFile,zlib.error):pass
    mesh=build()
    tmp=None
    try:
        folder.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=folder,delete=False) as output:
            tmp=Path(output.name)
            with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
                archive.comment=key
                archive.writestr('vertices',memoryview(mesh).cast('B'))
        tmp.replace(target)
    except OSError:
        if require_cache or prepare:raise
    finally:
        if tmp:tmp.unlink(missing_ok=True)
    return mesh
