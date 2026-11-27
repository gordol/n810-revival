"""Offline georeferenced outings using Mapzen Terrarium elevation tiles."""
from array import array
from concurrent.futures import ThreadPoolExecutor
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


# Overlapping 8 km exports keep the nearby surface detailed across tile changes.
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

def flight_relief(key,field):
    from data_paths import rainier_cache
    from pnw.scene import surface
    from geometry import HeightField,Vec
    from struct import Struct
    cache=rainier_cache()/'flight-imagery-v1'
    dest=cache/f'{key[0]}_{key[1]}.dem'
    try:data=dest.read_bytes()
    except FileNotFoundError:data=b''
    if len(data)!=129*129*2:
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            folder=Path(tmp)
            with urlopen(relief_url(key),timeout=8) as stream:raw=stream.read(1024**2+1)
            if len(raw)>1024**2:raise ValueError('Oversized elevation patch')
            (folder/'height.tif').write_bytes(raw)
            convert_local(folder,'relief',lambda:decode_relief(folder))
            data=(folder/'height').read_bytes()
            (folder/'height').replace(dest)
    values=array('h')
    values.frombytes(data)
    if sys.byteorder!='little':values.byteswap()
    x0,z0=(v*PATCH_STEP-PATCH_WIDTH/2 for v in key)
    if max(values)<400:return None
    heights=[]
    rows=[]
    vertex=Struct('=7f').pack
    step=PATCH_WIDTH/128
    mesh=array('f')
    for j in range(129):
        row=[]
        for i in range(129):
            x,z=x0+i*step,z0+j*step
            base=surface(field,x,z)
            # Keep authored shoreline structures and runways on their existing foundations.
            weight=max(0.,min(1.,(base-400.)/250.,min(i,j,128-i,128-j)/5.))
            y=base+weight*(values[j*129+i]-base)
            heights.append(y)
            row.append(vertex(x,y,z,.28,.39,.24,.219))
        rows.append(row)
        if j:
            a,b=rows
            mesh.frombytes(b''.join(v for i in range(128) for v in (a[i],b[i],a[i+1],a[i+1],b[i],b[i+1])))
            rows.pop(0)
    return HeightField(129,129,Vec(x0,0,z0),step,step,tuple(heights),'meters'),mesh

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
        return pixels,relief


class FlightImagery:
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.job=self.pending=self.loaded=None
        self.retry=0.

    def update(self,x,z,field):
        key=(round(x/PATCH_STEP),round(z/PATCH_STEP))
        if self.job is not None:
            if not self.job.done():return
            job,self.job=self.job,None
            try:pixels,relief=job.result()
            except (OSError,ValueError,ImportError,subprocess.SubprocessError):
                self.retry=time.monotonic()+30.
            else:
                if self.pending==key:
                    self.loaded=key
                    return key,pixels,relief
        if key!=self.loaded and time.monotonic()>=self.retry:
            self.pending=key
            self.job=self.pool.submit(flight_patch,key,field)

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
    if sys.argv[1]=='relief':decode_relief(folder)
    elif sys.argv[1]=='patch':decode_aerial(folder,(1024,1024))
    elif sys.argv[1]=='aerial':decode_aerial(folder)
    else:convert(sys.argv[1],folder)
