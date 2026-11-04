"""Shared best-first elevation catalogue for display, profiles, and LOS."""
from array import array
from functools import lru_cache
from pathlib import Path
from data_paths import data_root,content_identity
from threading import RLock
import hashlib,json,sys,time,zlib,math,platform
_lock=RLock();_checked=0.;_signature=();_catalogue=();_buckets={}
def sources():
 root=Path(__file__).with_name('data')
 paths=[root/'elevation-western-wa/index.json',root/'elevation-lakewood/index.json',data_root()/'elevation-western-wa/index.json',data_root()/'elevation-lakewood/index.json']
 paths+=sorted((data_root()/'elevation-fine').glob('*-guarded/index.json'))
 return [p for p in paths if p.is_file()]
@lru_cache(maxsize=128)
def read_index(path,modified,size):
 if size>1024*1024:raise ValueError('Elevation index exceeds bounds')
 m=json.loads(path.read_text())
 if m.get('tile_size')!=256 or m.get('units')!='meters' or not 2<=m['nx']<=16384 or not 2<=m['nz']<=16384:raise ValueError('Invalid elevation index')
 m.pop('maximum_bounds',None)
 m['catalogue_id']=str(path)
 m['_index_stamp']=modified
 if '-guarded' in path.parent.name:m['source']='USGS 3DEP fine western Washington export'
 return m
def catalogue(force=False):
 global _checked,_signature,_catalogue,_buckets
 with _lock:
  now=time.monotonic()
  if force or now-_checked>1:
   paths=sources();signature=tuple((str(p),p.stat().st_mtime_ns,p.stat().st_size) for p in paths)
   if signature!=_signature:
    entries=[(Path(p),read_index(Path(p),stamp,size)) for p,stamp,size in signature]
    entries.sort(key=lambda item:abs(item[1]['longitude_step']*item[1]['latitude_step']))
    buckets={}
    for entry in entries:
     m=entry[1];west=m['longitude_first'];south=m['latitude_first'];east=west+(m['nx']-1)*m['longitude_step'];north=south+(m['nz']-1)*m['latitude_step']
     for x in range(math.floor(min(west,east)*4),math.floor(max(west,east)*4)+1):
      for y in range(math.floor(min(south,north)*4),math.floor(max(south,north)*4)+1):buckets.setdefault((x,y),[]).append(entry)
    _catalogue=tuple(entries);_signature=signature;_buckets=buckets
   _checked=now
  return _catalogue
def revision():
 catalogue();return tuple(content_identity(Path(path)) for path,stamp,size in _signature)
@lru_cache(maxsize=4 if platform.machine().lower() in ('arm','armv6l','armv7','armv7l') else 64)
def tile(path,stamp,tx,ty):
 m=read_index(path,stamp,path.stat().st_size);item=m['tiles'][f'{tx},{ty}'];name=f'{tx}-{ty}.i16.zlib'
 if item['file']!=name or not 1<=item['width']<=256 or not 1<=item['height']<=256:raise ValueError('Invalid elevation tile')
 with (path.parent/name).open('rb') as source:raw=source.read(256*256*2+4097)
 if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Elevation checksum differs')
 expected=item['width']*item['height']*2;decoder=zlib.decompressobj();data=decoder.decompress(raw,expected+1)
 if len(data)!=expected or not decoder.eof or decoder.unused_data:raise ValueError('Elevation tile length differs')
 values=array('h');values.frombytes(data)
 if sys.byteorder!='little':values.byteswap()
 return values,item['width']
def sample(latitude,longitude):
 catalogue()
 for path,m in _buckets.get((math.floor(longitude*4),math.floor(latitude*4)),()):
  x=(longitude-m['longitude_first'])/m['longitude_step'];y=(latitude-m['latitude_first'])/m['latitude_step']
  if not 0<=x<=m['nx']-1 or not 0<=y<=m['nz']-1:continue
  ix=min(m['nx']-2,int(x));iy=min(m['nz']-2,int(y));fx=x-ix;fy=y-iy;stamp=m['_index_stamp']
  def get(xx,yy):
   values,width=tile(path,stamp,xx//256,yy//256);return values[yy%256*width+xx%256]
  a,b,c,d=get(ix,iy),get(ix+1,iy),get(ix,iy+1),get(ix+1,iy+1)
  if m['nodata'] in (a,b,c,d):continue
  return a*(1-fx)*(1-fy)+b*fx*(1-fy)+c*(1-fx)*fy+d*fx*fy,m
 return None,None
