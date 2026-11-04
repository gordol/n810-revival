"""Dependency-free offline line maps. Coordinates in packs are [longitude, latitude]."""
import glob, gzip, json, math, os, hashlib, tempfile, base64, zlib, marshal
from collections import OrderedDict



def clipped_segment(a,b,w,h):
    x,y=a;dx,dy=b[0]-x,b[1]-y;lo,hi=0.,1.
    for p,q in ((-dx,x),(dx,w-1-x),(-dy,y),(dy,h-1-y)):
        if p==0:
            if q<0:return None
        else:
            r=q/p
            if p<0:lo=max(lo,r)
            else:hi=min(hi,r)
            if lo>hi:return None
    return (x+lo*dx,y+lo*dy),(x+hi*dx,y+hi*dy)


class Atlas:
    def __init__(self,directory,cache_directory=None):
        self.packs=[];self.errors=[];self.cache=OrderedDict()
        self.cache_directory=cache_directory
        self.fingerprint=[]
        for path in sorted(glob.glob(os.path.join(directory,'*.json.gz'))):
            try:
                stat=os.stat(path);self.fingerprint.append((os.path.basename(path),stat.st_size,stat.st_mtime_ns))
                meta=path[:-8]+'.meta.json'
                if os.path.exists(meta) and os.stat(meta).st_mtime_ns>=stat.st_mtime_ns:
                    with open(meta,encoding='utf-8') as f:p=json.load(f)
                else:
                    with gzip.open(path,'rt',encoding='utf-8') as f:p=json.load(f)
                if p['version']!=1:raise ValueError('unsupported version')
                w,s,e,n=p['bbox']
                if not (-180<=w<e<=180 and -90<=s<n<=90):raise ValueError('invalid bounds')
                for label in p['labels']:
                    if not isinstance(label['name'],str):raise ValueError('invalid label')
                    float(label['lon']);float(label['lat'])
                p['_path']=path
                if p.get('close_roads'):
                    road_path=os.path.join(directory,os.path.basename(p['close_roads']))
                    if os.path.exists(road_path):
                        stat=os.stat(road_path)
                        self.fingerprint.append((os.path.basename(road_path),stat.st_size,stat.st_mtime_ns))
                        p['_road_path']=road_path
                self.packs.append(p)
            except (OSError,ValueError,KeyError,TypeError) as exc:self.errors.append(os.path.basename(path)+': '+str(exc))

    # Coarse regional bases first; finer local rasters overwrite their coverage.
        self.packs.sort(key=lambda p:(p['bbox'][2]-p['bbox'][0])/p['raster']['width'] if 'raster' in p else 0,reverse=True)

    def features(self,p):
        if '_features' in p:return p['_features']
        if 'lines' not in p:
            with gzip.open(p['_path'],'rt',encoding='utf-8') as f:p['lines']=json.load(f)['lines']
        features=[]
        for line in sorted(p['lines'],key=lambda l:l['kind']=='road'):
            if line['kind'] not in ('coast','water','road'):continue
            points=[(round(lon*100000),round(lat*100000)) for lon,lat in line['points']]
            if len(points)<2:continue
            xs,ys=zip(*points);bounds=(min(xs),min(ys),max(xs),max(ys))
            if line['kind']=='water' and max((bounds[2]-bounds[0])*75,(bounds[3]-bounds[1])*111)<500000:continue
            features.append((line['kind'],bounds,points))
        p['_features']=features
        del p['lines']
        return features

    def disk_path(self,key):
        if not self.cache_directory:return None
        digest=hashlib.sha256(repr((15,self.fingerprint,key)).encode()).hexdigest()
        return os.path.join(self.cache_directory,digest+'.bin')

    def save_base(self,path,result):
        if not path:return
        temp=None
        try:
            os.makedirs(self.cache_directory,mode=0o700,exist_ok=True)
            fd,temp=tempfile.mkstemp(dir=self.cache_directory,prefix='.base-')
            with os.fdopen(fd,'wb') as f:f.write(b'N8M2'+zlib.compress(marshal.dumps(result,2),3))
            os.replace(temp,path)
            files=sorted(glob.glob(os.path.join(self.cache_directory,'*.bin'))+glob.glob(os.path.join(self.cache_directory,'*.json')),key=os.path.getmtime)
            for old in files[:-32]:os.unlink(old)
        except (OSError,KeyError,ValueError):pass
        finally:
            if temp and os.path.exists(temp):os.unlink(temp)

    @staticmethod
    def project(lon,lat,center,span,w,h):
        lat0,lon0=center
        # 8x16 console cells: equal physical distance per axis.
        scale=(w-1)/span
        return ((w-1)/2+(lon-lon0)*111.32*math.cos(math.radians(lat0))*scale,
                (h-1)/2-(lat-lat0)*111.32*scale/2)

    def raster_base(self,center,span,w,h,roads):
        cells={};names=[]
        lat0,lon0=center
        dx=span/max(1,w-1)/(111.32*math.cos(math.radians(lat0)))
        dy=span/max(1,w-1)*2/111.32
        longitude=[[round((lon0+(x-(w-1)/2+offset)*dx)*1000000) for x in range(w)] for offset in (-.33,0,.33)]
        # Three rows per half-cell; the middle sample anchors land barriers.
        latitude=[[round((lat0-(y-(h-1)/2+offset)*dy)*1000000) for y in range(h)] for offset in (-.42,-.25,-.08,.08,.25,.42)]
        view_w=min(longitude[0])/1000000;view_e=max(longitude[-1])/1000000
        view_s=min(latitude[-1])/1000000;view_n=max(latitude[0])/1000000
        packs=[p for p in self.packs if 'raster' in p and span<=p.get('max_span_km',float('inf'))]
        first=0
        for i,p in enumerate(packs):
            west,south,east,north=p['bbox']
            if west<=view_w and east>=view_e and south<=view_s and north>=view_n:first=i
        for p in packs[first:]:
            west,south,east,north=p['bbox']
            if east<view_w or west>view_e or north<view_s or south>view_n:continue
            r=p['raster'];rw,rh=r['width'],r['height']
            if '_pixels' not in p:
                p['_pixels']=zlib.decompress(base64.b64decode(r['data']))
                if len(p['_pixels'])!=rw*rh:raise ValueError('invalid raster length')
            pixels=p['_pixels'];west,south,east,north=[round(v*1000000) for v in p['bbox']]
            xs=[[((value-west)*(rw-1)//(east-west) if west<=value<=east else -1) for value in row] for row in longitude]
            ys=[[((north-value)*(rh-1)//(north-south) if south<=value<=north else -1) for value in row] for row in latitude]
            typed=bool(p.get('water_classes'));covered=False
            for y in range(h):
                for x in range(w):
                    halves=[]
                    for offset in (0,3):
                        if p.get('fast_samples'):
                            xx,yy=xs[1][x],ys[offset+1][y]
                            if xx<0 or yy<0:halves.append(7);continue
                            value=pixels[yy*rw+xx];wet=(value&3)==1 or ((value&3)==2 and span<=120)
                            halves.append(0 if wet else 1+(value>>2));covered=True
                            continue
                        samples=[]
                        for row in range(offset,offset+3):
                            yy=ys[row][y]
                            if yy<0:continue
                            for column in range(3):
                                xx=xs[column][x]
                                if xx>=0:samples.append(pixels[yy*rw+xx])
                        xx,yy=xs[1][x],ys[offset+1][y]
                        if not samples or xx<0 or yy<0:halves.append(7);continue
                        covered=True;middle=pixels[yy*rw+xx]
                        def water(value):
                            kind=value&3 if typed else value&1
                            return kind==1 or (kind==2 and span<=120)
                        # Never paint over a sampled land center; suppress lakes at wide zoom.
                        wet=water(middle) and sum(water(value) for value in samples)*4>=len(samples)*3
                        if wet:halves.append(0)
                        else:
                            land=[value>>2 for value in samples if not water(value)]
                            halves.append(1+(max(land) if land else middle>>2))
                    top,bottom=halves
                    if top==7 and bottom==7:continue
                    char='▀' if top!=bottom else ' '
                    kind='relief' if p.get('terrain',{}).get('render')=='hillshade' else 'tone'
                    cells[x,y]=(char,kind+'%d%d'%(top,bottom))
            if covered:names.append(p['name'])
        return cells,names

    def close_roads(self,cells,center,span,w,h):
        if span>60:return
        scale=(w-1)/span
        sx=round(111.32*math.cos(math.radians(center[0]))*scale/100000*(1<<24))
        sy=round(111.32*scale/200000*(1<<24));unit=1<<24
        lon0,lat0=round(center[1]*100000),round(center[0]*100000)
        cx,cy=(w-1)*unit//2,(h-1)*unit//2
        def project(point):return (cx+(point[0]-lon0)*sx+unit//2)//unit,(cy-(point[1]-lat0)*sy+unit//2)//unit
        west,east=lon0-cx//sx,lon0+cx//sx;south,north=lat0-cy//sy,lat0+cy//sy
        packs=[p for p in self.packs if '_road_path' in p]
        for local in packs:
            left,bottom,right,top=[round(v*100000) for v in local['bbox']]
            if local.get('replace_roads') and left<=west and right>=east and bottom<=south and top>=north:
                packs=[local];break
        for p in packs:
            if '_roads' not in p:
                with gzip.open(p['_road_path'],'rt') as f:p['_roads']=json.load(f)
            for (left,bottom,right,top),points in p['_roads']:
                if right<west or left>east or top<south or bottom>north:continue
                previous=project(points[0])
                for point in points[1:]:
                    current=project(point)
                    clipped=clipped_segment(previous,current,w,h);previous=current
                    if not clipped:continue
                    (x,y),(xx,yy)=clipped;x,y,xx,yy=round(x),round(y),round(xx),round(yy)
                    dx,dy=abs(xx-x),abs(yy-y);error=dx-dy
                    symbol='─' if dx>dy*2 else ('│' if dy>dx*2 else ('/' if (xx-x)*(yy-y)<0 else chr(92)))
                    xstep=1 if x<xx else -1;ystep=1 if y<yy else -1
                    while True:
                        cells[x,y]=(symbol,'road')
                        if x==xx and y==yy:break
                        twice=2*error
                        if twice>-dy:error-=dy;x+=xstep
                        if twice<dx:error+=dx;y+=ystep

    def background(self,center,span,w,h,roads):
        key=(tuple(round(v,6) for v in center),round(span,6),w,h,roads)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        disk=self.disk_path(key)
        if disk:
            try:
                with open(disk,'rb') as f:data=f.read()
                if data[:4]!=b'N8M2':raise ValueError('bad cache magic')
                result=marshal.loads(zlib.decompress(data[4:]))
                cells,names=result
                if not isinstance(cells,dict) or not isinstance(names,list) or len(cells)>w*h:raise ValueError('bad cache shape')
                if any(x<0 or y<0 or x>=w or y>=h for x,y in cells):raise ValueError('cache out of bounds')
                self.cache[key]=result
                if len(self.cache)>8:self.cache.popitem(last=False)
                return result
            except (OSError,ValueError,KeyError,TypeError,IndexError,EOFError,zlib.error):pass
        if any('raster' in p for p in self.packs):
            result=self.raster_base(center,span,w,h,roads)
            if roads:self.close_roads(result[0],center,span,w,h)
            self.cache[key]=result
            self.save_base(disk,result)
            if len(self.cache)>8:self.cache.popitem(last=False)
            return result
        cells={};names=[]
        lat0,lon0=center
        # Fixed-point projection: all per-vertex arithmetic stays integer.
        fixed=1<<24
        sx=round(111.32*math.cos(math.radians(lat0))*(w-1)/span/100000*fixed)
        sy=round(111.32*(w-1)/span/200000*fixed)
        lon0=round(lon0*100000);lat0=round(lat0*100000)
        cx=(w-1)*fixed//2;cy=(h-1)*fixed//2;half=fixed//2
        west=lon0-cx//sx;east=lon0+cx//sx
        south=lat0-cy//sy;north=lat0+cy//sy
        def project(lon,lat):return (cx+(lon-lon0)*sx+half)//fixed,(cy-(lat-lat0)*sy+half)//fixed
        for p in self.packs:
            pw,ps,pe,pn=p['bbox']
            if pe*100000<west or pw*100000>east or pn*100000<south or ps*100000>north:continue
            names.append(p['name'])
            for kind,(left,bottom,right,top),points in self.features(p):
                if kind=='road' and not roads:continue
                if right<west or left>east or top<south or bottom>north:continue
                previous=project(*points[0])
                for point in points[1:]:
                    current=project(*point)
                    x,y=previous;xx,yy=current;previous=current
                    if max(x,xx)<0 or min(x,xx)>=w or max(y,yy)<0 or min(y,yy)>=h:continue
                    if not (0<=x<w and 0<=xx<w and 0<=y<h and 0<=yy<h):
                        clip=clipped_segment((x,y),(xx,yy),w,h)
                        if not clip:continue
                        (x,y),(xx,yy)=clip;x,y,xx,yy=round(x),round(y),round(xx),round(yy)
                    dx,dy=abs(xx-x),abs(yy-y)
                    char='.' if kind!='road' else ('-' if dx>dy*2 else ('|' if dy>dx else ('/' if (xx-x)*(yy-y)<0 else chr(92))))
                    xstep=1 if x<xx else -1;ystep=1 if y<yy else -1
                    error=dx-dy
                    while True:
                        cells[x,y]=(char,kind)
                        if x==xx and y==yy:break
                        twice=2*error
                        if twice>-dy:error-=dy;x+=xstep
                        if twice<dx:error+=dx;y+=ystep
        result=(cells,names);self.cache[key]=result
        self.save_base(disk,result)
        if len(self.cache)>8:self.cache.popitem(last=False)
        return result
