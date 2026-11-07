#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Full Pocket model, direct native pixel rendering and an SDL window."""
import argparse,importlib.util,json,signal,sys,time,ctypes as C,os
from pathlib import Path
HERE=Path(__file__).resolve().parent
CONFIG=json.loads((HERE.parent/'build/graphics/frontend.json').read_text())
sys.path.insert(0,CONFIG['graphics_path'])
from font_supplement import install as install_font
install_font()
from platform_window import Window
from explore_controls import ExploreControls
spec=importlib.util.spec_from_file_location('graphical_platform',Path(CONFIG['graphics_path'])/'full.py')
shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)

class DesktopWindow(Window):
    """Full desktop keyboard semantics; Escape is app input, not window close."""
    def active_room(self):
        platform=getattr(self,'platform',None)
        return next((room for room in platform.pixel_apps if room._active()),None) if platform else None
    def controls_for(self,room):
        if not hasattr(self,'controls'):self.controls={}
        if room not in self.controls:self.controls[room]=ExploreControls(time.monotonic())
        return self.controls[room]
    def events(self):
        raw=(C.c_int*6)()
        names={1073741904:'left',1073741903:'right',1073741906:'up',1073741905:'down',
            1073741898:'home',1073741901:'end',1073741899:'pageup',1073741902:'pagedown',
            1073741882:'help',1073741883:'f2',1073741884:'f3',1073741885:'f4',
            1073741886:'f5',1073741887:'f6',8:'\x7f',13:'\r',9:'\t',27:'\x1b'}
        from terminal_keys import legacy
        while self.lib.pocket_window_event(raw):
            kind,x,y,button,up,repeat=raw
            room=self.active_room()
            if kind==1:yield {'action':'quit'}
            elif kind==2:
                if self.captured:
                    if room and button==0 and not up:
                        room.lib.pocket_game_fire.argtypes=[C.c_float]*5
                        room.lib.pocket_game_fire(room.x,room.eye_height,room.z,room.yaw,room.pitch);room.pixel_dirty=True
                elif room and button==0 and not up:
                    wx,wy,ww,wh=self.platform.host.bounds(self.platform.host.window(room.name));ox,oy=self.platform.host.origin
                    if (wx+ox+1)*8<=x<(wx+ox+ww-1)*8 and (wy+oy+1)*16<=y<(wy+oy+wh-1)*16:self.capture(True)
                    else:yield dict(action='pointer',x=x,y=y,button=button,released=False)
                else:yield dict(action='pointer',x=x,y=y,button=button,released=bool(up))
            elif kind==3:
                motion={1073742049:'shift-left',1073742053:'shift-right',32:'space',1073741904:'left',1073741903:'right',1073741906:'up',1073741905:'down'}
                motion_key=motion.get(x,chr(x) if 32<=x<127 else '')
                if x==27 and not up and self.captured:
                    self.capture(False)
                    if room:self.controls_for(room).clear(time.monotonic())
                    continue
                if room and x==ord('g') and not up and not repeat:
                    self.game_enabled=not getattr(self,'game_enabled',False);room.lib.pocket_game_enable(int(self.game_enabled));room.pixel_dirty=True;continue
                if room and x==ord('r') and not up and not repeat:
                    room.lib.pocket_game_reset();room.pixel_dirty=True;continue
                if room and not repeat and self.controls_for(room).key(motion_key,bool(up),time.monotonic(),room):continue
                key=names.get(x,chr(x) if 32<=x<127 else None)
                if key is not None:
                    mods=(1 if button&3 else 0)|(2 if button&768 else 0)|(4 if button&192 else 0)|(8 if button&3072 else 0)
                    if mods&1 and len(key)==1 and 32<=ord(key)<127:
                        shifted=dict(zip('`1234567890-=[]\\;\',./','~!@#$%^&*()_+{}|:"<>?'))
                        key=shifted.get(key,key.upper());mods &= ~1
                    yield dict(action='key',key=legacy(key,mods),released=bool(up))
            elif kind==4:yield {'action':'redraw'}
            elif kind==5:
                if room and self.captured:self.controls_for(room).look(x,y,room)
            elif kind==6:
                self.captured=False
                for control in getattr(self,'controls',{}).values():control.clear(time.monotonic())
                yield {'action':'cancel-input'}
            elif kind==8:yield dict(action='resize',width=x,height=y)

def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--state',type=Path,default=Path.home()/'.local/state/current-world/graphics')
    p.add_argument('--seconds',type=float);p.add_argument('--actions',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--report',type=Path)
    p.add_argument('--resize-check',action='store_true',help='exercise actual OS window-size events')
    p.add_argument('--effect-backend',choices=('gpu','cpu'),default='gpu' if sys.platform=='darwin' and __import__('platform').machine()=='arm64' else 'cpu')
    p.add_argument('--allow-software',action='store_true',help='explicit software-GL test mode; not GPU performance evidence')
    p.add_argument('--headless',action='store_true',help='GPU verification without the presentation window')
    args,extra=p.parse_known_args()
    state=args.state;state.mkdir(parents=True,exist_ok=True)
    window=None if args.headless else DesktopWindow(CONFIG['display_library'])
    actions=json.loads(args.actions.read_text()) if args.actions else ()
    platform=shared.Platform(CONFIG['font'],CONFIG['gpu_library'],window,output=args.output,actions=actions,require_gpu=not args.allow_software)
    restore_effects=None
    if args.effect_backend=='gpu':
        try:import mlx.core
        except ImportError:raise SystemExit('GPU effects require requirements-graphics-macos.txt; install it or explicitly choose --effect-backend cpu.')
        effect_root=HERE/'effects'
        spec_provider=importlib.util.spec_from_file_location('graphical_gpu_effects',effect_root/'provider.py')
        provider_module=importlib.util.module_from_spec(spec_provider);spec_provider.loader.exec_module(provider_module)
        gpu_effects=provider_module.Provider();restore_effects=gpu_effects.install(platform)
    if window:window.platform=platform
    start=time.monotonic();base_events=platform.events;resize_stage=0
    def events():
        nonlocal resize_stage
        if window:
            for room,control in list(getattr(window,'controls',{}).items()):
                control.advance(time.monotonic(),room);room.set_eye_height(340.+control.height)
                if not room._active() and window.captured:window.capture(False)
            if args.resize_check and time.monotonic()-start>1+resize_stage and resize_stage<3:
                sizes=((1120,800),(640,448),(1280,864));w,h=sizes[resize_stage]
                window.lib.pocket_window_set_size.argtypes=[C.c_void_p,C.c_int,C.c_int]
                window.lib.pocket_window_set_size(window.handle,w,h);resize_stage+=1
        if args.seconds and time.monotonic()-start>=args.seconds:platform.closed=True
        return base_events()
    platform.events=events
    previous={}
    def stop(*unused):platform.closed=True
    for sig in (signal.SIGTERM,signal.SIGINT):previous[sig]=signal.signal(sig,stop)
    try:
        platform.run(['--shell','--session',str(state/'desktop.json'),'--app-state',str(state),
            '--station-db',str(state/'directory.sqlite3'),'--native',CONFIG['native_library'],
            '--no-local-services',*extra])
    finally:
        platform.report.update(renderer=platform.report.get('renderer'),software_allowed=args.allow_software,platform=sys.platform,desktop_pty=False,desktop_ansi=False,desktop_cells=platform.size)
        platform.close()
        if restore_effects:restore_effects()
        if args.report:args.report.write_text(json.dumps(platform.report,indent=2)+'\n')
        if args.report or args.headless:print(json.dumps({key:platform.report.get(key) for key in ('frames','focus','opened','native','desktop_ansi','desktop_pty','desktop_cells')}),flush=True)
        for sig,handler in previous.items():signal.signal(sig,handler)
if __name__=='__main__':main()
