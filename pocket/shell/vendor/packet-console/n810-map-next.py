"""Opt-in offline map engine with viewport, layers and bounded cell rendering."""
import math, importlib.util, sys, time, marshal, zlib, unicodedata, hashlib, copy, os, stat
from array import array
from pathlib import Path
from collections import namedtuple, OrderedDict

def project(lon,lat,center,span,width,height,cell_aspect=2):
    lat0,lon0=center
    scale=max(1,width-1)/span
    return ((width-1)/2+(lon-lon0)*111.32*math.cos(math.radians(lat0))*scale,
            (height-1)/2-(lat-lat0)*111.32*scale/cell_aspect)


class Viewport(namedtuple('ViewportFields','center span width height cell_aspect')):
    """Geographic view in terminal cells; coordinates are latitude, longitude."""
    __slots__=()
    def __new__(cls,center,span,width,height,cell_aspect=2):
        center=tuple(map(float,center));span=float(span);cell_aspect=float(cell_aspect)
        if len(center)!=2 or not all(math.isfinite(v) for v in center+(span,cell_aspect)):
            raise ValueError('Non-finite map view')
        if not -90<=center[0]<=90 or span<=0 or width<1 or height<1 or cell_aspect<=0:
            raise ValueError('Invalid map view')
        return super().__new__(cls,center,span,int(width),int(height),cell_aspect)
    @property
    def key(self):return tuple(self)
    @property
    def ground_m_per_halfcell(self):return self.span*1000/max(1,self.width-1)
    def project(self,lon,lat):return project(lon,lat,self.center,self.span,self.width,self.height,self.cell_aspect)
    @property
    def bbox(self):
        lat,lon=self.center
        half_lon=self.span/(2*111.32*max(.000001,math.cos(math.radians(lat))))
        half_lat=self.span*max(0,self.height-1)*self.cell_aspect/(2*max(1,self.width-1)*111.32)
        return lon-half_lon,max(-90,lat-half_lat),lon+half_lon,min(90,lat+half_lat)
    def bounds(self):return self.bbox


class Overlay(dict):
    """Clipped foreground cells; larger priority wins a shared cell."""
    def __init__(self,width,height):
        super().__init__();self.width=width;self.height=height;self.priorities={}
    def put(self,x,y,cell,priority=0):
        if not (0<=x<self.width and 0<=y<self.height):return False
        key=(x,y)
        if priority<self.priorities.get(key,-math.inf):return False
        self[key]=cell;self.priorities[key]=priority;return True
    def add(self,cells,priority=0):
        for (x,y),cell in cells.items():self.put(x,y,cell,priority)


def composite(frame,overlays,width,height):
    cells=list(frame)
    if len(cells)!=width*height:raise ValueError('Map frame size differs from view')
    for (x,y),mark in overlays.items():
        if 0<=x<width and 0<=y<height:
            i=y*width+x
            cells[i]=tuple(mark)+(cells[i][2],) if len(mark)==2 and len(cells[i])==3 else tuple(mark)
    return cells


def changed_runs(cells,previous,width):
    """Yield row, column, text and style for contiguous changed cells."""
    for y in range(len(cells)//width):
        x=0
        while x<width:
            i=y*width+x
            if previous is not None and cells[i]==previous[i]:x+=1;continue
            start=x;style=cells[i][1:];text=[]
            while x<width:
                j=y*width+x
                if cells[j][1:]!=style or (previous is not None and cells[j]==previous[j]):break
                text.append(cells[j][0]);x+=1
            yield y,start,''.join(text),style


class CellSurface:
    """Changed-cell output using native curses attributes and caller-owned colors."""
    def __init__(self):self.previous=None;self.geometry=None
    def invalidate(self):self.previous=None
    def draw(self,win,frame,overlays,x0,y0,width,height,force=False):
        cells=composite(frame,overlays,width,height);geometry=(x0,y0,width,height)
        previous=None if force or geometry!=self.geometry else self.previous
        for y,x,text,style in changed_runs(cells,previous,width):
            try:win.addnstr(y0+y,x0+x,text,len(text),style[0])
            except __import__('curses').error:pass
        self.previous=cells;self.geometry=geometry


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


ANSI_RGB=((0,0,0),(170,0,0),(0,170,0),(170,85,0),(0,0,170),(170,0,170),(0,170,170),(170,170,170),
          (85,85,85),(255,85,85),(85,255,85),(255,255,85),(85,85,255),(255,85,255),(85,255,255),(255,255,255))

def rgb_enabled():return load('next_rgb_probe','n810-map-rgb.py').enabled()

def ansi_color(number,colors=ANSI_RGB):
    if number<0:return colors[7]
    if number<16:return colors[number]
    if number>=232:return (min(255,8+(number-232)*10),)*3
    n=number-16;levels=(0,95,135,175,215,255)
    return levels[(n//36)%6],levels[(n//6)%6],levels[n%6]


def ansi_overlays(cells,colors=ANSI_RGB,backplate=None):
    """Keep app foreground semantics over an RGB terrain surface."""
    import curses
    result={}
    for key,(char,attr) in cells.items():
        try:fg,bg=curses.pair_content(curses.pair_number(attr))
        except curses.error:fg,bg=7,0
        if attr&curses.A_BOLD and 0<=fg<8:fg+=8
        reverse=bool(attr&curses.A_REVERSE)
        if reverse:fg,bg=bg,fg
        foreground=ansi_color(fg,colors)
        if attr&curses.A_DIM:foreground=tuple(v*2//3 for v in foreground)
        result[key]=(char,foreground,ansi_color(bg,colors)) if bg>0 or reverse else (char,foreground,backplate) if backplate is not None else (char,foreground)
    return result


def wide_color(palette,height):
    """One absolute height curve for filtered heights and coarse class edges."""
    edges=(0,200,500,1000,1800,2800)
    if height<=0:return palette.REGIONAL[1]
    for i,edge in enumerate(edges[1:],1):
        if height<edge:return palette.blend(palette.REGIONAL[i],palette.REGIONAL[i+1],(height-edges[i-1])/(edge-edges[i-1]))
    return palette.REGIONAL[6]


def canonical_places(packs):
    """Merge source labels once; prefer finer coordinates and retain provenance."""
    candidates=[]
    for pack in packs:
        raster=pack.get('raster',{});bbox=pack.get('bbox')
        spacing=math.inf
        if bbox and raster.get('width') and raster.get('height'):
            west,south,east,north=bbox
            spacing=max((east-west)*111320*math.cos(math.radians((north+south)/2))/raster['width'],(north-south)*111320/raster['height'])
        for label in pack.get('labels',[]):candidates.append((spacing,pack.get('name',''),label))
    groups={};by_id={};result=[]
    def identifiers(label,source):
        values=set()
        def add(namespace,value):
            namespace=str(namespace).casefold();value=str(value).rstrip('/').rsplit('/',1)[-1]
            if namespace=='wikidata':value=value.rsplit(':',1)[-1].upper()
            if namespace=='geonames' and value.endswith('.0') and value[:-2].isdecimal():value=value[:-2]
            values.add((namespace,value))
        supplied=label.get('identifiers',{})
        if isinstance(supplied,dict):
            for k,v in supplied.items():
                if v is not None:add(k,v)
        for field,namespace in (('wikidata','wikidata'),('wikidataid','wikidata'),('geonameid','geonames'),('geonames_id','geonames')):
            value=label.get(field)
            if value is not None:add(namespace,value)
        if label.get('osm_id') is not None:add('osm:'+str(label.get('osm_type','unknown')),label['osm_id'])
        if label.get('id') is not None and (source or label.get('id_namespace')):add(label.get('id_namespace',source),label['id'])
        return values
    def names(label):
        aliases=label.get('aliases',())
        if isinstance(aliases,str):aliases=(aliases,)
        return tuple(dict.fromkeys(' '.join(unicodedata.normalize('NFKC',n).casefold().split()) for n in (label['name'],)+tuple(aliases) if isinstance(n,str) and n.strip()))
    def conflict(a,b):
        return any({v for ns,v in a if ns==namespace}.isdisjoint(v for ns,v in b if ns==namespace) for namespace in {ns for ns,v in a}&{ns for ns,v in b})
    for spacing,source,label in sorted(candidates,key=lambda item:(item[0],item[1])):
        kind=str(label.get('kind','place')).casefold().strip();category='settlement' if kind in ('city','town','village','hamlet') else kind
        aliases=names(label);ids=identifiers(label,source);match=None
        for namespace,value in sorted(ids):
            if (category,namespace,value) in by_id:match=by_id[category,namespace,value];break
        cap=2500 if category=='settlement' else 300
        if match is None:
            for name in aliases:
                for previous in groups.get((name,category),()):
                    if conflict(ids,set(previous['identifiers'])):continue
                    other_spacing=previous['source_spacing_m']
                    scale=max(spacing,other_spacing) if other_spacing is not None else math.inf
                    threshold=min(cap,max(100,scale*2.5)) if math.isfinite(scale) else min(cap,300)
                    uncertainty=label.get('position_uncertainty_m');other=previous.get('position_uncertainty_m')
                    if isinstance(uncertainty,(int,float)) and isinstance(other,(int,float)) and math.isfinite(uncertainty+other) and min(uncertainty,other)>=0:
                        threshold=min(cap,uncertainty+other)
                    dx=(label['lon']-previous['lon'])*111320*math.cos(math.radians((label['lat']+previous['lat'])/2))
                    dy=(label['lat']-previous['lat'])*111320
                    if dx*dx+dy*dy<=threshold*threshold:match=previous;break
                if match is not None:break
        if match is not None:
            if source not in match['sources']:match['sources']+= (source,)
            match['identifiers']=tuple(sorted(set(match['identifiers'])|ids))
            match['aliases']=tuple(dict.fromkeys(match['aliases']+aliases))
        else:
            match=dict(label,kind=kind,sources=(source,),source_spacing_m=None if math.isinf(spacing) else spacing,identifiers=tuple(sorted(ids)),aliases=aliases)
            result.append(match)
        for name in aliases:
            group=groups.setdefault((name,category),[])
            if not any(p is match for p in group):group.append(match)
        for namespace,value in match['identifiers']:by_id[category,namespace,value]=match
    return tuple(result)


class Terrain:
    """Read filtered source-height levels; no raster decoding in the render loop."""
    def __init__(self,path):
        raw=Path(path).read_bytes()
        if raw[:4]!=b'N8T1':raise ValueError('Bad next terrain pack')
        data=marshal.loads(zlib.decompress(raw[4:]));self.nodata=data['nodata'];self.layers=data['layers']
        for layer in self.layers:
            for level in layer['levels']:
                heights=array('h');heights.frombytes(level.pop('heights'))
                if sys.byteorder!='little':heights.byteswap()
                level['values']=heights
    def sample(self,view):
        rows=[array('h',[self.nodata])*view.width for _ in range(view.height*2)]
        shades=[bytearray([255])*view.width for _ in range(view.height*2)];selected=[]
        lat,lon=view.center;dx=view.span/max(1,view.width-1)/(111.32*max(.000001,math.cos(math.radians(lat))))
        dy=view.span/max(1,view.width-1)*view.cell_aspect/2/111.32
        half_x=(view.width-1)/2*dx;half_y=(view.height*2-1)/2*dy
        for layer in self.layers:
            west,south,east,north=layer['bbox']
            if lon+half_x<west or lon-half_x>east or lat+half_y<south or lat-half_y>north:continue
            level=layer['levels'][0]
            for candidate in layer['levels'][1:]:
                if max(candidate['spacing_m'])<=view.ground_m_per_halfcell*1.5:level=candidate
                else:break
            west,south,east,north=layer['bbox'];w,h=level['width'],level['height']
            xs=[math.floor((lon+(x-(view.width-1)/2)*dx-west)/(east-west)*w) for x in range(view.width)]
            ys=[math.floor((north-lat+(j-(view.height*2-1)/2)*dy)/(north-south)*h) for j in range(view.height*2)]
            columns=[(x,xx) for x,xx in enumerate(xs) if 0<=xx<w]
            used=0
            for j,y in enumerate(ys):
                if not 0<=y<h:continue
                offset=y*w
                for x,xx in columns:
                    i=offset+xx;value=level['values'][i]
                    if value!=self.nodata:rows[j][x]=value;shades[j][x]=level['shade'][i];used+=1
            if used:selected.append((layer['name'],round(max(level['spacing_m'])),used))
        return rows,shades,selected


class Engine:
    """Opt-in map pipeline; style is explicit and independent of terminal capability."""
    def __init__(self,maps,style='ansi',attribute=None,palette=None,cache_directory=None):
        if style not in ('ansi','rgb'):raise ValueError('Unknown map style')
        self.style=style;self.attribute=attribute or (lambda kind,terrain:0)
        self._maps=Path(maps);self._geometry=self._atlas=self._terrain=None;self._terrain_loaded=False
        self.legacy=load('next_metadata','n810-map.py').Atlas(str(maps))
        self.packs=self.legacy.packs;self.errors=self.legacy.errors
        self.labels=canonical_places(self.packs)
        self.rgb=load('next_rgb_palette','n810-map-rgb.py')
        self._palette=self.rgb if palette is None else palette
        self.surface=self.rgb.Surface() if style=='rgb' else CellSurface()
        self.cache=OrderedDict();self.panel_cache=OrderedDict();self.view=None;self.frame=None;self.frame_key=None;self.legend='';self.stats={}
        self.prepared=None
        if cache_directory is not None and style=='rgb' and palette is None:
            directory=Path(cache_directory).expanduser()
            if not directory.is_absolute():raise ValueError('Prepared cache path must be absolute')
            if directory.exists() or directory.is_symlink():
                info=directory.lstat()
                if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('Prepared cache must be a private owned directory')
            self.prepared=copy.copy(self.legacy);self.prepared.cache_directory=str(directory)
            source=Path(__file__).parent
            paths=[source/name for name in ('n810-map-next.py','n810-walk-map.py','n810-map-rgb.py','n810-map.py')]
            paths+=sorted(p for p in Path(maps).iterdir() if p.is_file() and (p.name.endswith(('.json.gz','.roads.gz','.meta.json','.n8w','.n8t'))))
            self.prepared.fingerprint=[(p.name,hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths]
        self.layer_bounds={}
    def _load_geography(self):
        if self._atlas is not None:return
        geometry=load('next_geometry','n810-walk-map.py')
        atlas=geometry.Atlas(str(self._maps))
        bounds={}
        for layer in atlas.roads+([atlas.streams] if atlas.streams else []):
            coords=memoryview(layer['coords']);xs=coords[0::2];ys=coords[1::2]
            if xs:bounds[id(layer)]=(min(xs),min(ys),max(xs),max(ys))
        self._geometry,self.layer_bounds=geometry,bounds
        self._atlas=atlas
    @property
    def atlas(self):
        self._load_geography();return self._atlas
    @property
    def terrain(self):
        if not self._terrain_loaded:
            path=self._maps/'terrain-next.n8t'
            self._terrain=Terrain(path) if path.exists() else None
            self._terrain_loaded=True
        return self._terrain
    @property
    def geometry(self):
        self._load_geography();return self._geometry
    @property
    def palette(self):
        """Background palette selected for this engine's lifetime."""
        return self._palette
    def invalidate(self):
        """Call after erasing, modal screens or returning from a hidden window."""
        self.surface.previous=None
    def clear_cache(self):self.cache.clear();self.panel_cache.clear();self.invalidate()
    def places(self,view=None):
        if view is None:return self.labels
        west,south,east,north=view.bbox
        return tuple(p for p in self.labels if west<=p['lon']<=east and south<=p['lat']<=north)
    def panel(self,rect,tint=(14,21,18),opacity=.65,underlay=None):
        """Tint prepared RGB cells inside a clipped map-local panel rectangle."""
        if self.style!='rgb' or self.view is None:raise ValueError('Prepare an RGB view before tinting panels')
        if not math.isfinite(opacity) or not 0<=opacity<=1:raise ValueError('Panel opacity must be 0..1')
        left,top,width,height=rect;alpha=round(opacity*256)
        key=(self.frame_key,tuple(rect),tuple(tint),alpha)
        if underlay is None and self.frame_key is not None and key in self.panel_cache:
            self.panel_cache.move_to_end(key);return dict(self.panel_cache[key])
        source=composite(self.frame,underlay,self.view.width,self.view.height) if underlay else self.frame
        result={}
        def mix(color):return tuple((c*(256-alpha)+t*alpha+128)//256 for c,t in zip(color,tint))
        for y in range(max(0,top),min(self.view.height,top+height)):
            for x in range(max(0,left),min(self.view.width,left+width)):
                char,fg,bg=source[y*self.view.width+x]
                result[x,y]=(char,mix(fg),mix(bg))
        if underlay is None and self.frame_key is not None:
            self.panel_cache[key]=dict(result)
            while len(self.panel_cache)>8:self.panel_cache.popitem(last=False)
        return result
    def _lines(self,view,streams=False):
        cells={};count=0;m=view.ground_m_per_halfcell
        if m>6000:return cells,count
        layers=[(2,self.atlas.streams)] if streams and self.atlas.streams else ([] if streams else list(enumerate(self.atlas.roads)))
        west,south,east,north=view.bbox;bounds=tuple(round(v*100000) for v in (west,south,east,north))
        unit=1<<24;half=unit//2;lat,lon=view.center;lon0=round(lon*100000);lat0=round(lat*100000)
        fx=111.32*math.cos(math.radians(lat))*max(1,view.width-1)/view.span
        fy=111.32*max(1,view.width-1)/view.span/view.cell_aspect
        scale_x=round(fx*unit/100000);scale_y=round(fy*unit/100000)
        cx=round(((view.width-1)/2+(lon0/100000-lon)*fx)*unit)
        cy=round(((view.height-1)/2-(lat0/100000-lat)*fy)*unit)
        for role,layer in layers:
            # Scale by ground distance per cell, not a fixed viewport span.
            if (role==0 and m>=150) or (role==2 and m>=250):continue
            extent=self.layer_bounds.get(id(layer))
            if extent is None:continue
            w,s,e,n=max(bounds[0],extent[0]),max(bounds[1],extent[1]),min(bounds[2],extent[2]),min(bounds[3],extent[3])
            if w>e or s>n:continue
            tile=layer['tile'];ids=set();index=layer['index'];coords=layer['coords']
            for by in range(s//tile,n//tile+1):
                for bx in range(w//tile,e//tile+1):ids.update(index.get((bx,by),()))
            count+=len(ids)
            for i in sorted(ids):
                a,b,c,d=coords[i*4:i*4+4]
                if max(a,c)<w or min(a,c)>e or max(b,d)<s or min(b,d)>n:continue
                x=(cx+(a-lon0)*scale_x+half)//unit;y=(cy-(b-lat0)*scale_y+half)//unit
                xx=(cx+(c-lon0)*scale_x+half)//unit;yy=(cy-(d-lat0)*scale_y+half)//unit
                line=self.geometry.clip(x,y,xx,yy,view.width,view.height)
                if line is None:continue
                x,y,xx,yy=line;dx,dy=abs(xx-x),abs(yy-y);error=dx-dy
                glyph='─' if dx>dy*2 else '│' if dy>dx*2 else '/' if (xx-x)*(yy-y)<0 else '\\'
                sx=1 if x<xx else -1;sy=1 if y<yy else -1
                while True:
                    old=cells.get((x,y))
                    cells[x,y]=('┼' if old and old[0]!=glyph else glyph,max(role,old[1]) if old else role)
                    if x==xx and y==yy:break
                    twice=error*2
                    if twice>-dy:error-=dy;x+=sx
                    if twice<dx:error+=dx;y+=sy
        return cells,count
    def _rgb_terrain(self,view,terrain):
        p=self.palette;rows,fine,stats=self.atlas.raster(view.center,view.span,view.width,view.height)
        interval=5 if view.span<=2.5 else 10 if view.span<=5 else 25
        values=[(v-1)*5 for row in fine for v in row if v!=255]
        low=(min(values)//interval)*interval if values else 0
        high=((max(values)//interval)+1)*interval if values else interval
        heights=None
        if terrain and view.span>5 and self.terrain:
            heights,_,levels=self.terrain.sample(view)
            values=[v for row in heights for v in row if v!=self.terrain.nodata]
            if values:
                low=(min(values)//interval)*interval;high=((max(values)//interval)+1)*interval
            self.stats['height_levels']=levels
        colors={}
        def color(kind,value,height=None):
            if height is not None and height==self.terrain.nodata:height=None
            if height is not None:
                height=(height//interval)*interval
                key=(0 if kind==0 else 7,height)
            else:key=(kind,value,None)
            if key not in colors:
                if kind==0:c=p.WATER
                elif not terrain:c=p.LAND
                elif height is not None:
                    c=p.blend(wide_color(p,height),p.band_color(height,low,high),max(0,min(1,(20-view.span)/15)))
                elif value==255:c=p.REGIONAL[kind]
                else:
                    height=(value-1)*5;c=p.band_color((height//interval)*interval,low,high)
                    if view.span>5:
                        c=p.blend(wide_color(p,height),c,max(0,(20-view.span)/15))
                colors[key]=c
            return colors[key]
        frame=[]
        for y in range(view.height):
            for x in range(view.width):
                a=color(rows[y*2][x],fine[y*2][x],heights[y*2][x] if heights else None);b=color(rows[y*2+1][x],fine[y*2+1][x],heights[y*2+1][x] if heights else None)
                frame.append((' ' if a==b else '▀',a,b))
        legend=('%d–%d m / %d m bands'%(low,high,interval)) if values else 'Regional elevation classes'
        if heights:legend+=' · filtered USGS heights'
        if stats['unknown']==stats['samples']:legend='No offline elevation coverage'
        if not terrain:legend='Flat land/water · terrain OFF'
        self.stats.update(stats)
        return frame,legend
    def _ansi_terrain(self,view,terrain):
        rows,_,stats=self.atlas.raster(view.center,view.span,view.width,view.height)
        shades=None;levels=[]
        if terrain and self.terrain:_,shades,levels=self.terrain.sample(view)
        frame=[]
        for y in range(view.height):
            for x in range(view.width):
                a,b=rows[y*2][x],rows[y*2+1][x];kind='tone'
                if shades and a and b and shades[y*2][x]!=255 and shades[y*2+1][x]!=255:
                    a=2+shades[y*2][x];b=2+shades[y*2+1][x];kind='relief'
                elif a or b:
                    # Coarse terrain uses the same grayscale family as filtered relief.
                    a=0 if a==0 else min(5,2+max(0,a-1)//2)
                    b=0 if b==0 else min(5,2+max(0,b-1)//2);kind='relief'
                frame.append((' ' if a==b else '▀',self.attribute('%s%d%d'%(kind,a,b),terrain)))
        self.stats.update(stats,height_levels=levels)
        legend='Filtered USGS relief' if levels else 'Regional elevation classes'
        if stats['unknown']==stats['samples']:legend='No offline elevation coverage'
        return frame,legend
    def _prepared_frame(self,path,view):
        try:
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o022:return None
                data=stream.read(2*1024*1024+1)
            if len(data)>2*1024*1024 or data[:4]!=b'N8M2':return None
            decoder=zlib.decompressobj();payload=decoder.decompress(data[4:],16*1024*1024+1)
            if len(payload)>16*1024*1024 or not decoder.eof or decoder.unused_data:return None
            tag,frame,legend=marshal.loads(payload)
            if tag!='next-rgb-v1':return None
            if not isinstance(frame,tuple) or len(frame)!=view.width*view.height or not isinstance(legend,str) or len(legend)>1000:return None
            for cell in frame:
                if not isinstance(cell,tuple) or len(cell)!=3:return None
                char,fg,bg=cell
                if not isinstance(char,str) or len(char)!=1 or not char.isprintable():return None
                for color in (fg,bg):
                    if not isinstance(color,tuple) or len(color)!=3 or any(type(v) is not int or not 0<=v<=255 for v in color):return None
            return frame,legend
        except (OSError,ValueError,TypeError,EOFError,zlib.error):return None

    def prepare(self,view,terrain=True,roads=True):
        started=time.monotonic();key=(view.key,bool(terrain),bool(roads))
        self.view=view;self.frame_key=key
        if key in self.cache:
            self.frame,self.legend=self.cache[key];self.cache.move_to_end(key)
            self.stats={'cache':'ram','seconds':time.monotonic()-started};return self.frame,self.legend
        self.stats={'cache':'loading'}
        disk=self.prepared.disk_path(('next-rgb-v1',key)) if self.prepared else None
        saved=self._prepared_frame(disk,view) if disk else None
        if saved is not None:
            self.frame,self.legend=saved;self.cache[key]=saved
            while len(self.cache)>8:self.cache.popitem(last=False)
            self.stats={'cache':'prepared','seconds':time.monotonic()-started}
            return saved
        self.stats={'cache':'cold'}
        if self.style=='rgb':frame,legend=self._rgb_terrain(view,terrain)
        else:frame,legend=self._ansi_terrain(view,terrain)
        lines,candidates=self._lines(view) if roads else ({},0)
        streams,water_candidates=self._lines(view,True)
        m=view.ground_m_per_halfcell
        opacity={0:round(256*max(0,min(1,(150-m)/120))),1:256,2:round(256*max(0,min(1,(250-m)/200)))}
        for marks,is_water in ((lines,False),(streams,True)):
            for (x,y),(char,role) in marks.items():
                i=y*view.width+x
                if self.style=='rgb':
                    _,_,bg=frame[i];alpha=opacity[role]
                    target=self.rgb.CREEK if is_water else (218,222,207)
                    if role==0:target=(173,181,159)
                    fg=tuple((b*(256-alpha)+t*alpha+128)//256 for b,t in zip(bg,target));frame[i]=(char,fg,bg)
                else:
                    import curses
                    attr=self.attribute('half' if is_water else 'road',terrain)
                    if role==0:attr|=curses.A_DIM
                    frame[i]=(char,attr)
        self.frame=tuple(frame);self.legend=legend;self.cache[key]=(self.frame,legend)
        if disk:self.prepared.save_base(disk,('next-rgb-v1',self.frame,legend))
        while len(self.cache)>8:self.cache.popitem(last=False)
        self.stats.update(candidates=candidates+water_candidates,road_cells=len(lines),stream_cells=len(streams),seconds=time.monotonic()-started)
        return self.frame,legend
    def draw(self,overlays,x0=0,y0=0,win=None,force=False):
        if self.view is None:raise ValueError('Prepare a viewport before drawing')
        args=(self.frame,overlays,x0,y0,self.view.width,self.view.height)
        if self.style=='rgb':self.surface.draw(*args,force=force)
        else:
            if win is None:raise ValueError('ANSI drawing requires a curses window')
            self.surface.draw(win,*args,force=force)
