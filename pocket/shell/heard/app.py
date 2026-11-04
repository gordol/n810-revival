#!/usr/bin/env python3
"""Opt-in real read-only Heard app using the retained window framework."""
import sys,time
_BOOT_START=time.perf_counter();_BOOT_CPU_START=time.thread_time()
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import sys
import termios
import time
import tty
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from core import Host, Window
from input import Input
from terminal import Presentation, measure
from provider import CatalogFile, DirectoryDB, Reader
from model import Model
from views import Views
_IMPORT_SECONDS=time.perf_counter()-_BOOT_START
_IMPORT_CPU_SECONDS=time.thread_time()-_BOOT_CPU_START


def layout(host):
    # Preferred widths stay bounded as the desktop grows.
    left,right = host.window('Heard'),host.window('Details')
    left.x=1;left.y=1;left.w=min(host.app_spec['views'][0]['preferred_cells'][0],max(20,host.width//3));left.h=min(host.app_spec['views'][0]['preferred_cells'][1],host.height-2)
    right.x=left.x+left.w+1;right.y=1;right.w=min(host.app_spec['views'][1]['preferred_cells'][0],host.width-right.x-1);right.h=left.h
    host.invalidate((0,0,host.width,host.height))


def make_host(width,height,ascii=False):
    spec=json.loads(Path(__file__).with_name('app.json').read_text())
    if spec['provider']!='HeardCatalog@1' or spec['capacity']!=128: raise ValueError('unsupported declaration')
    host=Host(width,height,[Window(v['name'],0,0,*v['preferred_cells']) for v in spec['views']],ascii=ascii,animate=False,move_mode='live',resize_mode='live')
    host.desktop_count=1;host.background_enabled=False;host.shadow_enabled=False;host.window_opacity=1;host.set_style('rounded');host.set_palette('paper')
    host.app_spec=spec
    layout(host);host.select('Heard')
    return host


def cli_error(message):
    print('Heard: '+message,file=sys.stderr);raise SystemExit(2)


def parse_args(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    values=dict(catalog=None,directory_db=None,interval=5.,ascii=False,metrics=None,run_seconds=None,native=None,touch_device=None,touch_calibration=None,touch_display=None,touch_rotation=0,glyph_font=None)
    types={'--catalog':Path,'--directory-db':Path,'--interval':float,'--metrics':Path,'--run-seconds':float,'--native':Path,'--touch-device':Path,'--touch-calibration':Path,'--touch-display':str,'--touch-rotation':int,'--glyph-font':Path}
    while argv:
        option=argv.pop(0)
        if option in ('--help','-h'):
            print('Read-only Heard app\n--catalog FILE | --directory-db FILE\n[--interval SECONDS] [--ascii] [--glyph-font PSF2] [--metrics FILE] [--run-seconds SECONDS] [--native LIBRARY]\n[--touch-device DEVICE --touch-calibration FILE --touch-display WIDTHxHEIGHT --touch-rotation 0]')
            raise SystemExit(0)
        if option=='--ascii':values['ascii']=True;continue
        if '=' in option:option,value=option.split('=',1)
        else:
            if option not in types or not argv:cli_error('unknown option or missing value: '+option)
            value=argv.pop(0)
        if option not in types:cli_error('unknown option: '+option)
        try:values[option[2:].replace('-','_')]=types[option](value)
        except ValueError:cli_error('invalid value for '+option)
    if bool(values['catalog'])==bool(values['directory_db']):cli_error('choose exactly one of --catalog or --directory-db')
    if values['interval']<=0 or values['run_seconds'] is not None and values['run_seconds']<=0:cli_error('durations must be positive')
    touch_flags=(values['touch_device'],values['touch_calibration'],values['touch_display'])
    if any(touch_flags) and not all(touch_flags):cli_error('touch requires device, calibration and physical display size')
    if values['touch_rotation'] not in (0,90,180,270):cli_error('touch rotation must be 0, 90, 180 or 270')
    return SimpleNamespace(**values)


def main():
    setup_started=time.perf_counter();setup_cpu=time.thread_time()
    args=parse_args()
    if not sys.stdin.isatty(): cli_error('run inside a terminal')
    dimensions=measure(sys.stdout.fileno())
    if dimensions.columns<70 or dimensions.rows<16: cli_error('use at least 70 columns by 16 rows')
    host=make_host(dimensions.columns,dimensions.rows-2,args.ascii)
    if args.glyph_font:
        try:
            from cell_text import load_psf
            host.set_glyphs(load_psf(args.glyph_font))
        except (OSError,ValueError) as error:cli_error('glyph font unavailable: '+str(error))
    if args.native:host.enable_native(args.native)
    touch=None
    if args.touch_device:
        try:
            from touch_evdev import TouchSource,display
            pixels=tuple(map(int,args.touch_display.lower().split('x')))
            if len(pixels)!=2:raise ValueError('touch display must be WIDTHxHEIGHT')
            touch=TouchSource(args.touch_device,args.touch_calibration,display(*pixels,args.touch_rotation),dimensions.columns,dimensions.rows)
        except (OSError,ValueError) as error:cli_error('touch unavailable: '+str(error))
    model=Model();views=Views(model,host);decoder=Input();presentation=Presentation()
    reader=Reader(CatalogFile(args.catalog) if args.catalog else DirectoryDB(args.directory_db,profile=bool(args.metrics),managed=True),max(.2,args.interval),profile=bool(args.metrics))
    selector=selectors.DefaultSelector();selector.register(sys.stdin,selectors.EVENT_READ);selector.register(reader.readable,selectors.EVENT_READ)
    if touch is not None:selector.register(touch,selectors.EVENT_READ)
    started=time.monotonic();cpu_started=time.process_time();old=termios.tcgetattr(sys.stdin);resized=False;stopped=False
    timings={'imports_cpu_ms':_IMPORT_CPU_SECONDS*1000,'bootstrap_cpu_ms':(time.thread_time()-setup_cpu)*1000,'view_cpu_ms':0,'compose_cpu_ms':0,'terminal_write_cpu_ms':0,'imports_ms':_IMPORT_SECONDS*1000,'bootstrap_ms':(time.perf_counter()-setup_started)*1000,'view_ms':0,'compose_ms':0,'terminal_write_ms':0} if args.metrics else None
    metrics=dict(size=[dimensions.columns,dimensions.rows],wakeups=0,frames=0,changed_cells=0,composed_cells=0,output_bytes=0,inputs=0,max_input_handler_ms=0,max_input_to_present_ms=0,touch_inputs=0,touch_error=None,touch_drops=0)
    def stop(*_):
        nonlocal stopped
        stopped=True;reader.refresh()
    def resize(*_):
        nonlocal resized
        resized=True;reader.refresh()
    previous={s:signal.signal(s,stop) for s in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP)}
    previous[signal.SIGWINCH]=signal.signal(signal.SIGWINCH,resize)
    status_cache=None;move_dx=move_dy=0;input_started=None
    try:
        tty.setcbreak(sys.stdin)
        sys.stdout.write('\x1b[?1049h\x1b[?25l\x1b[2J\x1b[?1002h\x1b[?1006h')
        while not stopped:
            now=time.monotonic()
            if args.run_seconds and now-started>=args.run_seconds: break
            if resized:
                resized=False;dimensions=measure(sys.stdout.fileno())
                if dimensions.columns>=70 and dimensions.rows>=16:
                    if touch is not None:touch.cancel(host);touch.resize(dimensions.columns,dimensions.rows)
                    host.resize(dimensions.columns,dimensions.rows-2);layout(host);status_cache=None
                    sys.stdout.write('\x1b[2J')
                elif touch is not None:
                    touch.cancel(host);selector.unregister(touch);touch.close();touch=None
                    metrics['touch_error']='terminal too small for touch'
            phase_start=time.perf_counter() if timings is not None else 0
            phase_cpu=time.thread_time() if timings is not None else 0
            views.update(time.time())
            if timings is not None:
                timings['view_ms']+=(time.perf_counter()-phase_start)*1000;timings['view_cpu_ms']+=(time.thread_time()-phase_cpu)*1000
            state=('RETAINED / '+model.error if model.error else model.source)+' | '+str(len(model.order))+' endpoints'
            # Catalog captured is read-state generation time; individual row.last is RX time.
            if model.captured: state+=' | catalog read '+model.captured
            if args.touch_device:state+=' | touch' if touch is not None else ' | touch off'
            footer='1 Heard  2 Details | Arrows / wheel | Tab window | R refresh | M move, Enter | Q quit'
            status=(state,footer,dimensions.columns,dimensions.rows)
            phase_start=time.perf_counter() if timings is not None else 0
            phase_cpu=time.thread_time() if timings is not None else 0
            out,changed,composed=host.flush(host.width*host.height)
            if timings is not None:
                timings['compose_ms']+=(time.perf_counter()-phase_start)*1000;timings['compose_cpu_ms']+=(time.thread_time()-phase_cpu)*1000
            if status!=status_cache:
                out+='\x1b['+str(dimensions.rows-1)+';1H\x1b[2K'+state[:dimensions.columns]
                out+='\x1b['+str(dimensions.rows)+';1H\x1b[2K'+footer[:dimensions.columns]
                status_cache=status
            if out:
                phase_start=time.perf_counter() if timings is not None else 0
                phase_cpu=time.thread_time() if timings is not None else 0
                sys.stdout.write(presentation.begin+out+presentation.end);sys.stdout.flush()
                if timings is not None:
                    timings['terminal_write_ms']+=(time.perf_counter()-phase_start)*1000
                    timings['terminal_write_cpu_ms']+=(time.thread_time()-phase_cpu)*1000
                    timings.setdefault('first_paint_ms',(time.perf_counter()-_BOOT_START)*1000)
                if input_started is not None:
                    metrics['max_input_to_present_ms']=max(metrics['max_input_to_present_ms'],(time.monotonic()-input_started)*1000);input_started=None
                metrics['frames']+=1;metrics['output_bytes']+=len(out.encode());metrics['changed_cells']+=changed;metrics['composed_cells']+=composed
            deadline=max(0,args.run_seconds-(time.monotonic()-started)) if args.run_seconds else 60
            # No frame clock. Source completion, input, resize or observation-age boundary wakes UI.
            events=selector.select(min(deadline,.03 if decoder.pending else 60))
            if not events and decoder.pending: events=[(SimpleNamespace(fileobj=None),0)]
            if events: metrics['wakeups']+=1
            for key,_ in events:
                if key.fileobj is reader.readable:
                    snapshot=reader.drain();model.apply(snapshot)
                    if timings is not None and snapshot is not None and snapshot.rows is not None:timings.setdefault('first_source_ms',(time.perf_counter()-_BOOT_START)*1000)
                    continue
                if touch is not None and key.fileobj is touch:
                    before=time.monotonic();selection_before=model.selected
                    try:
                        touch_events=touch.drain();touch.dispatch(touch_events,host,views.click)
                        metrics['touch_drops']=touch.reader.drop_count
                        metrics['inputs']+=len(touch_events);metrics['touch_inputs']+=len(touch_events)
                    except (OSError,ValueError) as error:
                        touch.cancel(host);selector.unregister(touch);touch.close();touch=None
                        metrics['touch_error']=str(error)[:200]
                    if host.damage or host.latest is not None or model.selected!=selection_before or metrics['touch_error']:input_started=before
                    metrics['max_input_handler_ms']=max(metrics['max_input_handler_ms'],(time.monotonic()-before)*1000)
                    continue
                raw=os.read(sys.stdin.fileno(),4096) if key.fileobj is not None else b''
                if not raw and key.fileobj is not None: stopped=True;break
                before=time.monotonic();input_started=before
                for event in decoder.feed(raw,expire=key.fileobj is None):
                    metrics['inputs']+=1
                    if event[0]=='mouse':
                        _,button,x,y,released=event
                        if button&64:
                            if host.focus=='Details': views.scroll=max(0,views.scroll+(3 if button&1 else -3))
                            else: views.select_step(1 if button&1 else -1)
                        else:
                            host.pointer(button,x,y,released)
                            if not released and button==0: views.click(x,y)
                        continue
                    name=event[1]
                    if name in ('q','Q','\x03'): stopped=True
                    elif name in ('r','R'): reader.refresh()
                    elif name in ('1','2'): host.activate('Heard' if name=='1' else 'Details')
                    elif name in ('\t','f6','backtab','shift-f6'): host.activate('Details' if host.focus=='Heard' else 'Heard')
                    elif name in ('m','M'):
                        host.begin(False);move_dx=move_dy=0
                    elif host.drag:
                        if name in ('\r','\n'): host.finish(True)
                        elif name=='\x1b': host.finish(False)
                        elif name in ('up','down','left','right'):
                            dx,dy={'up':(0,-1),'down':(0,1),'left':(-1,0),'right':(1,0)}[name]
                            move_dx+=dx;move_dy+=dy;host.motion(move_dx,move_dy)
                    elif name in ('up','down'):
                        if host.focus=='Details': views.scroll=max(0,views.scroll+(1 if name=='down' else -1))
                        else: views.select_step(1 if name=='down' else -1)
                metrics['max_input_handler_ms']=max(metrics['max_input_handler_ms'],(time.monotonic()-before)*1000)
    finally:
        if touch is not None:touch.cancel(host);touch.close()
        reader.close();selector.close()
        for sig,handler in previous.items():signal.signal(sig,handler)
        termios.tcsetattr(sys.stdin,termios.TCSADRAIN,old)
        sys.stdout.write(presentation.end+'\x1b[?1006l\x1b[?1002l\x1b[?25h\x1b[?1049l');sys.stdout.flush()
        metrics.update(elapsed_seconds=time.monotonic()-started,cpu_seconds=time.process_time()-cpu_started,reader_reads=reader.reads,reader_seconds=reader.read_seconds,contacts=len(model.contacts),model_revision=model.revision,view_builds=views.builds,max_rss_native=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if timings is not None:
            metrics['phases_ms']=timings;metrics['reader_cpu_seconds']=reader.cpu_seconds
            metrics['last_db_phases_ms']=getattr(reader.source,'phases',None)
        metrics['glyph_font']=str(args.glyph_font) if args.glyph_font else None
        metrics['glyph_policy']='one cell per scalar; wide/combining/control replaced'
        metrics['backend']='native' if host._native is not None else 'python'
        metrics['native_error']=host.native_error
        metrics['native_buffer_bytes']=host._native.bytes if host._native else 0
        if args.metrics:args.metrics.write_text(json.dumps(metrics,indent=2)+'\n')


if __name__=='__main__':main()
