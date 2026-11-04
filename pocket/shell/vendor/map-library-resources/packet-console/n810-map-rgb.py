"""RGB map surfaces with local elevation contrast and changed-cell output."""
import importlib.util,os,sys
from collections import OrderedDict
from pathlib import Path

LOW=(28,57,48);HIGH=(153,157,101);WATER=(24,62,82);LAND=(40,64,51)
CREEK=(72,198,221);TRACK=(235,157,130)
REGIONAL=(WATER,(53,87,58),(86,105,65),(119,116,76),(140,117,90),(156,137,116),(183,178,162),LAND)

def enabled():
    if os.environ.get('N810_MAP_RGB')=='0' or not sys.stdout.isatty():return False
    try:return 'vt.rgb=1' in Path('/proc/cmdline').read_text().split()
    except OSError:return os.environ.get('COLORTERM') in ('truecolor','24bit')

def blend(a,b,t):return tuple(round(x+(y-x)*t) for x,y in zip(a,b))

def band_color(height,low,high):return blend(LOW,HIGH,max(0,min(1,(height-low)/max(5,high-low))))

def background(atlas,center,span,w,h,roads,terrain=True):
    key=(tuple(center),span,w,h,roads,terrain)
    cache=getattr(atlas,'rgb_cache',None)
    if cache is None:cache=atlas.rgb_cache=OrderedDict()
    if key in cache:
        value=cache[key];cache.move_to_end(key);return value
    rows,fine,stats=atlas.raster(center,span,w,h)
    interval=5 if span<=2.5 else 10 if span<=5 else 25
    values=[(v-1)*5 for row in fine for v in row if v!=255]
    low=(min(values)//interval)*interval if values else 0
    high=((max(values)//interval)+1)*interval if values else interval
    color_cache={}
    def color(kind,value):
        k=(kind,value)
        if k not in color_cache:
            if kind==0:c=WATER
            elif not terrain:c=LAND
            elif value==255:c=REGIONAL[kind]
            else:
                height=(value-1)*5;c=band_color((height//interval)*interval,low,high)
                if span>5:
                    level=1+sum(height>=v for v in (200,500,1000,1800,2800))
                    c=blend(REGIONAL[level],c,max(0,(20-span)/15))
            color_cache[k]=c
        return color_cache[k]
    lines,_=atlas.road_cells(center,span,w,h) if roads else ({},{})
    streams,_=atlas.road_cells(center,span,w,h,streams=True) if span<=5 else ({},{})
    frame=[]
    for y in range(h):
        for x in range(w):
            a=color(rows[y*2][x],fine[y*2][x]);b=color(rows[y*2+1][x],fine[y*2+1][x])
            char=' ' if a==b else '▀';fg=a
            if (x,y) in lines:char=lines[x,y][0];fg=(218,222,207)
            if (x,y) in streams:char=streams[x,y][0];fg=CREEK
            frame.append((char,fg,b))
    coverage=round(100*stats['local']/max(1,stats['samples']))
    text=('%d–%d m / %d m bands · %d%% local heights'%(low,high,interval,coverage)) if values else 'Regional heights: <200 / 500 / 1000 / 1800 / 2800+ m'
    if span>=20:text='Regional elevation bands: <200 / 500 / 1000 / 1800 / 2800+ m'
    if not values and not stats['fallback']:text='No offline elevation coverage'
    if values and coverage<100 and span<20:text+=' · rest regional classes'
    if not terrain:text='Flat land/water · terrain OFF'
    value=(tuple(frame),text);cache[key]=value
    if len(cache)>8:cache.popitem(last=False)
    return value

class Surface:
    def __init__(self):self.previous=None;self.geometry=None;self.last_bytes=0
    def draw(self,frame,overlays,x0,y0,w,h,force=False):
        cells=list(frame)
        for (x,y),mark in overlays.items():
            char,fg=mark[:2]
            if 0<=x<w and 0<=y<h:
                _,_,bg=cells[y*w+x]
                if len(mark)>2:bg=mark[2]
                cells[y*w+x]=(char,fg,bg)
        geometry=(x0,y0,w,h)
        previous=None if force or geometry!=self.geometry else self.previous
        chunks=[]
        for y in range(h):
            x=0
            while x<w:
                i=y*w+x
                if previous is not None and cells[i]==previous[i]:x+=1;continue
                start=x;char,fg,bg=cells[i];text=[]
                while x<w:
                    j=y*w+x;c,f,b=cells[j]
                    if f!=fg or b!=bg or (previous is not None and cells[j]==previous[j]):break
                    text.append(c);x+=1
                weight='22'
                chunks.append('\x1b[%d;%dH\x1b[%sm\x1b[38;2;%d;%d;%dm\x1b[48;2;%d;%d;%dm%s'%((y0+y+1,x0+start+1,weight)+fg+bg+(''.join(text),)))
        if chunks:
            data='\x1b7'+''.join(chunks)+'\x1b8';sys.stdout.write(data);sys.stdout.flush();self.last_bytes=len(data.encode())
        else:self.last_bytes=0
        self.previous=cells;self.geometry=geometry

def atlas(directory):
    spec=importlib.util.spec_from_file_location('rgb_walk_atlas',Path(__file__).with_name('n810-walk-map.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m.Atlas(directory)

def trail(points,project,w,h,clip):
    """Thin interpolated trail; don't join fixes across gaps over two minutes."""
    result={};points=list(points)
    for a,b in zip(points,points[1:]):
        if a.get('time') and b.get('time') and abs(b['time']-a['time'])>120:continue
        if abs(a['lon']-b['lon'])>180:continue
        x,y=map(round,project(a));xx,yy=map(round,project(b));bounds=clip(x,y,xx,yy,w,h)
        if bounds is None:continue
        x,y,xx,yy=bounds;dx,dy=abs(xx-x),abs(yy-y);error=dx-dy
        char='─' if dx>dy*2 else '│' if dy>dx*2 else '/' if (xx-x)*(yy-y)<0 else chr(92)
        sx=1 if x<xx else -1;sy=1 if y<yy else -1
        while True:
            result[x,y]=(char,TRACK)
            if x==xx and y==yy:break
            twice=error*2
            if twice>-dy:error-=dy;x+=sx
            if twice<dx:error+=dx;y+=sy
    return result
