"""Normal desktop map land/water geometry, rasterized at each view's resolution."""
from functools import lru_cache
from pathlib import Path
from data_paths import data_root
import gzip,json,math
PATH=data_root()/'shoreline-puget.json.gz'
def signature():
 if not PATH.is_file():return ()
 s=PATH.stat();return (str(PATH),s.st_mtime_ns,s.st_size)
@lru_cache(maxsize=2)
def load(identity):return json.loads(gzip.decompress(PATH.read_bytes()))
def mask(view):
 from map_hydrography import mask as hydro_mask
 fine=hydro_mask(view)
 identity=signature()
 if not identity:return fine
 import numpy as np
 from PIL import Image,ImageDraw
 data=load(identity);w,h=view.width,view.height*2
 dx=view.span/max(1,w-1)/(111.32*math.cos(math.radians(view.center[0])))
 dy=view.span/max(1,w-1)*view.cell_aspect/2/111.32
 if dx==0 or dy==0:return None
 west=view.center[1]-(w-1)/2*dx;east=west+(w-1)*dx
 north=view.center[0]+(h-1)/2*dy;south=north-(h-1)*dy
 bw,bs,be,bn=data['bbox']
 if east<bw or west>be or north<bs or south>bn:return fine
 image=Image.new('L',(w,h),0);draw=ImageDraw.Draw(image)
 def paint(rows,value):
  for poly in rows:
   a,b,c,d=poly['bbox']
   if c<west or a>east or d<south or b>north:continue
   for i,ring in enumerate(poly['rings']):
    draw.polygon([((lon-west)/dx,(north-lat)/dy) for lon,lat in ring],fill=value if i==0 else 1-value)
 paint(data['land'],1);paint(data['lakes'],0)
 from map_geography import load as geography,signature as geography_signature
 detail=geography(geography_signature())
 paint(detail.get('water',[]),0)
 result=np.asarray(image).astype('i1')
 lon=west+np.arange(w)*dx;lat=north-np.arange(h)*dy
 inside=(lon[None,:]>=bw)&(lon[None,:]<=be)&(lat[:,None]>=bs)&(lat[:,None]<=bn)
 result[~inside]=-1
 if fine is not None:
  known=fine>=0;result[known]=fine[known]
 return result
