#!/usr/bin/env python3
"""Local terrain camera scout. No saved desktop preferences or device access."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import selectors
import struct
import sys
import termios
import tty
import zlib

from geometry import Camera, Vec, render
from model_scene import view
from landscape_detail import Nature
from lighting import environment
from input import Input
from terminal import measure
from build_trace import Trace


def adjust(camera, key, step=150):
    """Movement is in camera-local horizontal axes; angles are radians."""
    x,y,z=camera.origin.x,camera.origin.y,camera.origin.z
    forward=(math.sin(camera.yaw),math.cos(camera.yaw))
    right=(math.cos(camera.yaw),-math.sin(camera.yaw))
    if key in ('w','s','a','d'):
        axis=forward if key in ('w','s') else right
        amount=step*(1 if key in ('w','d') else -1)
        return replace(camera,origin=Vec(x+axis[0]*amount,y,z+axis[1]*amount))
    if key in ('r','f'):return replace(camera,origin=Vec(x,y+step*(1 if key=='r' else -1),z))
    if key in ('left','right'):return replace(camera,yaw=(camera.yaw+math.radians(2)*(1 if key=='right' else -1)+math.pi)%math.tau-math.pi)
    if key in ('up','down'):return replace(camera,elevation=max(-1.4,min(1.4,camera.elevation+math.radians(2)*(1 if key=='down' else -1))))
    if key in ('+','=','-'):
        factor=.9 if key in ('+','=') else 1/.9
        span=max(100,min(100000,camera.span_y*factor))
        return replace(camera,span_y=span,span_x=camera.span_x*span/camera.span_y)
    return camera


def ansi(cells,width,height):
    out=[];style=None
    for y in range(height):
        out.append(f'\x1b[{y+2};1H')
        for x in range(width):
            char,color=cells.get((x,y),(' ',(1<<48)))
            if color!=style:
                fg=(color>>24)&0xffffff;bg=color&0xffffff
                out.append(f'\x1b[38;2;{fg>>16};{(fg>>8)&255};{fg&255};48;2;{bg>>16};{(bg>>8)&255};{bg&255}m');style=color
            out.append(char)
    out.append('\x1b[0m');return ''.join(out)


def capture(directory,camera,cells,width,height,mode,shadows,nature):
    """Capture completed pixels and their exact camera, never pending controls."""
    directory.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-%fZ')
    target=directory/('vantage-'+stamp)
    # A dependency-free half-block raster. ANSI companion retains exact glyphs.
    pixels=bytearray(width*height*2*3)
    for y in range(height):
        for x in range(width):
            char,c=cells.get((x,y),(' ',1<<48));fg=(c>>24)&0xffffff;bg=c&0xffffff
            upper,lower=(bg,fg) if char=='▄' else (fg,bg) if char=='▀' else (bg,bg)
            if char not in (' ','▄','▀'):lower=fg
            for yy,value in ((2*y,upper),(2*y+1,lower)):
                at=(yy*width+x)*3;pixels[at:at+3]=bytes((value>>16,(value>>8)&255,value&255))
    def chunk(kind,data):return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    rows=b''.join(b'\0'+pixels[y*width*3:(y+1)*width*3] for y in range(height*2))
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',width,height*2,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')
    target.with_suffix('.png').write_bytes(png)
    metadata={'version':1,'camera':asdict(camera),'viewport':{'columns':width,'scene_rows':height,'sample_aspect':width/(height*2)},'lighting':mode,'shadows':shadows,'nature':nature._asdict(),'angles_degrees':{'yaw':math.degrees(camera.yaw),'elevation_down':math.degrees(camera.elevation)},'coordinates':'Renderer local meters: x east, y elevation, z north; see data/tahoma-3dep.json for DEM bounds. Not surveyed GPS.','png':'Half-block color raster; non-block glyphs reduced to a colored sample. ANSI preserves exact glyphs.','dem':json.loads(Path(__file__).with_name('data').joinpath('tahoma-3dep.json').read_text())}
    from scenery_geo import reference,kml
    metadata['geographic_reference']=reference(camera)
    target.with_suffix('.kml').write_text(kml({'Captured vantage':camera}))
    target.with_suffix('.json').write_text(json.dumps(metadata,indent=2)+'\n')
    target.with_suffix('.ansi').write_text('\x1b[2J'+ansi(cells,width,height)+'\n')
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    vantage=parser.add_mutually_exclusive_group()
    vantage.add_argument('--view',type=Path,help='restore a captured vantage JSON')
    vantage.add_argument('--preset',choices=('wide','elevated','valley'),help='start from a selected saved composition')
    parser.add_argument('--captures',type=Path,default=Path(__file__).with_name('artifacts')/'vantages')
    parser.add_argument('--shadows',action='store_true',help='slower, full terrain shadows')
    args=parser.parse_args()
    if not (sys.stdin.isatty() and sys.stdout.isatty()):parser.error('run in an interactive terminal')
    width,rows=measure(sys.stdout.fileno());height=max(1,rows-3)
    initial=view(1,False,width/(height*2),nature=Nature(seed=12345))
    camera=initial.camera;mode='day';shadows=args.shadows;nature=Nature(seed=12345)
    if args.view or args.preset:
        saved=json.loads(args.view.read_text()) if args.view else json.loads(Path(__file__).with_name('data').joinpath('camera-presets.json').read_text())[args.preset]
        c=saved['camera'];camera=Camera(**{**c,'origin':Vec(*c['origin'])})
        mode=saved['lighting'];shadows=saved['shadows'];nature=Nature(**{**saved['nature'],'scenery':tuple(saved['nature']['scenery']) if saved['nature'].get('scenery') else None})
        # Keep vertical field of view; adapt to this terminal's current aspect.
        camera=replace(camera,span_x=camera.span_y*width/(height*2))
    reset=camera;step=150;decoder=Input();shown=None;pending=None;requested=None;notice='';dirty=True;stopping=False
    pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='camera-scout');trace=None
    fd=sys.stdin.fileno();previous=termios.tcgetattr(fd);selector=selectors.DefaultSelector()
    try:
        tty.setraw(fd);selector.register(fd,selectors.EVENT_READ)
        sys.stdout.write('\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[2J');sys.stdout.flush()
        while not stopping:
            size=measure(sys.stdout.fileno());rows=size.rows;new=(size.columns,max(1,size.rows-3))
            if new!=(width,height):
                width,height=new;camera=replace(camera,span_x=camera.span_y*width/(height*2));dirty=True
                sys.stdout.write('\x1b[2J')
            key=(camera,width,height,mode,shadows,nature)
            if pending is not None and pending.done():
                cells,_=pending.result();shown=(requested,cells);pending=None
                sys.stdout.write(ansi(cells,requested[1],requested[2]));dirty=True
            if pending is None and (shown is None or shown[0]!=key):
                requested=key;trace=Trace()
                def build(request):
                    c,w,h,m,s,n=request
                    scene=replace(view(1,False,w/(h*2),nature=n),camera=c)
                    return render(scene,w,h,environment=environment(35000 if m=='night' else 0),cast_shadows=s,season=n.season,grid_strength=n.grid)
                pending=pool.submit(trace.run,build,requested);dirty=True
            if dirty:
                c=shown[0][0] if shown else camera
                label=f' {"rendering" if pending else "ready"} | x {c.origin.x:.0f} y {c.origin.y:.0f} z {c.origin.z:.0f} m | yaw {math.degrees(c.yaw):.1f} tilt {math.degrees(c.elevation):.1f} | step {step}'
                help=' WASD move | arrows look | R/F height | +/- zoom | [/] step'
                footer=notice or ' P capture | N day/night | 0 reset | Q quit'
                for row,text in ((1,label),(rows-1,help),(rows,footer)):
                    sys.stdout.write(f'\x1b[{max(1,row)};1H\x1b[0;97;40m'+text[:width].ljust(width))
                sys.stdout.flush();dirty=False
            events=selector.select(.05)
            keys=decoder.feed(os.read(fd,4096) if events else b'',expire=not events)
            for event in keys:
                if event[0]!='key':continue
                k=event[1].lower()
                if k in ('q','\x03','\x1b'):stopping=True;break
                if k=='p':
                    if shown:
                        ck,cells=shown;path=capture(args.captures,ck[0],cells,ck[1],ck[2],ck[3],ck[4],ck[5]);notice=' Saved '+str(path)+'.png / .json / .ansi'
                    else:notice=' Wait for the first view before capturing.'
                elif k=='n':mode='night' if mode=='day' else 'day'
                elif k=='0':camera=replace(reset,span_x=reset.span_y*width/(height*2))
                elif k=='[':step=max(10,step//2)
                elif k==']':step=min(5000,step*2)
                else:camera=adjust(camera,k,step)
                dirty=True
    finally:
        if trace:trace.cancel()
        selector.close();termios.tcsetattr(fd,termios.TCSADRAIN,previous)
        sys.stdout.write('\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l');sys.stdout.flush()
        pool.shutdown(wait=True,cancel_futures=True)
    if shown and notice.startswith(' Saved '):print(notice.strip())


if __name__=='__main__':main()
