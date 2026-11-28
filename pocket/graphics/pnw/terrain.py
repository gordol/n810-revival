"""Offline georeferenced outings using Mapzen Terrarium elevation tiles."""
from array import array
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import shutil
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
        convert(region,folder)
        result=read(folder/'grid')
        (folder/'grid').replace(dest)
        return result

# Tile keys use the original cache coordinate system (two steps per tile).
PATCH_WIDTH=8192
PATCH_STEP=4096
PATCH_LIMIT=1024**3

# A 5:6 export matches the 240 by 288 Sound grid cells.
IMAGE_SIZE=(1280,1536)

def aerial_url(patch=None,pixels=1024,width=PATCH_WIDTH):
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
        w=h=width*projection/2
        size=(pixels,pixels)
    args={'bbox':','.join(map(str,(x-w,y-h,x+w,y+h))),'bboxSR':3857,
          'imageSR':3857,'size':','.join(map(str,size)),'format':'jpg','f':'image'}
    return 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export?'+urlencode(args)

def decode_aerial(folder,size=IMAGE_SIZE):
    from PIL import Image
    with Image.open(folder/'image.jpg') as im:
        if im.size!=size:raise ValueError('Unexpected aerial extent')
        rgb=im.convert('RGB').transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        (folder/'rgb').write_bytes(rgb.tobytes())

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
            decode_aerial(folder)
            rgb=read(folder/'rgb')
            (folder/'rgb').replace(dest)
            return rgb
    except (OSError,ValueError,URLError,subprocess.SubprocessError):return None


def relief_url(key,width=PATCH_WIDTH):
    from urllib.parse import parse_qs,urlsplit
    args=parse_qs(urlsplit(aerial_url(key,width=width)).query)
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

def flight_relief(key,field,*,local_only=False,width=PATCH_WIDTH):
    from data_paths import rainier_cache
    cache=rainier_cache()/'flight-imagery-v1'
    prefix='' if width==PATCH_WIDTH else f'{width}-'
    dest=cache/f'{prefix}{key[0]}_{key[1]}.dem'
    try:data=dest.read_bytes()
    except FileNotFoundError:data=b''
    if len(data)!=129*129*2:
        if local_only:return None
        cache.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            folder=Path(tmp)
            with urlopen(relief_url(key,width),timeout=8) as stream:raw=stream.read(1024**2+1)
            if len(raw)>1024**2:raise ValueError('Oversized elevation patch')
            (folder/'height.tif').write_bytes(raw)
            decode_relief(folder)
            data=(folder/'height').read_bytes()
            (folder/'height').replace(dest)
            trim_patch_cache(cache)
    values=array('h')
    values.frombytes(data)
    if sys.byteorder!='little':values.byteswap()
    return relief_mesh(key,field,values,width)

def relief_mesh(key,field,values=None,width=PATCH_WIDTH):
    from pnw.hiking import bounds
    from pnw.scene import surface
    from geometry import HeightField,Vec
    from struct import Struct
    west,east,south,north=bounds(field)
    x0,z0=(v*PATCH_STEP-width/2 for v in key)
    inside=west<=x0 and x0+width<=east and south<=z0 and z0+width<=north
    if not inside and values is None:
        raise ValueError('Elevation is unavailable beyond the prepared map')
    if inside:
        # Use the source DEM triangles where roads are baked onto that surface.
        # An independently sampled regular grid cuts across its ridges and valleys.
        ix=max(0,math.floor((x0-west)/field.dx))
        iz=max(0,math.floor((z0-south)/field.dz))
        ex=min(field.nx-1,math.ceil((x0+width-west)/field.dx))
        ez=min(field.nz-1,math.ceil((z0+width-south)/field.dz))
        samples=[field.values[j*field.nx+i] for j in range(iz,ez+1) for i in range(ix,ex+1)]
        if max(samples)<=400 and (ex-ix)*(ez-iz)<=128*128:
            vertex=Struct('=7f').pack
            rows=[[vertex(west+i*field.dx,field.values[j*field.nx+i],south+j*field.dz,.28,.39,.24,.219)
                   for i in range(ix,ex+1)] for j in range(iz,ez+1)]
            mesh=array('f')
            for a,b in zip(rows,rows[1:]):
                mesh.frombytes(b''.join(v for i in range(ex-ix) for v in (a[i],b[i],a[i+1],a[i+1],b[i],b[i+1])))
            return HeightField(ex-ix+1,ez-iz+1,Vec(west+ix*field.dx,0,south+iz*field.dz),
                               field.dx,field.dz,tuple(samples),'meters'),mesh
    cells=128 if values is not None and (width>PATCH_WIDTH or not inside or max(values)>=400) else 32
    heights=[]
    rows=[]
    vertex=Struct('=7f').pack
    step=width/cells
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

def flight_patch(key,field=None,pixels=1024,width=PATCH_WIDTH):
    from data_paths import rainier_cache
    cache=rainier_cache()/'flight-imagery-v1'
    cache.mkdir(parents=True,exist_ok=True)
    suffix='' if pixels==1024 else f'-{pixels}'
    prefix='' if width==PATCH_WIDTH else f'{width}-'
    target=cache/f'{prefix}{key[0]}_{key[1]}{suffix}.jpg'
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
        folder=Path(tmp)
        image=folder/'image.jpg'
        cached=True
        try:image.write_bytes(target.read_bytes())
        except FileNotFoundError:
            cached=False
            with urlopen(aerial_url(key,pixels,width),timeout=8) as stream:data=stream.read(4*1024**2+1)
            if len(data)>4*1024**2:raise ValueError('Oversized aerial patch')
            image.write_bytes(data)
        try:decode_aerial(folder,(pixels,pixels))
        except (OSError,ValueError,ImportError,subprocess.SubprocessError):
            target.unlink(missing_ok=True)
            raise
        rgb=(folder/'rgb').read_bytes()
        if len(rgb)!=pixels*pixels*3:raise ValueError('Incomplete aerial patch')
        if cached and target.exists():os.utime(target,None)
        else:image.replace(target)
        relief=None
        if field is not None and width<PATCH_WIDTH:
            try:relief=relief_mesh(key,field,width=width)
            except ValueError:pass  # Outside the overview, 3DEP supplies the surface.
            if relief is not None and max(relief[0].values)>400:relief=None
        if field is not None and relief is None:
            try:relief=flight_relief(key,field,width=width)
            except (OSError,ValueError,ImportError,subprocess.SubprocessError):pass
        trim_patch_cache(cache)
        if field is not None and relief is None:relief=relief_mesh(key,field,width=width)
        return rgb,relief


def trim_patch_cache(cache):
    files=[]
    for path in cache.iterdir():
        if path.suffix not in ('.jpg','.dem'):continue
        try:stat=path.stat()
        except FileNotFoundError:continue
        files.append((stat.st_mtime,stat.st_size,path))
    total=sum(size for _,size,_ in files)
    limit=min(PATCH_LIMIT,(total+shutil.disk_usage(cache).free)//10)
    for _,size,path in sorted(files):
        if total<=limit:break
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
    """Paint water and street features over the relief image."""
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
        draw_map_patch(folder)
        return (folder/'rgb').read_bytes(),relief

def load_surface(key,field,source,pixels=1024):
    if source!='Drawn terrain':
        try:return flight_patch(key,field,pixels)
        except (OSError,ValueError,ImportError,subprocess.SubprocessError):
            from data_paths import rainier_cache
            cache=rainier_cache()/'flight-imagery-v1'
            for size in (1024,512,2048):
                suffix='' if size==1024 else f'-{size}'
                if size!=pixels and (cache/f'{key[0]}_{key[1]}{suffix}.jpg').is_file():
                    try:return flight_patch(key,field,size)
                    except (OSError,ValueError,ImportError,subprocess.SubprocessError):pass
    return map_patch(key,field,fetch_missing=source!='Drawn terrain')


# Wide tiles use the same metre coordinates and image/DEM registration as local tiles.
HORIZON_WIDTH=4*PATCH_WIDTH
LANDMARKS=tuple(tuple(2*round(v/PATCH_WIDTH) for v in location('sound',lat,lon))
                for lat,lon in ((46.852,-121.760),(47.603,-122.382),(47.266,-122.449)))

def available_memory():
    """Available host memory in bytes, capped by the remaining cgroup allowance."""
    try:
        if sys.platform=='darwin':
            stats=subprocess.check_output(['/usr/bin/vm_stat'],text=True,timeout=2)
            page=int(stats.split('page size of ')[1].split()[0])
            rows=dict(line.rstrip('.').split(':') for line in stats.splitlines()[1:] if ':' in line)
            return page*sum(int(rows[k]) for k in ('Pages free','Pages inactive','Pages speculative'))
        info=Path('/proc/meminfo').read_text()
        free=int(info.split('MemAvailable:')[1].split()[0])*1024
        group=Path('/sys/fs/cgroup')
        try:
            limit=int((group/'memory.max').read_text())
            free=min(free,max(0,limit-int((group/'memory.current').read_text())))
        except (OSError,ValueError):pass
        return free
    except (OSError,IndexError,KeyError,ValueError,subprocess.SubprocessError):return None

class FlightHorizon:
    """One independent worker keeps the distant scenery from queuing behind local detail."""
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.job=self.pending=None
        self.resident={}
        self.retry={}
        self.settled=None
        self.next_sample=0.
        self.auto=90

    def update(self,x,z,field,setting,near_ground=False):
        now=time.monotonic()
        if setting=='Auto' and now>=self.next_sample:
            free=available_memory()
            self.auto=90
            if free is not None and free<1024**3:
                self.auto=0 if free<512*1024**2 else 50
            self.next_sample=now+30.
        radius={'Street':0,'Local':0,'50 km':50,'80 km':80,'90 km':90,'120 km':120}.get(setting,self.auto)
        if radius in (0,50,80):
            rings={0:0,50:1,80:2}[radius]
            cx,cz=(round(v/HORIZON_WIDTH) for v in (x,z))
            west,east,south,north=cx-rings,cx+rings,cz-rings,cz+rings
        else:
            metres=radius*1000
            west,east,south,north=(math.floor(v/HORIZON_WIDTH+.5)
                                   for v in (x-metres,x+metres,z-metres,z+metres))
        detail=setting=='Street' or near_ground and (setting!='Auto' or self.auto!=0)
        street_key=tuple(round(v/256)/16 for v in (x,z)) if detail else None
        neighborhood=(west,east,south,north,radius,street_key,tuple(round(v/1024) for v in (x,z)) if street_key else None)
        if self.settled==neighborhood:return [],None
        self.settled=None
        wanted={} if street_key is None else {
            110:(street_key,512),
            109:(tuple(round(v/1024)/4 for v in (x,z)),1024),
        }
        if radius:
            # Slots 25..27 are always reserved for detailed landmark scenery.
            for i,key in enumerate(LANDMARKS):wanted[25+i]=(key,PATCH_WIDTH)
            grid=sorted(((i,j) for i in range(west,east+1) for j in range(south,north+1)),
                        key=lambda ij:(ij[0]*HORIZON_WIDTH-x)**2+(ij[1]*HORIZON_WIDTH-z)**2)
            for i,j in grid:wanted[28+i%9+9*(j%9)]=((8*i,8*j),HORIZON_WIDTH)
        removed=[slot for slot in self.resident if slot not in wanted]
        for slot in removed:del self.resident[slot]
        self.retry={item:t for item,t in self.retry.items() if t>now and wanted.get(item[0])==item[1]}
        patch=None
        if self.job and self.job.done():
            slot,entry=self.pending
            try:rgb,relief=self.job.result()
            except (ValueError,OSError,ImportError,subprocess.SubprocessError):
                self.retry[self.pending]=now+60.
            else:
                if wanted.get(slot)==entry:
                    self.resident[slot]=entry
                    patch=(slot,entry[0],rgb,relief)
            self.job=None
        if self.job is None:
            for slot,entry in wanted.items():
                if self.resident.get(slot)==entry or (slot,entry) in self.retry:continue
                self.pending=slot,entry
                self.job=self.pool.submit(flight_patch,entry[0],field,2048 if slot>=109 else 1024,entry[1])
                break
        if not self.job and not self.retry:self.settled=neighborhood
        return removed,patch

    def close(self):
        self.pool.shutdown(wait=False,cancel_futures=True)

class FlightImagery:
    def __init__(self):
        self.pool=ThreadPoolExecutor(max_workers=2)
        self.jobs={}
        self.complete=None
        self.resident={}
        self.retry={}

    def update(self,x,z,field,source='Aerial'):
        cx,cz=(2*round(v/PATCH_WIDTH) for v in (x,z))
        neighborhood=(cx,cz,source)
        if self.complete==neighborhood:return
        self.complete=None
        wanted={}
        for dx in range(-4,5,2):
            for dz in range(-4,5,2):
                ring=max(abs(dx),abs(dz))//2
                size=(2048,1024,512)[ring] if source=='Aerial' else 1024
                wanted[cx+dx,cz+dz]=(source,size)
        now=time.monotonic()
        self.retry={item:t for item,t in self.retry.items() if t>now and wanted.get(item[0])==item[1:]}
        result=None
        for item,job in list(self.jobs.items()):
            if not job.done():continue
            del self.jobs[item]
            key,requested,size=item
            if key not in wanted or wanted[key][0]!=requested:continue
            slot=(key[0]//2)%5+5*((key[1]//2)%5)
            if self.resident.get(slot)==(key,*wanted[key]):continue
            try:rgb,relief=job.result()
            except (OSError,ValueError,ImportError,subprocess.SubprocessError):
                self.retry[item]=now+30.
                continue
            self.resident[slot]=item
            result=slot,key,rgb,relief
            break  # Bound GL upload work to one patch per frame.
        if len(self.jobs)<2:
            for key in sorted(wanted,key=lambda k:(k[0]*PATCH_STEP-x)**2+(k[1]*PATCH_STEP-z)**2):
                item=(key,*wanted[key])
                if item in self.resident.values() or item in self.jobs or item in self.retry:continue
                self.jobs[item]=self.pool.submit(load_surface,key,field,*wanted[key])
                if len(self.jobs)==2:break
        if not self.jobs and not self.retry:self.complete=neighborhood
        return result

    def close(self):
        self.pool.shutdown(wait=False,cancel_futures=True)
