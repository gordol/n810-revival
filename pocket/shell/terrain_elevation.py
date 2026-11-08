"""Sample the existing prepared USGS 3DEP elevation grid along a geographic path."""
from array import array
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import sys
import zlib
from path_profile import profile,EARTH_M


@lru_cache(maxsize=1)
def grid():
    from data_paths import data_root
    directory=data_root()
    if not (directory/'tahoma-3dep.json').is_file():directory=Path(__file__).with_name('data')
    metadata=json.loads((directory/'tahoma-3dep.json').read_text())
    raw=(directory/'tahoma-3dep.i16.zlib').read_bytes()
    if len(raw)>1024*1024 or hashlib.sha256(raw).hexdigest()!=metadata['sha256']:
        raise ValueError('USGS elevation grid failed its stored integrity check')
    nx,nz=metadata['nx'],metadata['nz']
    if type(nx) is not int or type(nz) is not int or not 2<=nx<=1024 or not 2<=nz<=1024 or metadata['units']!='meters':
        raise ValueError('Unsupported elevation grid')
    decoder=zlib.decompressobj();decoded=decoder.decompress(raw,nx*nz*2+1)
    if len(decoded)!=nx*nz*2 or not decoder.eof or decoder.unused_data:
        raise ValueError('USGS elevation grid length differs from metadata')
    values=array('h');values.frombytes(decoded)
    if sys.byteorder!='little':values.byteswap()
    return metadata,values


def elevation(latitude,longitude):
    metadata,values=grid()
    x=(longitude-metadata['longitude_first'])/metadata['longitude_step']
    y=(latitude-metadata['latitude_first'])/metadata['latitude_step']
    nx,nz=metadata['nx'],metadata['nz']
    if not 0<=x<=nx-1 or not 0<=y<=nz-1:return None
    ix=min(nx-2,int(x));iy=min(nz-2,int(y));fx=x-ix;fy=y-iy
    return ((1-fx)*(1-fy)*values[iy*nx+ix]+fx*(1-fy)*values[iy*nx+ix+1]
            +(1-fx)*fy*values[(iy+1)*nx+ix]+fx*fy*values[(iy+1)*nx+ix+1])


@lru_cache(maxsize=1)
def regional_grid():
    from data_paths import data_root
    directory=data_root()
    if not (directory/'pnw-etopo1.json').is_file():directory=Path(__file__).with_name('data')
    metadata=json.loads((directory/'pnw-etopo1.json').read_text())
    raw=(directory/'pnw-etopo1.i16.zlib').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=metadata['sha256']:raise ValueError('Regional elevation grid integrity check failed')
    expected=metadata['nx']*metadata['nz']*2
    if not 0<expected<=1024*1024:raise ValueError('Regional elevation grid exceeds bounds')
    decoder=zlib.decompressobj();decoded=decoder.decompress(raw,expected+1)
    if len(decoded)!=expected or not decoder.eof or decoder.unused_data:raise ValueError('Invalid regional grid length')
    values=array('h');values.frombytes(decoded)
    if sys.byteorder!='little':values.byteswap()
    return metadata,values


@lru_cache(maxsize=2)
def tiled_index(pack='elevation-western-wa'):
    if pack not in ('elevation-western-wa','elevation-lakewood'):raise ValueError('Unknown elevation pack')
    path=Path(__file__).with_name('data')/pack/'index.json'
    if not path.is_file():return None
    with path.open('rb') as source:raw=source.read(1024*1024+1)
    if len(raw)>1024*1024:raise ValueError('Elevation tile index exceeds bounds')
    metadata=json.loads(raw)
    if metadata.get('tile_size')!=256 or metadata.get('units')!='meters' or not 2<=metadata['nx']<=16384 or not 2<=metadata['nz']<=16384:
        raise ValueError('Unsupported tiled elevation format')
    return path.parent,metadata


@lru_cache(maxsize=4)
def elevation_tile(tx,ty,pack='elevation-western-wa'):
    directory,metadata=tiled_index(pack);item=metadata['tiles'][f'{tx},{ty}'];name=f'{tx}-{ty}.i16.zlib'
    if item['file']!=name or not 1<=item['width']<=256 or not 1<=item['height']<=256:
        raise ValueError('Invalid elevation tile descriptor')
    with (directory/name).open('rb') as source:raw=source.read(256*256*2+4097)
    if len(raw)>256*256*2+4096 or hashlib.sha256(raw).hexdigest()!=item['sha256']:
        raise ValueError('Elevation tile integrity check failed')
    expected=item['width']*item['height']*2
    decoder=zlib.decompressobj();decoded=decoder.decompress(raw,expected+1)
    if len(decoded)!=expected or not decoder.eof or decoder.unused_data:raise ValueError('Elevation tile length mismatch')
    values=array('h');values.frombytes(decoded)
    if sys.byteorder!='little':values.byteswap()
    return values,item['width']


def _sample(metadata,latitude,longitude,get):
    x=(longitude-metadata['longitude_first'])/metadata['longitude_step']
    y=(latitude-metadata['latitude_first'])/metadata['latitude_step']
    if not 0<=x<=metadata['nx']-1 or not 0<=y<=metadata['nz']-1:return None
    ix=min(metadata['nx']-2,int(x));iy=min(metadata['nz']-2,int(y));fx=x-ix;fy=y-iy
    values=(get(ix,iy),get(ix+1,iy),get(ix,iy+1),get(ix+1,iy+1))
    if metadata.get('nodata') in values:return None
    return values[0]*(1-fx)*(1-fy)+values[1]*fx*(1-fy)+values[2]*(1-fx)*fy+values[3]*fx*fy


def sample_elevation(latitude,longitude):
    from local_elevation import sample
    value,metadata=sample(latitude,longitude)
    if value is not None:return value,metadata
    for pack in ('elevation-lakewood','elevation-western-wa'):
        tiled=tiled_index(pack)
        if not tiled:continue
        metadata=tiled[1]
        def get(x,y):
            values,width=elevation_tile(x//256,y//256,pack)
            return values[(y%256)*width+x%256]
        value=_sample(metadata,latitude,longitude,get)
        if value is not None:return value,metadata
    value=elevation(latitude,longitude)
    if value is not None:return value,grid()[0]
    metadata,values=regional_grid()
    value=_sample(metadata,latitude,longitude,lambda x,y:values[y*metadata['nx']+x])
    return value,metadata


def terrain_upper_bound(a,b):
    """Bound a spherical arc using maxima, including interpolation neighbours."""
    tiled=tiled_index()
    if not tiled or 'maximum_bounds' not in tiled[1]:return None
    m=tiled[1];bounds=m['maximum_bounds']
    la,lo=map(math.radians,a);lb,lob=map(math.radians,b)
    angle=2*math.asin(min(1,math.sqrt(math.sin((lb-la)/2)**2+math.cos(la)*math.cos(lb)*math.sin((lob-lo)/2)**2)))
    # A circle about a containing the entire shortest arc is conservative.
    south=math.degrees(la-angle);north=math.degrees(la+angle)
    if abs(la)+angle>=math.pi/2:return None
    span=math.degrees(math.asin(min(1,math.sin(angle)/math.cos(la))))
    west=a[1]-span;east=a[1]+span
    from local_elevation import catalogue
    for path,fm in catalogue():
        if '-guarded' not in path.parent.name:continue
        ex=fm['extent']
        if not (east<ex['xmin'] or west>ex['xmax'] or north<ex['ymin'] or south>ex['ymax']):return None
    fine=tiled_index('elevation-lakewood')
    if fine:
        fm=fine[1];ex=fm['extent']
        intersects=not (east<ex['xmin'] or west>ex['xmax'] or north<ex['ymin'] or south>ex['ymax'])
        if intersects:
            if west>=ex['xmin'] and east<=ex['xmax'] and south>=ex['ymin'] and north<=ex['ymax']:
                m=fm;bounds=m['maximum_bounds']
            else:return None
    x0=math.floor((west-m['longitude_first'])/m['longitude_step'])-1
    x1=math.ceil((east-m['longitude_first'])/m['longitude_step'])+1
    y0=math.floor((south-m['latitude_first'])/m['latitude_step'])-1
    y1=math.ceil((north-m['latitude_first'])/m['latitude_step'])+1
    if x0<0 or y0<0 or x1>=m['nx'] or y1>=m['nz']:return None
    size=bounds['block_size'];values=bounds['values'];nx=bounds['nx'];highest=-32768
    for y in range(y0//size,y1//size+1):
        row=values[y*nx+x0//size:y*nx+x1//size+1]
        if bounds['unknown'] in row:return None
        highest=max(highest,max(row))
    return highest


def coordinate(text):
    try:latitude,longitude=map(float,text.split(','))
    except (ValueError,AttributeError):raise ValueError('Use latitude,longitude in decimal degrees')
    if not math.isfinite(latitude) or not math.isfinite(longitude) or not -85<=latitude<=85 or not -180<=longitude<=180:
        raise ValueError('Coordinates outside supported range')
    return latitude,longitude


def calculate(start,end,*,frequency_mhz=144.39,tx_height_m=2,rx_height_m=10,k=4/3,count=257):
    if type(count) is not int or not 3<=count<=4097:raise ValueError('Invalid path sample count')
    a=coordinate(start);b=coordinate(end)
    lat1,lon1,lat2,lon2=map(math.radians,(*a,*b))
    hav=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    angle=2*math.asin(math.sqrt(min(1,max(0,hav))))
    distance=angle*EARTH_M
    if not 1<=distance<=200000:raise ValueError('Choose distinct endpoints between 1 m and 200 km apart')
    samples=[];locations=[];sources={};source_counts={}
    def location(fraction):
        p=math.sin((1-fraction)*angle)/math.sin(angle);q=math.sin(fraction*angle)/math.sin(angle)
        x=p*math.cos(lat1)*math.cos(lon1)+q*math.cos(lat2)*math.cos(lon2)
        y=p*math.cos(lat1)*math.sin(lon1)+q*math.cos(lat2)*math.sin(lon2)
        z=p*math.sin(lat1)+q*math.sin(lat2)
        lat=math.degrees(math.atan2(z,math.hypot(x,y)));lon=math.degrees(math.atan2(y,x))
        return lat,lon
    first,_=sample_elevation(*a);last,_=sample_elevation(*b)
    adaptive=None
    if first is not None and last is not None and frequency_mhz>0 and k>0:
        from terrain_adaptive import fractions
        points,adaptive=fractions(distance,first+tx_height_m,last+rx_height_m,frequency_mhz,k,location,terrain_upper_bound,
                                  max_depth=max(1,int(math.log2(count-1))-1))
    else:points=[i/(count-1) for i in range(count)]
    for fraction in points:
        lat,lon=location(fraction)
        height,metadata=sample_elevation(lat,lon)
        if height is not None:
            identity=metadata.get('catalogue_id',metadata['source']);sources[identity]=metadata
            source_counts[identity]=source_counts.get(identity,0)+1
        samples.append((distance*fraction,height));locations.append((lat,lon))
    if samples[0][1] is None or samples[-1][1] is None:
        raise ValueError('Endpoint outside installed PNW elevations (43–52 N, 128–116 W). No synthetic fallback.')
    result=profile(samples,frequency_mhz=frequency_mhz,tx_height_m=tx_height_m,rx_height_m=rx_height_m,k=k)
    spacing=max(EARTH_M*math.radians(m['latitude_step']) for m in sources.values())
    identities=[m.get('sha256') or hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest() for m in sources.values()]
    result['adaptive_sampling']=adaptive
    result['elevation_sources']=[dict(source=m['source'],spacing_m=abs(EARTH_M*math.radians(m['latitude_step'])),samples=source_counts[key]) for key,m in sources.items()]
    result['finest_grid_spacing_north_m']=min(row['spacing_m'] for row in result['elevation_sources'])
    result.update(source=' + '.join(dict.fromkeys(m['source'] for m in sources.values())),source_accessed=', '.join(dict.fromkeys(m['accessed'] for m in sources.values())),dem_sha256=identities[0] if len(identities)==1 else identities,
                  native_grid_spacing_north_m=spacing,coarse=spacing>500,start=a,end=b,sample_coordinates=locations,
                  interpolation='Adaptive clearance sampling with conservative DEM maxima; graph joins sampled points and simplifies cleared valleys; DEM resolution limits still apply')
    return result


def classify_path(start,end,*,frequency_mhz=144.39,tx_height_m=2,rx_height_m=10,k=4/3):
    """Viewshed classification without building graph rows; stop at a known block.

    Sample spacing is at most 50 m up to the supported 200 km path length.
    A known obstruction also obstructs the Fresnel zone, so later samples cannot
    change that classification. Unknown terrain never establishes clearance.
    """
    from path_profile import finite,LIGHT_M_S
    frequency=finite(frequency_mhz,'Frequency');tx=finite(tx_height_m,'TX height');rx=finite(rx_height_m,'RX height')
    if not 0<frequency<=100000 or not 0<=tx<=10000 or not 0<=rx<=10000 or not .1<=k<=10:raise ValueError('Invalid path settings')
    a=coordinate(start);b=coordinate(end)
    lat1,lon1,lat2,lon2=map(math.radians,(*a,*b))
    hav=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    angle=2*math.asin(math.sqrt(min(1,max(0,hav))));distance=angle*EARTH_M
    if not 1<=distance<=200000:raise ValueError('Path outside supported length')
    first,m1=sample_elevation(*a);last,m2=sample_elevation(*b)
    if first is None or last is None:return dict(los='unknown',fresnel='unknown',samples=2,unknown_samples=sum(value is None for value in (first,last)))
    coarse=sum(EARTH_M*math.radians(abs(m['latitude_step']))>500 for m in (m1,m2))
    if coarse:
        return dict(los='unknown',fresnel='unknown',samples=2,unknown_samples=coarse)
    resolution=min(abs(m2['latitude_step'])*111194.9,abs(m2['longitude_step'])*111194.9*math.cos(math.radians(b[0])))
    origin=first+tx;destination=last+rx;wavelength=LIGHT_M_S/(frequency*1e6)
    sine=math.sin(angle);unknown_samples=0;fresnel_blocked=False
    def step(metadata,lat):
        spacing=min(abs(metadata['latitude_step'])*111194.9,abs(metadata['longitude_step'])*111194.9*math.cos(math.radians(lat)))
        return max(2,min(50,spacing/2))
    d=min(distance/2,step(m1,a[0]));i=0
    c1,s1,c2,s2=math.cos(lat1),math.sin(lat1),math.cos(lat2),math.sin(lat2)
    x1,y1=c1*math.cos(lon1),c1*math.sin(lon1);x2,y2=c2*math.cos(lon2),c2*math.sin(lon2)
    while d<distance:
        i+=1;f=d/distance;p=math.sin((1-f)*angle)/sine;q=math.sin(f*angle)/sine
        x=p*x1+q*x2;y=p*y1+q*y2;z=p*s1+q*s2
        lat=math.degrees(math.atan2(z,math.hypot(x,y)));lon=math.degrees(math.atan2(y,x))
        height,metadata=sample_elevation(lat,lon)
        if height is None or EARTH_M*math.radians(abs(metadata['latitude_step']))>500:
            unknown_samples+=1;d+=50;continue
        d=distance*f;product=d*(distance-d)
        clearance=origin+(destination-origin)*f-height-product/(2*k*EARTH_M)
        if clearance<0:return dict(los='blocked',fresnel='obstructed',samples=i+2,resolution_m=resolution,unknown_samples=unknown_samples)
        if clearance<.6*math.sqrt(wavelength*product/distance):fresnel_blocked=True
        d+=step(metadata,lat)
    return dict(los='unknown' if unknown_samples else 'clear',fresnel='obstructed' if fresnel_blocked else 'unknown' if unknown_samples else 'clear',samples=i+2,resolution_m=resolution,unknown_samples=unknown_samples)
