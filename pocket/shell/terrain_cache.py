"""Bounded completed LOS views, invalidated by terrain and calculation changes."""
import hashlib,json,os
from pathlib import Path
from runtime_codec import pack,unpack

LIMIT=8*1024*1024

def root():
    return Path(os.environ.get('POCKET_LOS_CACHE',Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'current-world/los'))

def identity(start,options):
    from local_elevation import revision
    source=b''.join(Path(__file__).with_name(name).read_bytes() for name in ('terrain_sites.py','terrain_elevation.py','local_elevation.py','path_profile.py'))
    raw=json.dumps([start,options,revision(),hashlib.sha256(source).hexdigest()],sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()

def read(key):
    try:
        with (root()/(key+'.msgpack')).open('rb') as source:raw=source.read(LIMIT+33)
        if len(raw)>LIMIT+32 or hashlib.sha256(raw[32:]).digest()!=raw[:32]:return None
        result=unpack(raw[32:],limit=LIMIT)
        if not result.get('complete') or not isinstance(result.get('cells'),list) or len(result['cells'])>30000:return None
        result['center']=tuple(result['center'])
        for cell in result['cells']:
            cell['position']=tuple(cell['position'])
            if 'raster_km' in cell:cell['raster_km']=tuple(cell['raster_km'])
        return result
    except (OSError,ValueError,KeyError,TypeError):return None

def write(key,result):
    if not result or not result.get('complete'):return
    try:
        raw=pack(result)
        if len(raw)>LIMIT:return
        directory=root();directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        path=directory/(key+'.msgpack');temporary=directory/(key+'.'+str(os.getpid())+'.tmp')
        with temporary.open('wb') as target:target.write(hashlib.sha256(raw).digest()+raw)
        temporary.chmod(0o600);temporary.replace(path)
        files=sorted(directory.glob('*.msgpack'),key=lambda p:p.stat().st_mtime,reverse=True)
        total=0
        for i,item in enumerate(files):
            total+=item.stat().st_size
            if i>=32 or total>32*1024*1024:item.unlink(missing_ok=True)
    except OSError:pass
