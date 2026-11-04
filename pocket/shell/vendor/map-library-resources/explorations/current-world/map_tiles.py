"""Read-only fixed-style geographic tiles; one caller-owned worker, no transport."""
from collections import OrderedDict
from concurrent.futures import CancelledError
from dataclasses import dataclass
from pathlib import Path
import hashlib,json,math,os,re,stat,struct,threading,time,zlib
CELL=struct.Struct('<IQ')

def integer(value,low,high):return type(value) is int and low<=value<=high
def finite(value,low,high):return type(value) in (int,float) and low<=value<=high and math.isfinite(value)
def checksum(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None
def pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('Duplicate manifest key')
        result[key]=value
    return result
def invalid_constant(value):raise ValueError('Non-finite manifest number')

def read_owned(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in (0,os.getuid()) or info.st_mode&0o022:raise ValueError('Untrusted pack file')
        if not 0<info.st_size<=limit:raise ValueError('Pack file exceeds size bound')
        data=stream.read(limit+1)
    if len(data)>limit:raise ValueError('Pack file exceeds size bound')
    return data

@dataclass(frozen=True)
class Frame:
    width:int
    height:int
    cells:tuple
    legend:str
    places:tuple=()
    seconds:float=0
    complete:bool=True

class Archive:
    def __init__(self,root,hot_tiles=24,allow_coarse=False):
        self.root=Path(root)
        if type(allow_coarse) is not bool:raise ValueError('Invalid coarse fallback setting')
        self.allow_coarse=allow_coarse
        data=read_owned(self.root/'manifest.json',1024*1024)
        try:
            self.manifest=json.loads(data,object_pairs_hook=pairs,parse_constant=invalid_constant)
            self._validate()
        except (KeyError,TypeError,AttributeError,OverflowError,RecursionError) as error:raise ValueError('Malformed tile manifest') from error
        self.levels=self.manifest['levels']
        if not integer(hot_tiles,1,24):raise ValueError('Invalid hot tile budget')
        self.hot=OrderedDict();self.limit=max(1,min(24,hot_tiles));self.lock=threading.Lock();self.revision=0;self.plans=OrderedDict()
        self.stats=dict(hits=0,misses=0,loads=0,decode_seconds=0.,assemble_seconds=0.,cancelled=0,preparations=0)
        self._preview_key=None;self._preview=None
    def _validate(self):
        m=self.manifest
        if not isinstance(m,dict) or type(m.get('version')) is not int or m['version']!=1 or m.get('style')!='fixed-geographic-elevation-low-relief-v2':raise ValueError('Unsupported tile style')
        if not checksum(m['identity']):raise ValueError('Invalid pack identity')
        if m['terrain'] is not True or m['roads'] is not True:raise ValueError('Unsupported pack settings')
        if not finite(m['projection']['cell_aspect'],2,2):raise ValueError('Unsupported projection aspect')
        tw,th=m['tile_width'],m['tile_height']
        if not integer(tw,1,32) or not integer(th,1,16):raise ValueError('Tile dimensions exceed bound')
        levels=m['levels']
        if not isinstance(levels,list) or not 1<=len(levels)<=3:raise ValueError('Invalid level count')
        ids=set();files=set();count=total=0
        for level in levels:
            identity=level['id']
            if not isinstance(identity,str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}',identity) or identity in ids:raise ValueError('Invalid or duplicate level identity')
            ids.add(identity);w,h,span=level['width'],level['height'],level['span']
            if not integer(w,2,1024) or not integer(h,2,512) or not finite(span,.001,2000):raise ValueError('Invalid region extent')
            center=level['center']
            if not isinstance(center,list) or len(center)!=2 or not finite(center[0],-84.999999,84.999999) or not finite(center[1],-179.999999,179.999999):raise ValueError('Invalid region center')
            lat,lon=center;dx=span/111.32/math.cos(math.radians(lat))/2;dy=span/(w-1)*(h-1)/111.32
            expected=(lon-dx,lat-dy,lon+dx,lat+dy);bbox=level['bbox']
            if not isinstance(bbox,list) or len(bbox)!=4 or any(not finite(v,-180,180) or abs(v-e)>1e-8 for v,e in zip(bbox,expected)) or bbox[1]<-85 or bbox[3]>85 or bbox[0]<-180 or bbox[2]>180:raise ValueError('Invalid region bounds')
            if not finite(level['spacing_m'],0,80000) or abs(level['spacing_m']-1000*span/(w-1))>1e-8:raise ValueError('Invalid sample spacing')
            if not isinstance(level['legend'],str) or len(level['legend'])>512 or not level['legend'].isprintable():raise ValueError('Invalid legend')
            tiles=level['tiles'];nx,ny=(w+tw-1)//tw,(h+th-1)//th
            if not isinstance(tiles,dict) or len(tiles)!=nx*ny:raise ValueError('Incomplete tile topology')
            count+=len(tiles)
            if count>1024:raise ValueError('Tile count exceeds bound')
            for y in range(ny):
                for x in range(nx):
                    item=tiles[f'{x},{y}'];iw,ih=item['width'],item['height']
                    if not integer(iw,1,tw) or not integer(ih,1,th) or iw!=min(tw,w-x*tw) or ih!=min(th,h-y*th):raise ValueError('Tile does not fit grid')
                    if not integer(item['bytes'],1,65536) or not checksum(item['sha256']):raise ValueError('Invalid tile metadata')
                    total+=item['bytes'];name=item['file']
                    if not isinstance(name,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\\.tile',name) or name in files:raise ValueError('Invalid or duplicate tile path')
                    files.add(name)
        if total>4*1024*1024:raise ValueError('Tile disk budget exceeded')
        sources=m['sources']
        if not isinstance(sources,list) or not 1<=len(sources)<=128:raise ValueError('Invalid sources')
        paths=set()
        for source in sources:
            name=source['file']
            if not isinstance(name,str) or not 1<=len(name)<=256 or '\\' in name or Path(name).is_absolute() or any(p in ('','..','.') for p in name.split('/')) or name in paths or not checksum(source['sha256']):raise ValueError('Invalid source identity')
            paths.add(name)
        palette=m['palette']
        if palette['version']!=m['style'] or not checksum(palette['sha256']):raise ValueError('Invalid palette identity')
        points=palette['breakpoints']
        if not isinstance(points,list) or not 2<=len(points)<=64:raise ValueError('Invalid palette breakpoints')
        previous=-10001
        for point in points:
            if not isinstance(point,list) or len(point)!=2 or not finite(point[0],-10000,10000) or point[0]<=previous or not isinstance(point[1],list) or len(point[1])!=3 or any(not integer(v,0,255) for v in point[1]):raise ValueError('Invalid palette breakpoint')
            previous=point[0]
    def snapshot(self):
        with self.lock:return dict(self.stats,hot_tiles=len(self.hot),hot_cells=sum(len(v) for v in self.hot.values()),revision=self.revision)
    def clear_hot(self):
        with self.lock:
            self.hot.clear();self.revision+=1;self._preview_key=None;self._preview=None
    def plan(self,view,allow_coarse=None,level_id=None,allow_downsample=False):
        if not integer(view.width,1,1024) or not integer(view.height,1,512) or not finite(view.span,.001,2000) or not finite(view.cell_aspect,2,2):return None
        if len(view.center)!=2 or not finite(view.center[0],-84.999999,84.999999) or not finite(view.center[1],-179.999999,179.999999):return None
        if allow_coarse is None:allow_coarse=self.allow_coarse
        if type(allow_coarse) is not bool:raise ValueError('Invalid coarse fallback setting')
        if type(allow_downsample) is not bool:raise ValueError('Invalid downsampling setting')
        if level_id is not None and (not isinstance(level_id,str) or not any(level['id']==level_id for level in self.levels)):return None
        key=(view.key,allow_coarse,level_id,allow_downsample)
        with self.lock:
            if key in self.plans:self.plans.move_to_end(key);return self.plans[key]
        value=self._plan(view,allow_coarse,level_id,allow_downsample)
        with self.lock:
            self.plans[key]=value
            while len(self.plans)>8:self.plans.popitem(last=False)
        return value
    def resolution(self,view,plan):
        native=plan[0]['spacing_m'];requested=1000*view.span/max(1,view.width-1)
        return dict(native_spacing_m=native,requested_spacing_m=requested,
                    oversampling_factor=max(1.,native/requested),resolution_limited=requested<native,coarse_fallback=requested/native<.45,
                    sampling='nearest existing source cells; no new measured detail')
    def _plan(self,view,allow_coarse=False,level_id=None,allow_downsample=False):
        spacing=view.span/max(1,view.width-1)
        level=next(level for level in self.levels if level['id']==level_id) if level_id is not None else min(self.levels,key=lambda l:abs(math.log(spacing/(l['span']/(l['width']-1)))))
        # Coarse fallback repeats existing samples without inventing measured detail.
        ratio=spacing/(level['span']/(level['width']-1))
        if ratio>2.5 and not allow_downsample or ratio<.45 and not allow_coarse:return None
        lat,lon=view.center;ref_lat,ref_lon=level['center'];scale=(level['width']-1)/level['span']
        cosine=math.cos(math.radians(ref_lat));dx=spacing/(111.32*math.cos(math.radians(lat)))
        xs=tuple(round((level['width']-1)/2+(lon+(x-(view.width-1)/2)*dx-ref_lon)*111.32*cosine*scale) for x in range(view.width))
        ys=tuple(round((level['height']-1)/2-(lat-(y-(view.height-1)/2)*spacing*view.cell_aspect/111.32-ref_lat)*111.32*scale/2) for y in range(view.height))
        if min(xs)<0 or max(xs)>=level['width'] or min(ys)<0 or max(ys)>=level['height']:return None
        tw,th=self.manifest['tile_width'],self.manifest['tile_height']
        keys={(x,y) for x in {v//tw for v in xs} for y in {v//th for v in ys}}
        cx,cy=(min(xs)+max(xs))/2/tw,(min(ys)+max(ys))/2/th
        keys=tuple(sorted(keys,key=lambda p:(p[0]-cx)**2+(p[1]-cy)**2))
        return level,xs,ys,keys
    def _load(self,level,key,cancel):
        identity=(level['id'],)+key
        with self.lock:
            if identity in self.hot:self.hot.move_to_end(identity);self.stats['hits']+=1;return self.hot[identity]
            self.stats['misses']+=1
        if cancel():raise CancelledError()
        item=level['tiles'][f'{key[0]},{key[1]}'];path=self.root/item['file'];start=time.perf_counter()
        data=read_owned(path,65536)
        if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('Tile checksum mismatch')
        try:
            decoder=zlib.decompressobj();raw=decoder.decompress(data,6145)
        except zlib.error as exc:raise ValueError('Invalid compressed tile') from exc
        if not decoder.eof or decoder.unused_data or len(raw)!=item['width']*item['height']*CELL.size:raise ValueError('Invalid tile data')
        values=[]
        for code,color in CELL.iter_unpack(raw):
            char=chr(code)
            if not char.isprintable() or not (1<<48)<=color<(1<<49):raise ValueError('Invalid tile cell')
            values.append((char,color))
        values=tuple(values)
        with self.lock:
            self.hot[identity]=values;self.revision+=1;self.stats['loads']+=1;self.stats['decode_seconds']+=time.perf_counter()-start
            while len(self.hot)>self.limit:self.hot.popitem(last=False)
        return values
    def _assemble(self,view,plan,tiles):
        start=time.perf_counter();level,xs,ys,keys=plan;tw,th=self.manifest['tile_width'],self.manifest['tile_height'];cells=[]
        missing=('░',(1<<48)|(0x304050<<24)|0x101820)
        for y in ys:
            for x in xs:
                key=x//tw,y//th;tile=tiles.get(key)
                item=level['tiles'][f'{key[0]},{key[1]}']
                cells.append(tile[(y%th)*item['width']+x%tw] if tile is not None else missing)
        self.stats['assemble_seconds']+=time.perf_counter()-start
        return Frame(view.width,view.height,tuple(cells),'Fixed v2 regional pack · '+level['legend'],complete=len(tiles)==len(keys))
    def preview(self,view,allow_coarse=None,level_id=None,allow_downsample=False):
        plan=self.plan(view,allow_coarse,level_id,allow_downsample)
        if plan is None:return None
        level,_,_,keys=plan
        with self.lock:
            signature=(view.key,self.revision,allow_coarse,level_id,allow_downsample)
            if signature==self._preview_key:return self._preview
            tiles={key:self.hot[(level['id'],)+key] for key in keys if (level['id'],)+key in self.hot}
        if not tiles:return None
        self._preview_key=signature;self._preview=self._assemble(view,plan,tiles)
        return self._preview
    def render(self,view,cancel=lambda:False,allow_coarse=None,level_id=None,allow_downsample=False):
        plan=self.plan(view,allow_coarse,level_id,allow_downsample)
        if plan is None:return None
        started=time.perf_counter();level,xs,ys,keys=plan
        tw,th=self.manifest['tile_width'],self.manifest['tile_height'];columns={};rows={}
        for x,source in enumerate(xs):columns.setdefault(source//tw,[]).append((x,source%tw))
        for y,source in enumerate(ys):rows.setdefault(source//th,[]).append((y,source%th))
        cells=[None]*(view.width*view.height)
        self.stats['assemble_seconds']+=time.perf_counter()-started
        for key in keys:
            if cancel():self.stats['cancelled']+=1;raise CancelledError()
            tile=self._load(level,key,cancel);started=time.perf_counter()
            stride=level['tiles'][f'{key[0]},{key[1]}']['width']
            for y,source_y in rows[key[1]]:
                destination=y*view.width;source=source_y*stride
                for x,source_x in columns[key[0]]:cells[destination+x]=tile[source+source_x]
            self.stats['assemble_seconds']+=time.perf_counter()-started
        if cancel():self.stats['cancelled']+=1;raise CancelledError()
        return Frame(view.width,view.height,tuple(cells),'Fixed v2 regional pack · '+level['legend'])
