#!/usr/bin/env python3
"""Read-only opt-in map trial using saved walks; no radio or telemetry access."""
import argparse, curses, io, json, math, resource, sys, time
from pathlib import Path
from contextlib import redirect_stdout
import importlib.util

BASE=Path(__file__).resolve().parent
def load(name,file):
    spec=importlib.util.spec_from_file_location(name,BASE/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
model=load('trial_map','n810-map-next.py')
history=load('trial_history','n810-walk-history.py')
palette=load('trial_palette','n810-map-style.py')
NAVIGATION={ord('+'),ord('='),ord('-'),curses.KEY_LEFT,curses.KEY_RIGHT,curses.KEY_UP,curses.KEY_DOWN}

def queued_keys(win,first):
    """Collapse queued navigation before rendering; other keys form a barrier."""
    keys=[first]
    if first not in NAVIGATION:return keys
    win.timeout(0)
    try:
        while len(keys)<128:
            key=win.getch()
            if key==-1:break
            keys.append(key)
            if key not in NAVIGATION:break
    finally:win.timeout(250)
    return keys

def fitted(track,w,h):
    if not track:return (5.5355,5.5655),2
    south=min(p['lat'] for p in track);north=max(p['lat'] for p in track)
    west=min(p['lon'] for p in track);east=max(p['lon'] for p in track)
    center=((south+north)/2,(west+east)/2)
    span=max(.5,(east-west)*111.32*math.cos(math.radians(center[0]))*1.2,(north-south)*111.32*max(1,w-1)/max(1,h-1)/2*1.2)
    return center,span

def marks(engine,view,walk,variant):
    result=model.Overlay(view.width,view.height)
    track=walk.get('track',[])
    rgb=engine.style=='rgb'
    cells=engine.rgb.trail(track,lambda p:view.project(p['lon'],p['lat']),view.width,view.height,engine.geometry.clip)
    for (x,y),(char,fg) in cells.items():
        cell=(char,fg) if variant==0 else (char,(246,243,222) if variant==1 else (107,247,224),(16,26,22))
        result.put(x,y,cell if rgb else (char,palette.ink(72)|curses.A_BOLD),0)
    for p in walk.get('probes',[]):
        position=p['position'];x,y=map(round,view.project(position['lon'],position['lat']))
        char='R' if p.get('return_path') else 'I' if p.get('internet_reports') else 'P'
        cell=(char,(16,26,22),(153,224,244) if char=='I' else (121,230,158) if char=='R' else (246,243,222)) if rgb else (char,palette.ink(73 if char=='R' else 7)|curses.A_BOLD)
        result.put(x,y,cell,10 if char=='P' else 11)
    if track:
        x,y=map(round,view.project(track[-1]['lon'],track[-1]['lat']))
        result.put(x,y,('@',(16,26,22),(246,243,222)) if rgb else ('@',palette.ink(7)|curses.A_BOLD),20)
    return result

def benchmark(args,walk):
    started=time.monotonic();engine=model.Engine(args.maps,args.style);init=time.monotonic()-started
    class Sink:
        def __init__(self):self.bytes=0
        def addnstr(self,y,x,text,length,attr):self.bytes+=len(text.encode())+16
    records=[]
    for span in (524,262,131,65.5,32.8,16.4,8.19,4.09,2.05,1.02,.51):
        view=model.Viewport((5.5355,5.5655),span,100,23)
        start=time.monotonic();engine.prepare(view);cold=time.monotonic()-start
        start=time.monotonic();engine.prepare(view);cached=time.monotonic()-start
        overlays=marks(engine,view,walk,args.variant);sink=Sink();buffer=io.StringIO();engine.invalidate()
        with redirect_stdout(buffer):
            engine.draw(overlays,win=sink)
            first=len(buffer.getvalue().encode()) if args.style=='rgb' else sink.bytes
            buffer.seek(0);buffer.truncate();sink.bytes=0
            engine.draw(overlays,win=sink)
            repeat=len(buffer.getvalue().encode()) if args.style=='rgb' else sink.bytes
        records.append(dict(span=span,cold_seconds=cold,cached_seconds=cached,first_bytes=first,repeat_bytes=repeat,stats=engine.stats))
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform=='darwin':peak//=1024
    result=dict(style=args.style,initialization_seconds=init,peak_kib=peak,track_fixes=len(walk.get('track',[])),records=records)
    print(json.dumps(result,indent=2))

def run(win,args,walk):
    try:curses.curs_set(0)
    except curses.error:pass
    palette.init_screen(win);engine=model.Engine(args.maps,args.style,attribute=palette.cell_attr)
    if args.style=='rgb' and not engine.rgb.enabled():raise RuntimeError('RGB trial requires an RGB-capable console; use --style ansi')
    visibility=load('trial_visible','n810-ui-visible.py');visibility.setup()
    h,w=win.getmaxyx();center,span=fitted(walk.get('track',[]),w,max(1,h-6))
    terrain=roads=True;variant=args.variant;dirty=True;size=None;was_visible=True
    win.timeout(250)
    while True:
        visible=visibility.visible()
        if visible and not was_visible:dirty=True;size=None
        was_visible=visible
        key=win.getch()
        h,w=win.getmaxyx();mh=max(1,h-6)
        if size!=(h,w):win.erase();engine.invalidate();dirty=True;size=(h,w)
        for key in queued_keys(win,key):
            if key==ord('q'):return
            if key in (ord('+'),ord('=')):span=max(.5,span/2);dirty=True
            elif key==ord('-'):span=min(48000,span*2);dirty=True
            elif key==ord('f'):center,span=fitted(walk.get('track',[]),w,mh);dirty=True
            elif key==ord('t'):terrain=not terrain;dirty=True
            elif key==ord('r'):roads=not roads;dirty=True
            elif key==ord('v'):variant=(variant+1)%3;dirty=True
            elif key in (curses.KEY_LEFT,curses.KEY_RIGHT,curses.KEY_UP,curses.KEY_DOWN):
                lat,lon=center
                if key in (curses.KEY_LEFT,curses.KEY_RIGHT):lon+=span*.2/(111.32*max(.01,math.cos(math.radians(lat))))*(-1 if key==curses.KEY_LEFT else 1)
                else:lat+=span*.2/111.32*(1 if key==curses.KEY_UP else -1)
                center=(max(-80,min(80,lat)),(lon+180)%360-180);dirty=True
        if not dirty or not visible:continue
        view=model.Viewport(center,span,w,mh);_,legend=engine.prepare(view,terrain,roads)
        lines={0:'MAP NEXT TRIAL | read-only saved walk | %s | %.3g km'%(args.style,span),
               1:'t terrain %s | r roads %s | %d fixes | overlay %d'%(terrain,roads,len(walk.get('track',[])),variant),
               2:'Arrows pan  +/- zoom  f fit  t terrain  r roads  v overlay style  q close',
               h-3:'P submitted  R recorded return  I Internet  @ end | no radio connection',
               h-2:legend,h-1:'Map: OpenStreetMap contributors | Elevation: USGS 3DEP | experimental engine'}
        for y,text in lines.items():
            win.move(y,0);win.clrtoeol()
            try:win.addnstr(y,0,text,max(0,w-1))
            except curses.error:pass
        overlays=marks(engine,view,walk,variant)
        if args.style=='ansi':engine.draw(overlays,0,3,win=win)
        win.refresh()
        if args.style=='rgb':engine.draw(overlays,0,3)
        dirty=False

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--maps',default=str(BASE/'maps'));p.add_argument('--style',choices=['ansi','rgb'],default='ansi')
    p.add_argument('--walks',default='~/.local/state/n810-aprs/walks');p.add_argument('--callsign',default='N0CALL')
    p.add_argument('--variant',type=int,choices=[0,1,2],default=1);p.add_argument('--benchmark',action='store_true')
    args=p.parse_args();walks=history.load(Path(args.walks).expanduser(),args.callsign)
    walk=walks[0] if walks else dict(track=[],probes=[])
    if args.benchmark:benchmark(args,walk)
    else:curses.wrapper(run,args,walk)

if __name__=='__main__':main()
