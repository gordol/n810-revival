"""Offline georeferenced outings using Mapzen Terrarium elevation tiles."""
from array import array
import market_visit
from concurrent.futures import ThreadPoolExecutor
import math
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from urllib.parse import urlencode
from urllib.request import urlopen
from urllib.error import URLError
import zlib

# Centre, zoom, source pixels per vertex, columns and rows.
GRIDS={'sound':(47.23,-122.18,9,2,241,289),'hoh':(47.861,-123.935,15,2,257,257)}
PLACES=(('Thun Field',47.104,-122.287),('Tacoma waterfront',47.266,-122.449),
        ('Tacoma Narrows Airport',47.268,-122.578),('Seattle waterfront',47.604,-122.339),
        ('Rainier',46.852,-121.760))
BAY=(47.295,-122.435)
OUTINGS={'Plane from Rainier':'plane','Plane from Thun Field':'thun',
         'Boat on Commencement Bay':'boat','Hoh Rain Forest walk':'hoh','Bainbridge ferry':'ferry','Seattle Great Wheel':'wheel',
         'Pike Place Market':'market','Fish counter':'fishshop','Space Needle':'needle'}

OUTINGS.update(market_visit.DESTINATIONS)

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

WHEEL=(47.6062,-122.3425)
# Seattle and Bainbridge landings and Eagle Harbor bends, OSM way 332476322.
FERRY=tuple(location('sound',*p) for p in (
    (47.6028952, -122.3398411),(47.6028572, -122.3408157),(47.6028536, -122.3411992),
    (47.6028717, -122.3417062),(47.6027487, -122.3567748),(47.6024883, -122.3667527),
    (47.6033274, -122.3921586),(47.6049478, -122.438078),(47.6068719, -122.4718523),
    (47.6073349, -122.4835253),(47.6076821, -122.4864006),(47.608391, -122.4891043),
    (47.609447, -122.4908209),(47.6106622, -122.4920011),(47.6131647, -122.4933958),
    (47.6160867, -122.4949622),(47.6176488, -122.4959064),(47.6194423, -122.4973655),
    (47.620339, -122.4990392),(47.6208887, -122.5012279),(47.6217448, -122.5069982),
    (47.6219853, -122.508332),(47.6221412, -122.5095054),
))
FERRY_LEGS=tuple((a,b,math.dist(a,b)) for a,b in zip(FERRY,FERRY[1:]))
CROSSING=sum(length for _,_,length in FERRY_LEGS)/45.
DOCK_TIME=15.

def ferry_stop(elapsed):
    t=elapsed%(2*(CROSSING+DOCK_TIME))
    if t<DOCK_TIME:return 'colman'
    if CROSSING+DOCK_TIME<=t<CROSSING+2*DOCK_TIME:return 'bainbridge'
    return None

def runway_geometry():
    # Threshold coordinates and widths from OurAirports runways.csv.
    for a,b,width in (((47.108898,-122.287003),(47.098918,-122.287278),18.29),
                      ((47.2747,-122.577004),(47.261135,-122.579335),30.48)):
        x,z=location('sound',*a)
        ex,ez=location('sound',*b)
        yield x,z,math.atan2(ex-x,ez-z),math.hypot(ex-x,ez-z),width

def ride_pose(outing,elapsed):
    if outing=='wheel':
        x,z=location('sound',*WHEEL)
        phase=elapsed*math.tau/100.
        return x,z+23*math.sin(phase),1.45,-.04,4+23*(1-math.cos(phase))
    phase=elapsed%(2*(CROSSING+DOCK_TIME))
    returning=phase>=CROSSING+DOCK_TIME
    t=phase-(CROSSING+DOCK_TIME) if returning else phase
    distance=max(0.,min(CROSSING,t-DOCK_TIME))
    along=45*(CROSSING-distance if returning else distance)
    for (x,z),(ex,ez),d in FERRY_LEGS:
        if along<=d:
            t=along/d
            return x+(ex-x)*t,z+(ez-z)*t,math.atan2(ex-x,ez-z)+math.pi*returning,.015,5.
        along-=d
    return *FERRY[-1],0.,0.,5.

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

def aerial_url():
    _,_,zoom,step,nx,nz=GRIDS['sound']
    cx,cy,_=layout('sound')
    world=40075016.68557849
    scale=world/(256*(1<<zoom))
    x=cx*scale-world/2
    y=world/2-cy*scale
    w=(nx-1)*step*scale/2
    h=(nz-1)*step*scale/2
    args={'bbox':','.join(map(str,(x-w,y-h,x+w,y+h))),'bboxSR':3857,
          'imageSR':3857,'size':','.join(map(str,IMAGE_SIZE)),'format':'jpg','f':'image'}
    return 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export?'+urlencode(args)

def decode_aerial(folder):
    from PIL import Image
    with Image.open(folder/'image.jpg') as im:
        if im.size!=IMAGE_SIZE:raise ValueError('Unexpected aerial extent')
        rgb=im.convert('RGB').transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        (folder/'rgb').write_bytes(rgb.tobytes())

def convert_local(folder,mode,convert_image):
    if os.environ.get('POCKET_TERMUX')=='1':
        script=folder/'pnw_outings.py'
        script.write_bytes(Path(__file__).read_bytes())
        subprocess.run(['proot-distro','login','pocket-maps','--bind',str(folder),'--',
                        '/usr/bin/python3',str(script),mode,str(folder)],check=True,timeout=45)
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

def build_world(outing):
    from geometry import Vec
    from summit_detail import RegionalTerrain
    region='hoh' if outing=='hoh' else 'sound'
    if outing in market_visit.FLOORS:return market_visit.indoor(outing)
    raw=elevations(region)
    _,_,_,_,nx,nz=GRIDS[region]
    _,_,d=layout(region)
    field=RegionalTerrain(nx,nz,Vec(-(nx//2)*d,0,-(nz//2)*d),d,d,tuple(max(0,v) for v in raw),'meters')
    mesh=array('f')
    aerial=sound_aerial() if region=='sound' else None
    rows=[]
    for j in range(nz):
        row=[]
        for i in range(nx):
            k=j*nx+i
            y=field.values[k]
            dx=(field.values[j*nx+min(nx-1,i+1)]-field.values[j*nx+max(0,i-1)])/(2*d)
            dz=(field.values[min(nz-1,j+1)*nx+i]-field.values[max(0,j-1)*nx+i])/(2*d)
            shade=max(.45,min(1.2,.88+.52*(dx-dz)))
            color=(.11,.32,.37) if raw[k]<=0 else (.88,.92,.95) if y>2400 else (.28,.39,.24)
            row.append((field.origin.x+i*d,y,field.origin.z+j*d,*(v*shade for v in color),.216 if aerial is not None and raw[k]>0 else .20 if raw[k]<=0 else .974 if region=='hoh' else .0))
        rows.append(row)
    # Keep 384-vertex culling batches spatially compact in both dimensions.
    for z0 in range(0,nz-1,8):
        for x0 in range(0,nx-1,8):
            for j in range(z0,min(nz-1,z0+8)):
                a,b=rows[j:j+2]
                for i in range(x0,min(nx-1,x0+8)):
                    for v in (a[i],b[i],a[i+1],a[i+1],b[i],b[i+1]):mesh.extend(v)
    if region=='sound':
        from rainier_pixels import surface
        def quad(points,color,material=0.):
            for i in (0,1,2,0,2,3):mesh.extend((*points[i],*color,material))
        def box(x,z,y,width,depth,height,color,material=0.,rotation=None):
            base=[(x+sx*width/2,y,z+sz*depth/2) for sx,sz in ((-1,-1),(1,-1),(1,1),(-1,1))]
            if rotation:
                c,s=rotation
                base=[(x+c*(px-x)-s*(pz-z),y,z+s*(px-x)+c*(pz-z)) for px,_,pz in base]
            top=[(px,y+height,pz) for px,_,pz in base]
            quad(top,color)
            for i in range(4):
                j=(i+1)%4
                shade=(.78,.91,.84,.69)[i]
                quad((base[i],base[j],top[j],top[i]),tuple(c*shade for c in color),material)
        # Game scenery at named locations. Runway paint follows the sampled terrain.
        for x,z,a,length,width in runway_geometry():
            def strip(width,start,end,color,lift):
                for side,t in ((-1,start),(1,start),(-1,end),(-1,end),(1,start),(1,end)):
                    xx=x+t*math.sin(a)+side*width*math.cos(a)
                    zz=z+t*math.cos(a)-side*width*math.sin(a)
                    mesh.extend((xx,surface(field,xx,zz)+lift,zz,*color,0.))
            for t in range(0,math.ceil(length),25):
                strip(width/2,t,min(length,t+25),(.19,.20,.21),.14)
                if t%50==0:strip(.65,t,min(length,t+15),(.94,.93,.80),.18)
        for name,lat,lon in (PLACES[1],):
            rng=random.Random(name)
            x,z=location(region,lat,lon)
            for col in range(10):
                for row in range(18):
                    xx=x+col*96+rng.uniform(-12,12)
                    zz=z+(row-8)*106+rng.uniform(-15,15)
                    y=surface(field,xx,zz)
                    if y<4:continue
                    width,depth=rng.uniform(30,63),rng.uniform(34,76)
                    tower=math.exp(-((col-4)**2+(row-9)**2)/15)
                    height=rng.uniform(14,48)+tower*rng.uniform(40,200)
                    color=rng.choice(((.41,.51,.56),(.47,.49,.51),(.59,.47,.40),(.44,.57,.63)))
                    box(xx,zz,y-2,width,depth,height,color,.228)
                    box(xx,zz,y+height-2,width*.65,depth*.66,rng.uniform(2,10),color,.228)
        # Long timber piers and gabled sheds step out into Elliott Bay.
        for lat,lon,length in ((47.6056,-122.3412,108),(47.6065,-122.3418,122),
                               (47.6075,-122.3423,112),(47.6093,-122.3441,94)):
            x,z=location(region,lat,lon)
            deck=surface(field,x,z)+2.
            box(x,z,deck-1.2,length,29,1.2,(.42,.34,.25))
            for u in range(-int(length/2)+3,int(length/2),7):
                for side in (-1,1):
                    box(x+u,z+side*13,deck-11,.7,.7,10.,(.22,.22,.17))
            box(x+5,z,deck,length*.79,19.,6.,(.64,.42,.32),.228)
            for side in (-1,1):
                eave=z+side*10.
                left=x+5-length*.41
                right=x+5+length*.41
                quad(((left,deck+6,eave),(right,deck+6,eave),(right,deck+10,z),
                      (left,deck+10,z)),(.33,.38,.39))
        x,z=location('sound',*WHEEL)
        base=field.height(x,z)+27
        # Two rims, axle braces and radial spokes facing Elliott Bay.
        def beam(a,b,width,color):
            dx,dy,dz=(v-u for u,v in zip(a,b))
            length=math.hypot(dy,dz) or 1.
            uy,uz=width*dz/length,-width*dy/length
            for point,side in ((a,-1),(a,1),(b,-1),(b,-1),(a,1),(b,1)):
                mesh.extend((point[0],point[1]+side*uy,point[2]+side*uz,*color,0.))
        for side in (-1,1):
            xx=x+side*2.
            for j in range(48):
                a=j*math.tau/48;b=(j+1)*math.tau/48
                tip=(xx,base+24*math.cos(a),z+24*math.sin(a))
                beam(tip,(xx,base+24*math.cos(b),z+24*math.sin(b)),.45,(.89,.89,.84))
                if j%2==0:beam((xx,base,z),tip,.13,(.70,.76,.78))
            for foot in (-1,1):beam((xx,base-26,z+foot*10),(xx,base,z),.65,(.42,.48,.51))
        for j in range(32):
            a=j*math.tau/32
            zz=z+24*math.sin(a)
            y=base+24*math.cos(a)-2.4
            box(x,zz,y,3.8,2.3,1.15,(.80,.83,.81))
            box(x,zz,y+1.15,3.5,2.,1.05,(.24,.38,.45))
            box(x,zz,y+2.2,3.8,2.3,.18,(.84,.85,.80))
        import pike_market
        from seattle_places import arcade_origin,buildings,space_needle,streets
        def ground(x,z):return surface(field,x,z)
        pike_market.build(arcade_origin(),ground,quad)
        streets(ground,quad)
        buildings(ground,quad)
        space_needle(ground,quad)
        market_visit.outdoor(ground,quad,box)
    else:
        from forest_floor import broadleaf_clump,nurse_log,fern
        rng=random.Random(47861)
        def face(a,b,c,color,material=0.):
            materials=material if isinstance(material,tuple) else (material,)*3
            for v,m in zip((a,b,c),materials):
                mesh.extend((v.x,v.y,v.z,*(k/255 for k in color),m))
        # Clumps within the opening sightline give the rainforest a middle
        # storey. Keep an irregular gap through the centre for the walker.
        for _ in range(85):
            z=rng.uniform(-15,40)
            x=rng.choice((-1,1))*rng.uniform(1.8,18)+1.15*math.sin(z*.22)
            y=field.height(x,z)
            if rng.random()<.67:fern(x,z,y,rng.uniform(.7,1.55),face,rng,compact=True)
            else:broadleaf_clump(x,y,z,rng.uniform(.55,1.1),(73,113,57),face,rng)
        for _ in range(40):
            x,z=rng.uniform(-80,80),rng.uniform(-80,80)
            a=rng.random()*math.tau
            nurse_log(x,z,math.sin(a),math.cos(a),field.height,face,rng)
            for _ in range(3):
                px,pz=x+rng.uniform(-2,2),z+rng.uniform(-2,2)
                fern(px,pz,field.height(px,pz),rng.uniform(.6,1.4),face,rng,compact=True)
    count=len(mesh)//7
    return field,Vec(0,0,0),mesh,count,array('I',[0]),(),count,aerial

if __name__=='__main__':
    folder=Path(sys.argv[2])
    if sys.argv[1]=='aerial':decode_aerial(folder)
    else:convert(sys.argv[1],folder)
