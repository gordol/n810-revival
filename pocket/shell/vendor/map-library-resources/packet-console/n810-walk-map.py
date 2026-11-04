"""Walk-only indexed height bands, plain water fallback and road row runs."""
from array import array
from collections import OrderedDict
import curses,marshal,math,os,sys,zlib

PALETTE=(4,0,8,2,3,6,7,0)
COLORED=False
BANDS=[['band%d%d'%(a,b) for b in range(8)] for a in range(8)]
ROADS=[['street%d'%b for b in range(8)],['route%d'%b for b in range(8)]]


def init_colors():
    global COLORED
    COLORED=False
    if not curses.has_colors() or curses.COLOR_PAIRS<240:return
    colors=[v if v<curses.COLORS else 2 for v in PALETTE]
    for a in range(8):
        for b in range(8):curses.init_pair(144+a*8+b,colors[a],colors[b])
    for major in range(2):
        for b in range(8):
            bg=colors[b];fg=0 if bg in (3,6,7) else 7
            curses.init_pair(208+major*8+b,fg,bg)
    for b in range(8):
        curses.init_pair(224+b,7 if colors[b] in (0,8,2) else 0,colors[b])
        curses.init_pair(232+b,14 if curses.COLORS>=16 else 6,colors[b])
    COLORED=True


def attr(kind,terrain=True):
    if not COLORED:return 0
    if kind.startswith('band'):
        a,b=map(int,kind[-2:])
        if not terrain:a=0 if a==0 else 7;b=0 if b==0 else 7
        return curses.color_pair(144+a*8+b)
    if kind.startswith(('contour','stream')):
        b=int(kind[-1])
        if kind.startswith('contour') and not terrain:return curses.color_pair(144+7*8+7)
        if not terrain:b=0 if b==0 else 7
        return curses.color_pair((232 if kind.startswith('stream') else 224)+b)|(curses.A_BOLD if kind.startswith('stream') else curses.A_DIM)
    major=kind.startswith('route');b=int(kind[-1])
    if not terrain:b=0 if b==0 else 7
    value=curses.color_pair(208+int(major)*8+b)
    return value if major or PALETTE[b] in (3,6,7) else value|curses.A_DIM


def clip(x,y,xx,yy,w,h):
    def code(a,b):return (1 if a<0 else 2 if a>=w else 0)|(4 if b<0 else 8 if b>=h else 0)
    a,b=code(x,y),code(xx,yy)
    for _ in range(8):
        if not(a|b):return x,y,xx,yy
        if a&b:return None
        outside=a or b
        if outside&8:nx=x+(xx-x)*(h-1-y)//(yy-y);ny=h-1
        elif outside&4:nx=x+(xx-x)*(-y)//(yy-y);ny=0
        elif outside&2:ny=y+(yy-y)*(w-1-x)//(xx-x);nx=w-1
        else:ny=y+(yy-y)*(-x)//(xx-x);nx=0
        if outside==a:x,y=nx,ny;a=code(x,y)
        else:xx,yy=nx,ny;b=code(xx,yy)
    return None


class Atlas:
    def __init__(self,directory):
        path=os.path.join(directory,'walk-layers.n8w')
        with open(path,'rb') as f:data=f.read()
        if data[:4]!=b'N8W1':raise ValueError('Bad Walk layer pack')
        p=marshal.loads(zlib.decompress(data[4:]));self.grids=p['grids'];self.roads=p['roads'];self.streams=p.get('streams');self.cache=OrderedDict();self.stats={}
        for layer in self.roads+([self.streams] if self.streams else []):
            coords=array('i');coords.frombytes(layer.pop('segments'))
            if sys.byteorder!='little':coords.byteswap()
            layer['coords']=coords

    @staticmethod
    def project(lon,lat,center,span,w,h):
        lat0,lon0=center;scale=(w-1)/span
        return ((w-1)/2+(lon-lon0)*111.32*math.cos(math.radians(lat0))*scale,(h-1)/2-(lat-lat0)*111.32*scale/2)

    def raster(self,center,span,w,h):
        lat,lon=center;dx=span/max(1,w-1)/(111.32*math.cos(math.radians(lat)));dy=span/max(1,w-1)/111.32
        samples=[]
        for g in reversed(self.grids):
            west,south,east,north=g['bbox'];rw,rh=g['width'],g['height'];unit=1<<20
            sx=round(dx/(east-west)*rw*unit);sy=round(dy/(north-south)*rh*unit)
            x0=round((lon-west)/(east-west)*rw*unit-(w-1)/2*sx);y0=round((north-lat)/(north-south)*rh*unit-(2*h-1)/2*sy)
            xs=[(x0+x*sx)//unit for x in range(w)];ys=[(y0+j*sy)//unit for j in range(2*h)]
            samples.append((g,xs,ys))
            if 0<=xs[0] and xs[-1]<rw and 0<=ys[0] and ys[-1]<rh:break
        rows=[];fine_rows=[];local=0;fallback=0;unknown=0
        for j in range(2*h):
            row=bytearray([7])*w;fine=bytearray([255])*w;covered=bytearray(w)
            for g,xs,ys in samples:
                y=ys[j]
                if not 0<=y<g['height']:continue
                offset=y*g['width'];data=g['pixels'];rw=g['width'];is_local=g['heights']
                for x,xx in enumerate(xs):
                    if not covered[x] and 0<=xx<rw:
                        row[x]=data[offset+xx];covered[x]=1
                        if is_local:
                            local+=1
                            if 'fine' in g:fine[x]=g['fine'][offset+xx]
                        else:fallback+=1
            unknown+=w-sum(covered);rows.append(row);fine_rows.append(fine)
        return rows,fine_rows,dict(local=local,fallback=fallback,unknown=unknown,samples=w*h*2)

    def road_cells(self,center,span,w,h,streams=False):
        if span>500:return {},dict(road_candidates=0,road_segments=0,road_cells=0)
        lat,lon=center;scale=(w-1)/span;unit=1<<16
        sx=round(111.32*math.cos(math.radians(lat))*scale/100000*unit);sy=round(111.32*scale/200000*unit)
        lon0,lat0=round(lon*100000),round(lat*100000);cx=(w-1)*unit//2;cy=(h-1)*unit//2
        west,east=lon0-cx//max(1,sx),lon0+cx//max(1,sx);south,north=lat0-cy//max(1,sy),lat0+cy//max(1,sy)
        cells={};candidate=0;segments=0
        layers=((0,self.streams),) if streams and self.streams else (() if streams else (enumerate(self.roads) if span<=5 else ((1,self.roads[1]),)))
        for major,layer in layers:
            tile=layer['tile'];ids=set();index=layer['index'];coords=layer['coords']
            for by in range(south//tile,north//tile+1):
                for bx in range(west//tile,east//tile+1):ids.update(index.get((bx,by),()))
            candidate+=len(ids)
            for i in ids:
                offset=i*4;a,b,c,d=coords[offset:offset+4]
                if max(a,c)<west or min(a,c)>east or max(b,d)<south or min(b,d)>north:continue
                segments+=1
                x=(cx+(a-lon0)*sx+unit//2)//unit;y=(cy-(b-lat0)*sy+unit//2)//unit
                xx=(cx+(c-lon0)*sx+unit//2)//unit;yy=(cy-(d-lat0)*sy+unit//2)//unit
                bounds=clip(x,y,xx,yy,w,h)
                if bounds is None:continue
                x,y,xx,yy=bounds;dx,dy=abs(xx-x),abs(yy-y);err=dx-dy
                char='─' if dx>dy*2 else '│' if dy>dx*2 else '/' if (xx-x)*(yy-y)<0 else chr(92)
                xstep=1 if x<xx else -1;ystep=1 if y<yy else -1
                while True:
                    cells[x,y]=(char,major)
                    if x==xx and y==yy:break
                    twice=err*2
                    if twice>-dy:err-=dy;x+=xstep
                    if twice<dx:err+=dx;y+=ystep
        return cells,dict(road_candidates=candidate,road_segments=segments,road_cells=len(cells))

    def background(self,center,span,w,h,roads):
        if not 0<span<=48000:raise ValueError('Map span must be <=48000 km')
        key=(tuple(center),span,w,h,roads)
        if key in self.cache:
            result,stats=self.cache[key];self.cache.move_to_end(key);self.stats=dict(stats,cache='ram');return result
        rows,fine,stats=self.raster(center,span,w,h);cells,road_stats=self.road_cells(center,span,w,h) if roads else ({},dict(road_candidates=0,road_segments=0,road_cells=0))
        water,_=self.road_cells(center,span,w,h,streams=True) if span<=5 else ({},{})
        interval=5 if span<=2.5 else 10 if span<=5 else 25
        stats['interval']=interval;stats['stream_cells']=len(water)
        stats.update(road_stats);stats['profile']='walk streets' if span<=5 else 'major routes';runs=[]
        for y in range(h):
            a,b=rows[2*y:2*y+2];start=0;previous=None
            for x in range(w):
                road=cells.get((x,y))
                value=(road[0],ROADS[road[1]][b[x]]) if road else (' ' if a[x]==b[x] else '▀',BANDS[a[x]][b[x]])
                stream=water.get((x,y))
                if stream:value=(stream[0],'stream%d'%b[x])
                if previous is not None and value!=previous:runs.append((y,start,x,*previous));start=x
                previous=value
            runs.append((y,start,w,*previous))
        result=(runs,['Walk indexed bands']);self.cache[key]=(result,stats)
        if len(self.cache)>8:self.cache.popitem(last=False)
        self.stats=dict(stats,cache='miss');return result

    def description(self):
        s=self.stats
        if not s:return 'Local heights; regional land/water fallback'
        percent=round(100*s['local']/max(1,s['samples']))
        return 'Local25m / regional elevation classes; %d%% local coverage'%percent
