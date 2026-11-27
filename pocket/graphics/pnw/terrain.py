"""Offline georeferenced outings using Mapzen Terrarium elevation tiles."""
from array import array
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError
import zlib

# Centre, zoom, source pixels per vertex, columns and rows.
GRIDS={'sound':(47.23,-122.18,9,2,241,289),'hoh':(47.861,-123.935,15,2,257,257)}

def pixel(lat,lon,zoom):
    scale=256*(1<<zoom)
    return (lon+180)*scale/360,(1-math.asinh(math.tan(math.radians(lat)))/math.pi)*scale/2

def layout(region):
    lat,lon,zoom,step,nx,nz=GRIDS[region]
    cx,cy=map(round,pixel(lat,lon,zoom))
    spacing=40075016.686*math.cos(math.radians(lat))*step/(256*(1<<zoom))
    return cx,cy,spacing

def location(region,lat,lon):
    _,_,zoom,step,_,_=GRIDS[region]
    cx,cy,spacing=layout(region)
    px,py=pixel(lat,lon,zoom)
    return (px-cx)*spacing/step,(cy-py)*spacing/step

def convert(region,folder):
    from PIL import Image
    _,_,_,step,nx,nz=GRIDS[region]
    cx,cy,_=layout(region)
    values=array('h')
    tiles={}
    for row in range(nz):
        py=cy+(nz//2-row)*step
        for col in range(nx):
            px=cx+(col-nx//2)*step
            key=px//256,py//256
            if key not in tiles:
                with Image.open(folder/f'{key[0]}-{key[1]}.png') as im:
                    if im.size!=(256,256):raise ValueError('Invalid elevation tile')
                    tiles[key]=im.convert('RGB')
            r,g,_=tiles[key].getpixel((px%256,py%256))
            values.append(256*r+g-32768)
    if sys.byteorder!='little':values.byteswap()
    (folder/'grid').write_bytes(zlib.compress(values.tobytes()))

def elevations(region):
    from data_paths import rainier_cache
    _,_,zoom,step,nx,nz=GRIDS[region]
    cx,cy,_=layout(region)
    dest=rainier_cache()/f'{region}-terrarium-v1.i16.zlib'
    def read(path):
        data=array('h')
        data.frombytes(zlib.decompress(path.read_bytes()))
        if len(data)!=nx*nz:raise ValueError('Incomplete outing grid')
        if sys.byteorder!='little':data.byteswap()
        return data
    try:return read(dest)
    except (FileNotFoundError,zlib.error,ValueError):pass
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
        folder=Path(tmp)
        def fetch(key):
            x,y=key
            url=f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{x}/{y}.png'
            with urlopen(url,timeout=15) as stream:data=stream.read(300001)
            if len(data)>300000:raise ValueError('Oversize elevation tile')
            (folder/f'{x}-{y}.png').write_bytes(data)
        cols=range((cx-nx//2*step)//256,(cx+nx//2*step)//256+1)
        rows=range((cy-nz//2*step)//256,(cy+nz//2*step)//256+1)
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetch,((x,y) for x in cols for y in rows)))
        convert_local(folder,region,lambda:convert(region,folder))
        result=read(folder/'grid')
        (folder/'grid').replace(dest)
        return result

# A 5:6 export matches the 240 by 288 Sound grid cells.
IMAGE_SIZE=(1280,1536)

def aerial_url(patch=None):
    _,_,zoom,step,nx,nz=GRIDS['sound']
    cx,cy,_=layout('sound')
    world=40075016.68557849
    scale=world/(256*(1<<zoom))
    x=cx*scale-world/2
    y=world/2-cy*scale
    w=(nx-1)*step*scale/2
    h=(nz-1)*step*scale/2
    size=IMAGE_SIZE
    if patch is not None:
        _,_,spacing=layout('sound')
        projection=step*scale/spacing
        x+=patch[0]*PATCH_STEP*projection
        y+=patch[1]*PATCH_STEP*projection
        w=h=PATCH_WIDTH*projection/2
        size=(1024,1024)
    args={'bbox':','.join(map(str,(x-w,y-h,x+w,y+h))),'bboxSR':3857,
          'imageSR':3857,'size':','.join(map(str,size)),'format':'jpg','f':'image'}
    return 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export?'+urlencode(args)

def decode_aerial(folder,size=IMAGE_SIZE):
    from PIL import Image
    with Image.open(folder/'image.jpg') as im:
        if im.size!=size:raise ValueError('Unexpected aerial extent')
        rgb=im.convert('RGB').transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        (folder/'rgb').write_bytes(rgb.tobytes())

def convert_local(folder,mode,convert_image):
    if os.environ.get('POCKET_TERMUX')=='1':
        run_image_worker(Path(__file__),folder,mode)
    else:convert_image()

def sound_aerial():
    from data_paths import rainier_cache
    dest=rainier_cache()/'sound-usgs-1280x1536-v1.rgb'
    expected=math.prod(IMAGE_SIZE)*3
    def read(path):
        if path.stat().st_size!=expected:raise ValueError('Incomplete aerial texture')
        return bytearray(path.read_bytes())
    try:return read(dest)
    except (FileNotFoundError,ValueError):pass
    # A cached heightfield remains playable when the imagery server is offline.
    try:
        with tempfile.TemporaryDirectory(dir=dest.parent) as tmp:
            folder=Path(tmp)
            with urlopen(aerial_url(),timeout=12) as stream:data=stream.read(expected+1)
            if len(data)>expected:return None
            (folder/'image.jpg').write_bytes(data)
            convert_local(folder,'aerial',lambda:decode_aerial(folder))
            rgb=read(folder/'rgb')
            (folder/'rgb').replace(dest)
            return rgb
    except (OSError,ValueError,URLError,subprocess.SubprocessError):return None


# Tile keys use the original cache coordinate system (two steps per tile).
PATCH_WIDTH=8192
PATCH_STEP=4096
PATCH_LIMIT=128*1024**2

def relief_url(key):
    from urllib.parse import parse_qs,urlsplit
    args=parse_qs(urlsplit(aerial_url(key)).query)
    left,bottom,right,top=map(float,args['bbox'][0].split(','))
    # ArcGIS samples pixel centres. Extend the box by half a grid step.
    half=(right-left)/256
    query=dict(bbox=','.join(map(str,(left-half,bottom-half,right+half,top+half))),
               bboxSR=3857,imageSR=3857,size='129,129',pixelType='F32',format='tiff',
               adjustAspectRatio='false',interpolation='RSP_BilinearInterpolation',f='image')
    return 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage?'+urlencode(query)

def decode_relief(folder):
    from PIL import Image
    with Image.open(folder/'height.tif') as image:
        if image.size!=(129,129):raise ValueError('Unexpected elevation extent')
        pixels=image.convert('F').transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        elevations=array('f')
        elevations.frombytes(pixels.tobytes())
        values=array('h',(max(0,min(5000,round(v))) if math.isfinite(v) else 0 for v in elevations))
    if sys.byteorder!='little':values.byteswap()
    (folder/'height').write_bytes(values.tobytes())

def flight_relief(key,field,*,local_only=False):
    from data_paths import rainier_cache
    cache=rainier_cache()/'flight-imagery-v1'
    dest=cache/f'{key[0]}_{key[1]}.dem'
    try:data=dest.read_bytes()
    except FileNotFoundError:data=b''
    if len(data)!=129*129*2:
        if local_only:return None
        cache.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            folder=Path(tmp)
            with urlopen(relief_url(key),timeout=8) as stream:raw=stream.read(1024**2+1)
            if len(raw)>1024**2:raise ValueError('Oversized elevation patch')
            (folder/'height.tif').write_bytes(raw)
            convert_local(folder,'relief',lambda:decode_relief(folder))
            data=(folder/'height').read_bytes()
            (folder/'height').replace(dest)
            trim_patch_cache(cache)
    values=array('h')
    values.frombytes(data)
    if sys.byteorder!='little':values.byteswap()
    return relief_mesh(key,field,values)

def relief_mesh(key,field,values=None):
    from pnw.hiking import bounds
    from pnw.scene import surface
    from geometry import HeightField,Vec
    from struct import Struct
    west,east,south,north=bounds(field)
    x0,z0=(v*PATCH_STEP-PATCH_WIDTH/2 for v in key)
    inside=west<=x0 and x0+PATCH_WIDTH<=east and south<=z0 and z0+PATCH_WIDTH<=north
    if not inside and values is None:
        raise ValueError('Elevation is unavailable beyond the prepared map')
    cells=128 if values is not None and (not inside or max(values)>=400) else 32
    heights=[]
    rows=[]
    vertex=Struct('=7f').pack
    step=PATCH_WIDTH/cells
    mesh=array('f')
    for j in range(cells+1):
        row=[]
        for i in range(cells+1):
            x,z=x0+i*step,z0+j*step
            y=surface(field,x,z)
            if values is not None and cells==128:
                dem=values[j*129+i]
                if west<=x<=east and south<=z<=north:
                    # Keep shoreline structures and runways seated on the base mesh.
                    weight=max(0.,min(1.,(y-400.)/250.,min(i,j,128-i,128-j)/5.))
                    y+=weight*(dem-y)
                else:y=dem
            heights.append(y)
            row.append(vertex(x,y,z,.28,.39,.24,.219))
        rows.append(row)
        if j:
            a,b=rows
            mesh.frombytes(b''.join(v for i in range(cells) for v in (a[i],b[i],a[i+1],a[i+1],b[i],b[i+1])))
            rows.pop(0)
    return HeightField(cells+1,cells+1,Vec(x0,0,z0),step,step,tuple(heights),'meters'),mesh

def flight_patch(key,field=None):
    from data_paths import rainier_cache
    cache=rainier_cache()/'flight-imagery-v1'
    cache.mkdir(parents=True,exist_ok=True)
    target=cache/f'{key[0]}_{key[1]}.jpg'
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
        folder=Path(tmp)
        image=folder/'image.jpg'
        cached=True
        try:image.write_bytes(target.read_bytes())
        except FileNotFoundError:
            cached=False
            with urlopen(aerial_url(key),timeout=8) as stream:data=stream.read(4*1024**2+1)
            if len(data)>4*1024**2:raise ValueError('Oversized aerial patch')
            image.write_bytes(data)
        try:convert_local(folder,'patch',lambda:decode_aerial(folder,(1024,1024)))
        except (OSError,ValueError,ImportError,subprocess.SubprocessError):
            target.unlink(missing_ok=True)
            raise
        pixels=(folder/'rgb').read_bytes()
        if len(pixels)!=1024*1024*3:raise ValueError('Incomplete aerial patch')
        if cached and target.exists():os.utime(target,None)
        else:image.replace(target)
        relief=None
        if field is not None:
            try:relief=flight_relief(key,field)
            except (OSError,ValueError,ImportError,subprocess.SubprocessError):pass
        trim_patch_cache(cache)
        if field is not None and relief is None:relief=relief_mesh(key,field)
        return pixels,relief


def trim_patch_cache(cache):
    files=[]
    for path in cache.iterdir():
        if path.suffix not in ('.jpg','.dem'):continue
        try:stat=path.stat()
        except FileNotFoundError:continue
        files.append((stat.st_mtime,stat.st_size,path))
    total=sum(size for _,size,_ in files)
    for _,size,path in sorted(files):
        if total<=PATCH_LIMIT:break
        path.unlink(missing_ok=True)
        total-=size


def patch_corner(x,z):
    cx,cy,spacing=layout('sound')
    _,_,zoom,step,_,_=GRIDS['sound']
    size=256*(1<<zoom)
    px=cx+x*step/spacing
    py=cy-z*step/spacing
    return px/size*360-180,math.degrees(math.atan(math.sinh(math.pi*(1-2*py/size))))

def draw_map_patch(folder):
    """Pillow-only stage shared with the isolated Android map worker."""
    from PIL import Image,ImageDraw
    image=Image.frombytes('RGB',(129,129),(folder/'base').read_bytes())
    image=image.resize((1024,1024),Image.Resampling.BILINEAR,box=(.5,.5,128.5,128.5))
    features=json.loads((folder/'features').read_text())
    draw=ImageDraw.Draw(image)
    for rings in features['water']:
        # Preserve terrain and islands inside polygon holes.
        mask=Image.new('1',image.size)
        pen=ImageDraw.Draw(mask)
        for i,ring in enumerate(rings):
            if len(ring)>=6:pen.polygon(ring,fill=i==0)
        image.paste((47,92,107),(0,0,1024,1024),mask)
    for points,stream,width in features['lines']:
        if len(points)>=4:draw.line(points,fill=(64,114,133) if stream else (134,129,113),width=width)
    (folder/'rgb').write_bytes(image.tobytes())

def map_patch(key,field,*,fetch_missing=False):
    """Paint south-first pixels in the same Sound coordinates as the GPU mesh."""
    from types import SimpleNamespace
    import map_geography
    import map_hydrography
    from pnw.scene import surface
    x0,z0=(v*PATCH_STEP-PATCH_WIDTH/2 for v in key)
    bounds=(*patch_corner(x0,z0),*patch_corner(x0+PATCH_WIDTH,z0+PATCH_WIDTH))
    relief=flight_relief(key,field,local_only=True)
    if relief is None:
        try:relief=relief_mesh(key,field)
        except ValueError:
            if not fetch_missing:raise
            relief=flight_relief(key,field)
    heights=relief[0]
    step=PATCH_WIDTH/128
    base=bytearray()
    for j in range(129):
        z=z0+j*step
        for i in range(129):
            x=x0+i*step
            y=surface(heights,x,z)
            slope=(surface(heights,x-step,z)-surface(heights,x+step,z)
                   +surface(heights,x,z+step)-surface(heights,x,z-step))/(2*step)
            shade=max(.60,min(1.17,.92+.25*slope))
            color=(47,92,107) if y<=0 else (213,220,223) if y>2350 else (135,133,117) if y>1550 else (85,109,84)
            base.extend(min(255,round(c*shade)) for c in color)
    def points(coords):
        line=[]
        for lon,lat in coords:
            x,z=location('sound',lat,lon)
            line.extend((round((x-x0)/8-.5),round((z-z0)/8-.5)))
        return line
    features={'water':[[points(ring) for ring in poly['rings']] for poly in map_hydrography.polygons_in(bounds)],'lines':[]}
    view=SimpleNamespace(bbox=bounds,span=PATCH_WIDTH/1000,ground_m_per_halfcell=8.)
    streams,roads,_=map_geography.selected_geography(None,view,forest_roads=True)
    for group,stream in ((streams,True),(roads,False)):
        for feature in group:
            width=2 if feature.get('kind') in ('motorway','trunk','river') else 1
            features['lines'].append((points(feature['points']),stream,width))
    with tempfile.TemporaryDirectory() as tmp:
        folder=Path(tmp)
        (folder/'base').write_bytes(base)
        (folder/'features').write_text(json.dumps(features,separators=(',',':')))
        convert_local(folder,'map',lambda:draw_map_patch(folder))
        return (folder/'rgb').read_bytes(),relief

def load_surface(key,field,source):
    if source!='Drawn terrain':
        try:return flight_patch(key,field)
        except (OSError,ValueError,ImportError,subprocess.SubprocessError):pass
    return map_patch(key,field,fetch_missing=source!='Drawn terrain')


class FlightImagery:
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.job=self.pending=None
        self.resident={}
        self.retry={}

    def update(self,x,z,field,source='Aerial'):
        cx,cz=(2*round(v/PATCH_WIDTH) for v in (x,z))
        wanted=sorted(((cx+dx,cz+dz) for dx in (-2,0,2) for dz in (-2,0,2)),
                      key=lambda k:(k[0]*PATCH_STEP-x)**2+(k[1]*PATCH_STEP-z)**2)
        result=None
        now=time.monotonic()
        self.retry={k:t for k,t in self.retry.items() if k[0] in wanted and k[1]==source and t>now}
        if self.job is not None:
            if not self.job.done():return
            job,self.job=self.job,None
            key,requested=self.pending
            try:pixels,relief=job.result()
            except (OSError,ValueError,ImportError,subprocess.SubprocessError):
                self.retry[self.pending]=now+30.
            else:
                if key in wanted and requested==source:
                    slot=(key[0]//2)%3+3*((key[1]//2)%3)
                    self.resident[slot]=self.pending
                    result=slot,key,pixels,relief
        for key in wanted:
            identity=(key,source)
            if identity not in self.resident.values() and identity not in self.retry:
                self.pending=identity
                self.job=self.pool.submit(load_surface,key,field,source)
                break
        return result

    def close(self):
        self.pool.shutdown(wait=False,cancel_futures=True)


def run_image_worker(source,folder,*args):
    """Run only the standalone image worker in the Android map interpreter."""
    script=folder/source.name
    script.write_bytes(source.read_bytes())
    subprocess.run(['proot-distro','login','pocket-maps','--bind',str(folder),'--',
                    '/usr/bin/python3',str(script),*args,str(folder)],check=True,timeout=45)

if __name__=='__main__':
    folder=Path(sys.argv[2])
    if sys.argv[1]=='map':draw_map_patch(folder)
    elif sys.argv[1]=='relief':decode_relief(folder)
    elif sys.argv[1]=='patch':decode_aerial(folder,(1024,1024))
    elif sys.argv[1]=='aerial':decode_aerial(folder)
    else:convert(sys.argv[1],folder)
