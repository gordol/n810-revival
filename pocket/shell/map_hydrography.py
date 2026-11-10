"""View-resolution polygon hydrography; spatial tiles, no place-specific rules."""
from pathlib import Path
from data_paths import data_root
from functools import lru_cache
import json,gzip,hashlib,math,platform
PATH=data_root()/'hydrography/index.json'
def signature():
 if not PATH.is_file():return ()
 s=PATH.stat();return str(PATH),s.st_mtime_ns,s.st_size
@lru_cache(maxsize=2)
def index(identity):
 data=json.loads(PATH.read_text())
 if not data.get('complete'):raise ValueError('Incomplete hydrography catalogue')
 return data
@lru_cache(maxsize=192 if platform.machine().lower() not in ('armv6l','armv7l','armv7','arm') else 64)
def tile(name,digest):
 raw=(PATH.parent/name).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Hydrography tile integrity failure')
 polygons=json.loads(gzip.decompress(raw))
 for poly in polygons:
  outer=poly['rings'][0];xs=[p[0] for p in outer];ys=[p[1] for p in outer]
  poly['bbox']=(min(xs),min(ys),max(xs),max(ys));area=0
  for n,ring in enumerate(poly['rings']):
   x0,y0=ring[0];value=abs(sum((a[0]-x0)*(b[1]-y0)-(b[0]-x0)*(a[1]-y0) for a,b in zip(ring,ring[1:])))/2
   area+=value if n==0 else -value
  poly['area']=max(0,area)
 return polygons
def labels():return index(signature()).get('labels',[]) if signature() else []
def mask(view):
 identity=signature()
 if not identity:return None
 import numpy as np
 from PIL import Image,ImageDraw
 data=index(identity);w,h=view.width,view.height*2
 dx=view.span/max(1,w-1)/(111.32*math.cos(math.radians(view.center[0])));dy=view.span/max(1,w-1)*view.cell_aspect/2/111.32
 if dx<=0 or dy<=0:return None
 west=view.center[1]-(w-1)/2*dx;north=view.center[0]+(h-1)/2*dy;east=west+(w-1)*dx;south=north-(h-1)*dy
 a,b,c,d=data['coverage']
 if east<a or west>c or north<b or south>d:return None
 image=Image.new('L',(w,h),1);draw=ImageDraw.Draw(image);step=data['step']
 coverage=data.get('coverage_geometry')
 if coverage:
  image=Image.new('L',(w,h),255);draw=ImageDraw.Draw(image)
  polygons=[coverage['coordinates']] if coverage['type']=='Polygon' else coverage['coordinates']
  for rings in polygons:
   for n,ring in enumerate(rings):draw.polygon([((lon-west)/dx,(north-lat)/dy) for lon,lat in ring],fill=1 if n==0 else 255)
 scale=4 if w*h<=250000 else 2 if w*h<=1000000 else 1
 offset=(scale-1)/2
 water=Image.new('L',(w*scale,h*scale),0)
 for iy in range(math.floor(max(south,b)/step),math.floor(min(north,d)/step)+1):
  for ix in range(math.floor(max(west,a)/step),math.floor(min(east,c)/step)+1):
   row=data['tiles'].get(f'{ix},{iy}')
   if row is None:continue
   for poly in tile(row['file'],row['sha256']):
    pa,pb,pc,pd_=poly['bbox']
    if pc<west or pa>east or pd_<south or pb>north or poly['area']<dx*dy/8:continue
    left=max(0,math.floor((pa-west)/dx*scale+offset));right=min(w*scale,math.ceil((pc-west)/dx*scale+offset)+1)
    top=max(0,math.floor((north-pd_)/dy*scale+offset));bottom=min(h*scale,math.ceil((north-pb)/dy*scale+offset)+1)
    if right<=left or bottom<=top:continue
    # Union independent polygon masks, preserving islands and overlaps. A small
    # pond must not become a whole blue map cell merely through pixel rounding.
    part=Image.new('L',(right-left,bottom-top),0);pd=ImageDraw.Draw(part)
    for n,ring in enumerate(poly['rings']):pd.polygon([((lon-west)/dx*scale+offset-left,(north-lat)/dy*scale+offset-top) for lon,lat in ring],fill=255 if n==0 else 0)
    water.paste(255,(left,top),part)
 result=np.asarray(image).astype('i1');lon=west+np.arange(w)*dx;lat=north-np.arange(h)*dy
 result[np.asarray(water.resize((w,h),Image.Resampling.BOX))>=128]=0
 # An inland-water inventory describes water presence, not land/ocean absence.
 if not data.get('defines_land',False):result[result==1]=-1
 inside=(lon[None,:]>=a)&(lon[None,:]<=c)&(lat[:,None]>=b)&(lat[:,None]<=d)
 result[~inside]=-1
 return result
