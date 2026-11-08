#!/usr/bin/env python3
"""DoomGeneric/Freedoom app on the existing Current World Host and RGB layer."""
import argparse, ctypes as C, json, mmap, os, resource, select, subprocess, sys, tempfile, termios, time, tty
from pathlib import Path
from collections import deque
HERE=Path(__file__).resolve().parent
FRAMEWORK=HERE.parents[1]
sys.path.insert(0,str(FRAMEWORK))
from core import Host,Window,Cell
from input import Input
from terminal import measure,Presentation


def cell_aspect(fd=0):
    """Use terminal pixel geometry when supplied; otherwise use the shared 1:2 cell convention."""
    import fcntl,struct
    try:
        rows,columns,pixels_w,pixels_h=struct.unpack('HHHH',fcntl.ioctl(fd,termios.TIOCGWINSZ,bytes(8)))
        if rows and columns and pixels_w and pixels_h:
            ratio=pixels_w*rows/(pixels_h*columns)
            if .1<=ratio<=2:return ratio
    except (OSError,ValueError):pass
    return .5


def fitted_viewport(width,height,aspect):
    """Fit Doom's intended 4:3 display, with character cells of physical aspect."""
    if width<1 or height<1 or not .1<=aspect<=2:raise ValueError('invalid Doom viewport')
    ratio=(4/3)/aspect
    game_w=min(width,max(1,int(height*ratio)))
    game_h=min(height,max(1,round(game_w/ratio)))
    return ((width-game_w)//2,(height-game_h)//2,game_w,game_h)


def fit_cells(codes,source_w,source_h,width,height,rectangle):
    """Scale bounded RGB half samples into a complete, opaque window body."""
    left,top,game_w,game_h=rectangle
    if len(codes)!=source_w*source_h or min(source_w,source_h,game_w,game_h)<1:
        raise ValueError('invalid Doom source samples')
    if left<0 or top<0 or left+game_w>width or top+game_h>height:
        raise ValueError('Doom fit outside window body')
    black=Cell('▀',1<<48);blank=(black,)*width
    xs=[min(source_w-1,(2*x+1)*source_w//(2*game_w)) for x in range(game_w)]
    rows={};output=[]
    for y in range(height):
        if not top<=y<top+game_h:
            output.extend(blank);continue
        yy=y-top
        upper=min(source_h*2-1,(4*yy+1)*source_h//(2*game_h))
        lower=min(source_h*2-1,(4*yy+3)*source_h//(2*game_h))
        key=upper,lower
        row=rows.get(key)
        if row is None:
            a=(upper//2)*source_w;b=(lower//2)*source_w
            shift_a=24 if upper%2==0 else 0;shift_b=24 if lower%2==0 else 0
            # Construct at most source_w Cells, then repeat immutable references
            # across the enlarged row. Aligned halves already have packed RGB.
            if a==b and shift_a==24 and shift_b==0:
                samples=tuple(Cell('▀',(1<<48)|(codes[a+x]&((1<<48)-1))) for x in range(source_w))
            elif upper==lower:
                samples=tuple(Cell('▀',(1<<48)|(((codes[a+x]>>shift_a)&0xffffff)*0x1000001)) for x in range(source_w))
            else:
                samples=tuple(Cell('▀',(1<<48)|(((codes[a+x]>>shift_a)&0xffffff)<<24)|((codes[b+x]>>shift_b)&0xffffff)) for x in range(source_w))
            game=samples if game_w==source_w else tuple(samples[x] for x in xs)
            row=(black,)*left+game+(black,)*(width-left-game_w)
            rows[key]=row
        output.extend(row)
    return tuple(output)


class Frame(C.Structure):
    _fields_=[('seq',C.c_uint32),('number',C.c_uint32),('ns',C.c_uint64),('input',C.c_uint32),('reserved',C.c_uint32),('pixels',C.c_uint32*(320*200))]

class DoomApp:
    """One owner, one native child, one overwritten latest frame; no frame queue."""
    def configure_bridge(self):
        """Validate optional presentation ABI before creating any owned resources."""
        pass

    def __init__(self,host,state,name='Doom / Freedoom',resource_root=None):
        self.host=host;self.state=state;self.name=name;self.previous=();self.dimensions=None;self.last=0
        self.resource_root=Path(resource_root) if resource_root is not None else HERE
        self.lib=C.CDLL(str(self.resource_root/'build/bridge.so'))
        self.lib.bridge_now_ns.restype=C.c_uint64
        if self.lib.frame_size()!=C.sizeof(Frame):raise ValueError("Doom frame ABI mismatch; rebuild the adapter")
        self.lib.snapshot.argtypes=[C.POINTER(Frame),C.POINTER(Frame)]
        self.lib.convert.argtypes=[C.POINTER(Frame),C.POINTER(C.c_uint64),C.c_int,C.c_int]
        self.configure_bridge()
        self.file=open(state/'frame','w+b');self.file.truncate(C.sizeof(Frame))
        self.mapping=mmap.mmap(self.file.fileno(),C.sizeof(Frame));self.shared=Frame.from_buffer(self.mapping);self.frame=Frame()
        self.log=open(state/'engine.log','wb')
        wad=self.resource_root/'vendor/freedoom-0.13.0/freedoom1.wad'
        try:self.child=subprocess.Popen([str(self.resource_root/'build/doom-engine'),'-iwad',str(wad),'-config',str(state/'doom.cfg'),'-savedir',str(state),'-warp','1','1','-skill','2','-nosound'],stdin=subprocess.PIPE,stdout=self.log,stderr=subprocess.STDOUT,env=dict(os.environ,DOOM_FRAME=str(state/'frame')),cwd=state)
        except OSError:
            self.log.close();del self.shared;self.mapping.close();self.file.close();raise
        os.set_blocking(self.child.stdin.fileno(),False)
        self._init_input()
        self.stats=dict(sampled=0,skipped=0,conversion_seconds=0,damage_seconds=0,snapshot_seconds=0)
    def _init_input(self):
        self.mouse_buttons=0;self.held={};self.edge_keys={};self.input_count=0;self.pending={};self.latencies=deque(maxlen=4096)
    def send(self,key,pressed):
        try:os.write(self.child.stdin.fileno(),bytes((pressed,key)))
        except (BlockingIOError,BrokenPipeError):return False
        if pressed:self.input_count+=1;self.pending[self.input_count]=time.monotonic()
        if len(self.pending)>256:del self.pending[next(iter(self.pending))]
        return True
    def mouse(self,dx=0,dy=0,buttons=0):
        """One atomic, bounded input message; the engine owns Doom mouse semantics."""
        import struct
        dx=max(-32768,min(32767,int(dx)));dy=max(-32768,min(32767,int(dy)))
        try:os.write(self.child.stdin.fileno(),struct.pack('<BBhh',2,buttons&7,dx,dy))
        except (BlockingIOError,BrokenPipeError):return False
        self.mouse_buttons=buttons&7
        if dx or dy or buttons:
            self.input_count+=1;self.pending[self.input_count]=time.monotonic()
            if len(self.pending)>256:del self.pending[next(iter(self.pending))]
        return True
    @staticmethod
    def key_code(key):
        codes={'up':0xad,'w':0xad,'down':0xaf,'s':0xaf,'left':0xac,'right':0xae,'a':0xa0,'d':0xa1,' ':0xa3,'e':0xa2,'\r':13,'\n':13,'\x1b':27,'\t':9}
        return codes.get(key,ord(key) if len(key)==1 and ord(key)<128 else None)
    def key(self,key,now):
        code=self.key_code(key)
        if code is None:return
        if code not in self.held and self.send(code,1):self.held[code]=now+.22
        elif code in self.held and self.held[code] is not None:self.held[code]=now+.22
    def key_event(self,key,kind,now):
        code=self.key_code(key)
        if code is None or kind not in ('press','repeat','release'):return False
        if kind=='repeat':return key in self.edge_keys
        if kind=='press':
            if key in self.edge_keys:return True
            if code not in self.held and not self.send(code,1):return False
            self.edge_keys[key]=code;self.held[code]=None
        elif key in self.edge_keys:
            del self.edge_keys[key]
            if code not in self.edge_keys.values():
                # Leave a failed release due for retry on the existing poll.
                self.held[code]=now
                if self.send(code,0):del self.held[code]
        return True
    def release(self,now,all_keys=False):
        if all_keys:
            self.edge_keys.clear()
            if self.mouse_buttons:self.mouse()
        for key,due in tuple(self.held.items()):
            if all_keys or due is not None and now>=due:
                if self.send(key,0):del self.held[key]
                elif all_keys:self.held[key]=now
    def update(self):
        start=time.perf_counter();ok=self.lib.snapshot(C.byref(self.shared),C.byref(self.frame));self.stats['snapshot_seconds']+=time.perf_counter()-start
        w=self.host.window(self.name);dims=(max(1,w.w-2),max(1,w.h-2))
        rectangle=fitted_viewport(*dims,cell_aspect())
        if not ok or not self.frame.number or (self.frame.number==self.last and dims==self.dimensions and rectangle==getattr(self,'viewport',None)):return None
        if not self.host.shown(w) or w.rolled:return None
        self.stats['skipped']+=max(0,self.frame.number-self.last-1) if self.last else 0
        self.last=self.frame.number;self.stats['sampled']+=1
        width,height=dims
        source_w,source_h=min(160,rectangle[2]),min(100,rectangle[3])
        start=time.perf_counter();codes=(C.c_uint64*(source_w*source_h))();self.lib.convert(C.byref(self.frame),codes,source_w,source_h)
        cells=fit_cells(codes,source_w,source_h,width,height,rectangle)
        self.stats['conversion_seconds']+=time.perf_counter()-start
        start=time.perf_counter();changed=None if dims!=self.dimensions else [i for i,v in enumerate(cells) if v!=self.previous[i]]
        self.host.layer_patch(self.name,(0,0,width,height,cells),changed)
        self.previous=cells;self.dimensions=dims;self.viewport=rectangle
        self.stats['damage_seconds']+=time.perf_counter()-start
        return self.frame.number,self.frame.ns,self.frame.input
    def presented(self,frame,now):
        for number,started in tuple(self.pending.items()):
            if number<=frame[2]:self.latencies.append((now-started)*1000);del self.pending[number]
    def close(self):
        self.child.terminate()
        try:self.child.wait(timeout=2)
        except subprocess.TimeoutExpired:self.child.kill();self.child.wait()
        self.child.stdin.close();self.log.close();del self.shared;self.mapping.close();self.file.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend',choices=('native','python'),default='native')
    p.add_argument('--seconds',type=float,default=0,help='bounded local measurement run')
    p.add_argument('--metrics',type=Path);p.add_argument('--snapshot',type=Path)
    p.add_argument('--scripted-input',action='store_true',help='local benchmark turns/walks/fires')
    args=p.parse_args()
    if not sys.stdin.isatty():p.error('run in a terminal')
    cols,rows=measure(0);h=Host(cols,rows,[Window('Doom / Freedoom',2,2,min(82,cols-2),min(27,rows-3))],animate=False)
    h.background_enabled=False;h.shadow_enabled=False;h.window_opacity=1;h.show_clock=False;h.show_connectivity=False
    if args.backend=='native':h.enable_native(FRAMEWORK/'native/build/_cellengine.abi3.so')
    decoder=Input();presentation=Presentation();wm=False
    old=termios.tcgetattr(0);start=time.monotonic();cpu=time.process_time();count=bytes_out=0;composition=output_cost=0.;ages=deque(maxlen=10000);intervals=deque(maxlen=10000);last_present=None;active=None;active_wrote=False;completed=0;next_frame=start;next_script=start+2;script=0
    with tempfile.TemporaryDirectory(prefix='cw-doom-') as temporary:
        app=DoomApp(h,Path(temporary))
        try:
            tty.setraw(0);os.write(1,b'\x1b[?1049h\x1b[?25l\x1b[?1000h\x1b[?1002h\x1b[?1006h')
            running=True
            while running:
                now=time.monotonic()
                if args.seconds and now-start>=args.seconds:break
                if app.child.poll() is not None:raise RuntimeError((Path(temporary)/'engine.log').read_text())
                geometry=measure(0)
                if geometry!=(h.width,h.height):h.resize(*geometry)
                ready=select.select([0],[],[],max(0,min(.01,next_frame-now)))[0]
                events=decoder.feed(os.read(0,4096)) if ready else decoder.feed(b'',expire=True)
                for event in events:
                    if event[0]=='mouse':h.pointer(*event[1:]);continue
                    key=event[1]
                    if key=='\x03':running=False;break
                    if key=='\x1d':wm=not wm;app.release(now,True);continue
                    if wm:
                        if key=='q':running=False
                        elif key=='r':h.begin(True)
                        elif key=='m':h.begin(False)
                        elif key=='\r':h.finish(True)
                        elif key=='\x1b':h.finish(False)
                        elif key in ('left','right','up','down') and h.drag:
                            dx,dy=h.latest or (h.drag[2][0]-h.drag[1][0],h.drag[2][1]-h.drag[1][1]) if not h.drag[3] else (h.drag[2][2]-h.drag[1][2],h.drag[2][3]-h.drag[1][3])
                            mx,my={'left':(-1,0),'right':(1,0),'up':(0,-1),'down':(0,1)}[key];h.motion(dx+mx,dy+my)
                    else:app.key(key,now)
                if args.scripted_input and now>=next_script:
                    app.key(('right','w',' ','left','e')[script%5],now);script+=1;next_script=now+.3
                app.release(now)
                if now>=next_frame and not h.damage:
                    active=app.update();active_wrote=False;next_frame=now+1/35
                t=time.perf_counter();out,_,_=h.flush(4096,max_seconds=.008);composition+=time.perf_counter()-t
                text=presentation.write(out,not h.damage,time.monotonic())
                if text:
                    t=time.perf_counter();data=text.encode();offset=0
                    while offset<len(data):offset+=os.write(1,data[offset:])
                    output_cost+=time.perf_counter()-t;bytes_out+=len(data)
                    if active:active_wrote=True
                if active and not h.damage:
                    done=time.monotonic();completed+=1;count+=int(active_wrote);ages.append((app.lib.bridge_now_ns()-active[1])/1e6);app.presented(active,done)
                    if last_present is not None:intervals.append((done-last_present)*1000)
                    last_present=done;active=None
                if not h.window(app.name).opened:break
            if args.snapshot:
                # Export retained Host cells as a portable SVG, including actual window chrome.
                from html import escape
                parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{h.width*8}" height="{h.height*16}" viewBox="0 0 {h.width*8} {h.height*16}"><rect width="100%" height="100%" fill="#0a0a0a"/>']
                for i,cell in enumerate(h.front):
                    if cell is None:continue
                    x,y=(i%h.width)*8,(i//h.width)*16;c=cell.color
                    fg=(c>>24)&0xffffff if c>=1<<48 else 0xc0d0d0;bg=c&0xffffff if c>=1<<48 else 0x0a0a0a
                    parts.append(f'<rect x="{x}" y="{y}" width="8" height="16" fill="#{bg:06x}"/>')
                    if cell.char=='▀':parts.append(f'<rect x="{x}" y="{y}" width="8" height="8" fill="#{fg:06x}"/>')
                    else:parts.append(f'<text x="{x}" y="{y+13}" font-family="monospace" font-size="14" fill="#{fg:06x}">{escape(cell.char)}</text>')
                args.snapshot.write_text(''.join(parts)+'</svg>')
        finally:
            app.close();os.write(1,(presentation.close()+'\x1b[?1006l\x1b[?1002l\x1b[?1000l\x1b[?25h\x1b[?1049l').encode());termios.tcsetattr(0,termios.TCSANOW,old)
        elapsed=time.monotonic()-start
        def summary(values):
            values=sorted(values)
            return dict(n=len(values),p50=values[len(values)//2],p95=values[min(len(values)-1,int(len(values)*.95))],max=values[-1]) if values else dict(n=0)
        usage=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
        report=dict(wall_seconds=elapsed,backend_requested=args.backend,backend_observed=h.render_backend,host_dimensions=[h.width,h.height],viewport_cells=app.dimensions,engine_pixels=[320,200],frames_written=count,completed_updates=completed,completed_update_hz=completed/elapsed,changed_frame_write_hz=count/elapsed,output_bytes=bytes_out,composition_encode_seconds=composition,output_write_seconds=output_cost,parent_cpu_seconds=time.process_time()-cpu,engine_cpu_seconds=child.ru_utime+child.ru_stime,parent_peak_rss_bytes=usage.ru_maxrss*(1 if sys.platform=="darwin" else 1024),engine_peak_rss_bytes=child.ru_maxrss*(1 if sys.platform=="darwin" else 1024),frame_age_at_write_ms=summary(ages),update_interval_ms=summary(intervals),input_to_frame_write_ms=summary(app.latencies),adapter=app.stats,framework_sha256={name:__import__("hashlib").sha256((FRAMEWORK/name).read_bytes()).hexdigest() for name in ("core.py","native_cells.py","terminal.py","input.py","native/build/_cellengine.abi3.so")},build=json.loads((HERE/'build/identity.json').read_text()),limits='Counts completed Host composition + terminal writes, not display scanout FPS. PTY drain is not physical terminal presentation. Input latency ends at first written frame acknowledging engine input; does not assert visible motion. Terminal key releases inferred after 220 ms; initial OS repeat delay can interrupt held movement.')
        if args.metrics:args.metrics.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report))
if __name__=='__main__':main()
