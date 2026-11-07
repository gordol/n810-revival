#!/usr/bin/env python3
"""Pocket graphical frontend, independent of the terminal launcher."""
import argparse,json,sys,time,signal,os
from pathlib import Path

def main(argv=None):
    config_path=Path(__file__).resolve().parents[1]/'build/graphics/frontend.json'
    config=json.loads(config_path.read_text()) if config_path.exists() else {}
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--renderer',choices=('mbx','native'),default=None)
    parser.add_argument('--font',type=Path,default=config.get('font'),help='captured PSF1 font')
    parser.add_argument('--renderer-library',type=Path,default=config.get('renderer_library'),help='native RGB565 cell renderer')
    parser.add_argument('--native-library',type=Path,default=config.get('native_library'),help='optional native Pocket compositor')
    parser.add_argument('--output',type=Path,help='optional raw RGB565 capture')
    parser.add_argument('--display-library',type=Path,default=config.get('display_library'),help='SDL graphical window library for the development host')
    parser.add_argument('--framebuffer-fd',type=int,default=-1,help='already owned Nokia framebuffer; no automatic takeover')
    parser.add_argument('--touch-device',type=Path)
    parser.add_argument('--touch-calibration',type=Path)
    parser.add_argument('--actions',type=Path,help='replay JSON actions instead of opening a window')
    parser.add_argument('--once',action='store_true',help='render one desktop frame and exit')
    args=parser.parse_args(argv)
    if not args.font or not args.renderer_library:parser.error('Build with make graphics-native or supply font and renderer library')
    if not args.once and not args.actions and not args.display_library:parser.error('Interactive graphics requires --display-library')
    if args.once and not args.output:parser.error('--once requires --output')
    backend=args.renderer or ('mbx' if args.framebuffer_fd>=0 else 'native')
    if backend=='mbx' and os.environ.get('POCKET_MBX_PRELOADED')!='1':
        mesa=args.renderer_library.resolve().parent/'libOSMesa.so.8'
        if not mesa.is_file():parser.error('Matching libOSMesa.so.8 must be beside the MBX renderer')
        env=dict(os.environ,POCKET_MBX_PRELOADED='1')
        env['LD_PRELOAD']=str(mesa)+(' '+env['LD_PRELOAD'] if env.get('LD_PRELOAD') else '')
        os.execvpe(sys.executable,[sys.executable,str(Path(__file__).resolve()),*(sys.argv[1:] if argv is None else argv)],env)
    from desktop import Desktop
    app=Desktop(args.font,args.renderer_library,native_library=args.native_library,backend=backend)
    previous_signals={}
    def stop(*unused):app.closed=True
    for sig in (signal.SIGINT,signal.SIGTERM):
        previous_signals[sig]=signal.signal(sig,stop)
    output=None;window=None;touch=None
    try:
        if args.output:output=args.output.open('wb')
        if args.display_library and not args.once and not args.actions:
            from window import Window
            window=Window(args.display_library,args.framebuffer_fd)
        if args.touch_device:
            if not args.touch_calibration:raise ValueError("Touch requires its existing calibration")
            from touch_process import ProcessTouchSource
            from touch_evdev import display
            touch=ProcessTouchSource(args.touch_device,args.touch_calibration,display(800,480),800,480,native_library=args.native_library)
        if app.renderer.font.height!=16:raise ValueError('This frontend requires the unchanged 8x16 console font')
        print(json.dumps(dict(frontend='pixels',width=800,height=480,format='rgb565le' if sys.byteorder=='little' else 'rgb565be',renderer='mbx-cells' if backend=='mbx' else 'native-cells',gpu=backend=='mbx')),file=sys.stderr)
        def present():
            frame=app.render()
            if frame:
                if output:output.write(frame);output.flush()
                if window:window.present(frame)
        present()
        if args.once:return
        if args.actions:
            with args.actions.open('rb') as actions:
                for line in actions:
                    if len(line)>65536:raise ValueError('Action exceeds64KiB')
                    event=json.loads(line)
                    if not isinstance(event,dict):raise ValueError('Action must be an object')
                    app.dispatch(event)
                    if app.closed:break
                    present()
        else:
            while not app.closed:
                started=time.monotonic()
                for event in window.events():app.dispatch(event)
                if touch:
                    for event in touch.drain():
                        if event[0]=='mouse':app.dispatch(dict(action='pointer',button=event[1],x=event[2],y=event[3],released=event[4]))
                        elif event[0]=='touch_cancel':touch.cancel(app.host);app.host.finish(False);app.host.pointer_origin=None
                if not app.closed:present()
                time.sleep(max(0.,1/60-(time.monotonic()-started)))
    finally:
        if touch:touch.close()
        app.close()
        if window:window.close()
        if output:output.close()
        for sig,handler in previous_signals.items():signal.signal(sig,handler)

if __name__=='__main__':main()
