#!/usr/bin/env python3
"""Local synthetic operator console; no device or network access."""
import sys
_BOOT_STARTED=__import__('time').monotonic()
if __name__=='__main__' and sys.stdin.isatty() and sys.stdout.isatty() and not any(v in sys.argv for v in ('--help','-h','--smoke')):
    sys.stdout.write('Starting desktop...\r\n');sys.stdout.flush()
import argparse
import json
import os
from pathlib import Path
import selectors
import select
import signal
import sys
import termios
import tempfile
import tty
import time
from session import Store, capture, default_path
from terminal import measure,Presentation,console_wake
from panel import Panels, DOCKS, MODES
from settings import SettingsManager, slider
from launcher import Launcher
import build_identity
from widgets import Clock, CalendarView, Link, link_label
from weather import Weather, PRESETS
from effects import NAMES as EFFECTS
from input import Input,WM_ESCAPES,phone_action
from controls import scene_controls,Button,Slider,Choice
from core import World, Record, Host, Window, Inbox, compile_model, STYLES, PALETTES


def present_form_content(host,name,form,lines,spans,layer,metrics=None):
    """Admit retained plane damage before ordinary text and style changes."""
    patch=form.take_layer_patch() if callable(getattr(form,'take_layer_patch',None)) else None
    if patch is not None:
        patched_layer,indices=patch
        if patched_layer is layer:
            if metrics:metrics.model_call(name,'layer_patch',host.layer_patch,name,layer,indices)
            else:host.layer_patch(name,layer,indices)
        else:
            # A stale producer delta cannot describe the currently sampled plane.
            host.invalidate(host.window(name).rect)
    if metrics:metrics.model_call(name,'content',host.content,name,lines,lines,spans,layer)
    else:host.content(name,lines,lines,spans,layer)


def drain_touch_ready(source, trace):
    """Service a bounded ready burst; merge only compatible adjacent motion."""
    from pointer_events import coalesce_motion
    events=[]
    started=time.monotonic()
    for _ in range(4):
        batch=source.drain()
        trace.received(source,batch)
        for event in batch:
            merged=(coalesce_motion(events[-1],event)
                    if events and events[-1][0]=='mouse' and event[0]=='mouse' else None)
            if merged is not None:events[-1]=merged
            else:events.append(event)
        if any(event[0]=='touch_cancel' for event in batch):break
        if time.monotonic()-started>=.004 or not select.select((source,),(),(),0)[0]:break
    return events


def main():
    startup={'imports_complete_seconds':time.monotonic()-_BOOT_STARTED}
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene-preset",choices=("original","wide","elevated","valley"))
    parser.add_argument("--scene-quality",choices=("compact","detailed"))
    parser.add_argument('--scene-backend',choices=('cpu','numpy','gpu'),default='cpu',help='terrain lighting backend; GPU requires Apple Metal/MLX (default: cpu)')
    parser.add_argument('--scene-cache',type=Path,help='opt-in completed terrain view cache (four entries, 64 MiB)')
    parser.add_argument('--scene-report',type=Path,help='write actual terrain backend, fallback and cache counters on exit')
    parser.add_argument('--compute-backend',choices=('auto','python','existing'),default='auto',help='guarded native geometry stages, portable CPU, or an embedding caller selection')
    parser.add_argument('--compute-info',action='store_true',help='print geometry stage selection and counters, then exit')
    parser.add_argument('--background-inline',action='store_true',help='compute decorative backgrounds on the event-loop thread for comparison')
    parser.add_argument("--scenery-app",action="store_true",help="open the Scenery app")
    parser.add_argument("--scenery-library",type=Path,help="directory for scenery recipes and view captures")
    parser.add_argument("--scenery-tune",action="store_true",help="terrain background and scenery settings / named library")
    parser.add_argument('--workbench',action='store_true',help='open local file inspection, CW replay and retained analysis results')
    parser.add_argument('--reader',action='store_true',help='open cached feeds and offline articles; network refresh is explicit')
    parser.add_argument('--library',action='store_true',help='open local collections; scanning is explicit')
    parser.add_argument('--library-root',action='append',default=[],help='explicit Library collection folder (repeatable); no automatic scan')
    parser.add_argument('--app-state',type=Path,help='private Reader/Workbench state root for this client; leaves desktop session and radio paths unchanged')
    parser.add_argument('--audio-provider',type=Path,help='shared local PCM endpoint without opening or moving Audio Monitor')
    parser.add_argument('--audio-socket',type=Path,help='existing receive-only local PCM socket; opens Audio Monitor, playback off')
    parser.add_argument('--timezone',help='IANA display time zone, saved per desktop (default UTC)')
    parser.add_argument('--session', type=Path, default=default_path())
    parser.add_argument('--native-stations',action='store_true',help='open native linked Stations and Station Map with terminal apps retained as fallback')
    parser.add_argument('--flurry-trial',type=Path,help='bounded private 80x24 Flurry comparison; requires a NEW output directory')
    parser.add_argument('--flurry-library',type=Path,help='opt-in tested Flurry numeric library; unsupported settings use Python')
    parser.add_argument('--flurry-sha256',help='expected hash for the explicitly selected Flurry library')
    parser.add_argument('--native',type=Path,help='explicit native cell compositor library (default: verified host build)')
    parser.add_argument('--no-native',action='store_true',help='force portable composition for comparison')
    parser.add_argument('--legacy-apps',action='store_true',help='keep terminal-hosted app defaults instead of accepted native views')
    parser.add_argument('--station-db',type=Path,help='existing read-only station database for native Stations without terminal wrappers')
    parser.add_argument('--station-maps',type=Path,help='offline map packs for native Station Map')
    parser.add_argument('--device-radio',action='store_true',help='read existing device-local radio snapshots without changing their owner')
    parser.add_argument('--radio-read-socket',type=Path,help='existing owner read-current control socket; requests are explicit')
    parser.add_argument('--radio-state',type=Path,default=os.environ.get('N810_RADIO_STATE'),help='operator-owned connector catalog/live JSON snapshot')
    parser.add_argument('--receive-status',type=Path,help='local SSH receive recovery status from the launcher')
    parser.add_argument('--receive-feed',type=Path,help='existing decoded receive Unix socket shared by native apps')
    parser.add_argument('--receive-snapshot',type=Path,help='existing raw receive snapshot Unix socket')
    parser.add_argument('--receive-sources',type=Path,help='approved client Directory ingest modules; requires --receive-feed and --station-db')
    parser.add_argument('--receive-bridge',type=Path,help='owned SSH bridge directory for bounded read-only radio status')
    parser.add_argument('--no-save', action='store_true')
    parser.add_argument('--profile', choices=['small', 'wide'], default='small')
    parser.add_argument('--panel', choices=DOCKS, default=None)
    parser.add_argument('--panel-mode',choices=MODES,help='bar, responsive auto, icon dock or compact sidebar')
    parser.add_argument('--effect', choices=EFFECTS)
    parser.add_argument('--light', choices=('dynamic','day','night'))
    parser.add_argument('--scene-seed',type=int,help='explicit reproducible landscape seed')
    parser.add_argument('--moon-phase',choices=('auto','full','waxing','crescent','new','waning'))
    parser.add_argument('--style', choices=STYLES, default=None)
    parser.add_argument('--window-controls',choices=('auto','left','right'),help='title controls: auto favors left at 160+ columns, right below')
    parser.add_argument('--palette', choices=PALETTES, default=None)
    parser.add_argument('--ascii', action='store_true', help='fallback for terminals without box drawing')
    parser.add_argument('--no-animation', action='store_true')
    parser.add_argument('--static-world',action='store_true',help='freeze terrain world age for controlled UI tests; not saved as a preference')
    parser.add_argument('--minimal',action='store_true',help='plain event-driven desktop; defer showcase imports and backgrounds')
    parser.add_argument('--metrics',type=Path,help='write aggregate draw timings on exit (no screen contents)')
    parser.add_argument('--move', choices=['outline','live'], default=None)
    parser.add_argument('--resize', choices=['outline','live'], default=None)
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--screensaver',action='store_true')
    parser.add_argument('--kitchen-sink',action='store_true')
    parser.add_argument('--arrival-seconds',type=float,help='enable and time the first terrain reveal (0.25 to 12 seconds); --no-animation takes precedence')
    parser.add_argument('--app-preview',action='store_true',help='open proposed app layouts using local fixtures')
    parser.add_argument('--legacy-workspace',type=Path,help='JSON declarations for unchanged PTY apps')
    parser.add_argument('--legacy-aprs',type=Path,help='host an unchanged APRS viewer script in a PTY window')
    parser.add_argument('--terminal',action='store_true',help='open a shell window on startup (also available in the menu)')
    parser.add_argument('--terminal-opacity',type=float,help='shell background opacity from 0 to 1; text stays opaque')
    parser.add_argument('--navigation-trial',action='store_true',help='consistent native focus, tab bars, list search and Back keys; terminal input is unchanged')
    parser.add_argument('--phone-keys',action='store_true',help='direct phone buttons: F7 Menu, F8 Windows, F9 Close, F10 Max, F12 Next')
    parser.add_argument('--wm-escape',choices=WM_ESCAPES,help='WM escape; in WM mode Ctrl-V sends it to the focused child')
    parser.add_argument('--mirror',action='store_true',help='easter egg: nested live desktops, ending with a tiny koan')
    parser.add_argument('--mirror-delay',type=float,default=.4,help='seconds between mirror levels (0 to 2)')
    parser.add_argument('--mirror-depth',type=int,default=0,help=argparse.SUPPRESS)
    parser.add_argument('--mouse-trails',action='store_true',help='brief settling rainbow wireframe decoration around reported pointer cells')
    parser.add_argument('--aprs-socket',help='mandatory existing decoded feed socket for the legacy viewer')
    parser.add_argument('--aprs-maps',type=Path,help='existing offline map directory')
    parser.add_argument('--aprs-history',type=Path,help='optional retained capture; never labeled live by the host')
    parser.add_argument('--replay',action='store_true',help='label a local recorded-service app window REPLAY')
    parser.add_argument('--touch-device',type=Path)
    parser.add_argument('--touch-acquisition',choices=('python','process'),default=build_identity.IDENTITY['touch_acquisition_default'],help='touch acquisition owner: current Python path or opt-in independent process; selected trial may set its packaged default')
    keyboard_options=parser.add_mutually_exclusive_group()
    keyboard_options.add_argument('--keyboard-device',type=Path,help='explicit optional Linux motion keyboard; requires readable input device and foreground console')
    keyboard_options.add_argument('--keyboard-fd',type=int,help='validated inherited motion keyboard descriptor from the console owner')
    parser.add_argument('--touch-calibration',type=Path)
    parser.add_argument('--touch-display',help='physical WIDTHxHEIGHT, matching calibration')
    parser.add_argument('--touch-rotation',type=int,choices=(0,90,180,270),default=0)
    parser.add_argument('--pointer-trace',type=Path,help='opt-in bounded pointer/camera diagnostic JSON; no effect on gesture timing')
    args = parser.parse_args()
    from pointer_trace import PointerTrace
    pointer_trace=PointerTrace(args.pointer_trace)
    if args.keyboard_fd is not None and not 3<=args.keyboard_fd<=65535:parser.error('keyboard descriptor must be in 3..65535')
    if args.navigation_trial:
        from native_navigation import native_key,native_presentation,native_pointer,navigation
    trial=None
    if args.flurry_trial:
        from flurry_trial import Trial
        trial=Trial(args.flurry_trial);trial.configure(args)
    if bool(args.receive_feed)!=bool(args.receive_snapshot):parser.error('receive feed and snapshot sockets must be provided together')
    if args.receive_sources:
        if not (args.receive_feed and args.station_db):parser.error('--receive-sources requires --receive-feed and --station-db')
        args.receive_sources=args.receive_sources.expanduser().resolve()
        if not (args.receive_sources/'n810-aprs-directory.py').is_file():parser.error('--receive-sources must contain the approved n810-aprs-directory.py adapter')
    receive_status=None
    if args.receive_status:
        from receive_bridge import Status
        receive_status=Status(args.receive_status)
    if not 0<=args.mirror_delay<=2 or args.mirror_depth<0:parser.error('invalid mirror delay or depth')
    if args.mirror:
        args.no_save=True
    if args.terminal_opacity is not None and not 0<=args.terminal_opacity<=1:parser.error('--terminal-opacity must be between 0 and 1')
    if args.flurry_sha256 and not args.flurry_library:parser.error('--flurry-sha256 requires --flurry-library')
    metrics=None
    if args.metrics:
        from draw_metrics import Metrics
        metrics=Metrics()
    import compute_runtime
    compute_runtime.select(args.compute_backend)
    if args.compute_info:
        print(json.dumps(compute_runtime.status(),sort_keys=True));return
    import scene_acceleration
    scene_selection=scene_acceleration.configure(args.scene_backend,args.scene_cache)
    if scene_selection['setup_fallback']:
        print('Scene acceleration unavailable; using CPU: '+scene_selection['setup_fallback'],file=sys.stderr)
    if args.minimal and (args.kitchen_sink or args.app_preview or args.screensaver):parser.error('--minimal excludes showcase app/screen previews')
    workspace=()
    if args.legacy_workspace:
        from legacy_workspace import load
        try:workspace=load(args.legacy_workspace)
        except (OSError,ValueError,KeyError,TypeError) as error:parser.error('workspace: '+str(error))
    native_defaults=bool((args.radio_state or args.device_radio or args.receive_feed) and not args.legacy_apps)
    terminal_fallbacks=tuple(app._replace(name=app.name+' (terminal)') for app in workspace) if native_defaults else ()
    if native_defaults and workspace:
        sizes={'Messages':(44,14),'Nets':(42,14),'Services':(42,14)}
        workspace=tuple(app._replace(minimum=sizes.get(app.name,app.minimum)) for app in workspace)
        if any(app.name=='Directory' for app in workspace):args.native_stations=True
    if args.minimal or workspace or native_defaults and not (args.app_preview or args.kitchen_sink):app_gallery=demo_apps=None
    else:
        import app_gallery,demo_apps
    if args.replay and not (args.legacy_aprs or workspace):parser.error('--replay requires an explicit legacy app or workspace')
    if any((args.touch_device,args.touch_calibration,args.touch_display)) and not all((args.touch_device,args.touch_calibration,args.touch_display)):parser.error('touch requires device, calibration and physical display size')
    if args.legacy_aprs and (not args.aprs_socket or not args.aprs_maps):parser.error('--legacy-aprs requires --aprs-socket and --aprs-maps')
    if args.legacy_aprs and (not args.legacy_aprs.is_file() or not args.aprs_maps.is_dir()):parser.error('legacy viewer script and maps directory must exist')
    plans = () if args.minimal or workspace or native_defaults and not (args.app_preview or args.kitchen_sink) else compile_model(Path(__file__).with_name('operator.json').read_text())
    world = World(plans)
    world.apply([Record(1, 'N0CALL', 'APRS observed', 'Listening'), Record(2, 'W7EXAMPLE', 'Offline record', 'Contact unconfirmed')])
    geometry = measure(sys.stdout.fileno())
    panel=Panels(args.panel or 'top',mode=args.panel_mode or ('auto' if workspace else 'bar'))
    panel.launcher_count=2+len(workspace)
    ox,oy,width,height=panel.layout(*(trial.viewport(geometry.columns,geometry.rows) if trial else (geometry.columns,geometry.rows)))
    if width < 40 or height < 12:
        raise SystemExit('Use a terminal at least 40 columns by 14 rows.')
    windows = (app_gallery.windows(width,height) if app_gallery is not None else [])+[
        Window('Settings',max(0,(width-68)//2),1,min(68,width),min(18,height-1),visible=False,opened=False),
        Window('Scenery',1,1,min(100,width),min(32,height-1),visible=False,opened=False),
        Window('Font Preview',1,1,min(78,width),min(28,height-1),visible=False,opened=False),
        Window('Calendar',max(0,(width-40)//2),1,min(40,width),min(13,height-1),visible=False,opened=False)]
    if not args.minimal or args.radio_state or args.device_radio or args.receive_feed or args.radio_read_socket:
        windows.append(Window('Radio Manager',max(0,(width-86)//2),2,min(86,width),min(29,height-2),visible=False,opened=False))
        if not any(window.name=='Radio' for window in windows):
            windows.append(Window('Radio',max(0,width-48),2,min(46,width),min(19,height-2),visible=False,opened=False))
        windows.append(Window('System',max(0,(width-78)//2),2,min(78,width),min(27,height-2),visible=False,opened=False))
    if native_defaults or args.audio_socket or args.audio_provider:
        windows.append(Window('Audio Monitor',1,1,min(86,width),min(30,height),visible=False,opened=False))
    windows.append(Window('Render Debug',1,1,min(76,width),min(18,height),visible=False,opened=False))
    tw,th=min(82,width),min(26,height)
    windows.append(Window('Terminal',max(0,(width-tw)//2),max(0,(height-th)//2),tw,th,visible=False,opened=False))
    if demo_apps is not None:windows.extend(demo_apps.windows(width,height))
    from app_registry import discover as discover_apps
    registered_apps=discover_apps()
    from last_heard_runtime import descriptor as last_heard_descriptor,SnapshotCache,LastHeardApp
    def make_last_heard(_host):
        return LastHeardApp(SnapshotCache(native_catalog,context),
            visible=lambda:host.shown(host.window('Last heard')) and not host.window('Last heard').rolled)
    registered_apps.register(last_heard_descriptor(make_last_heard))
    windows.extend(registered_apps.windows(width,height))
    windows.append(Window('Help',max(0,(width-90)//2),1,min(90,width),min(28,height-1),visible=False,opened=False))
    terminal_name='APRS REPLAY' if args.replay else 'APRS Terminal'
    if args.legacy_aprs:windows.append(Window(terminal_name,1,1,max(24,width-2),max(8,height-2)))
    if workspace:
        from legacy_workspace import arrange as workspace_windows
        try:windows.extend(workspace_windows(workspace,width,height))
        except ValueError as error:parser.error(str(error))
    if native_defaults and args.device_radio and not workspace:
        from legacy_workspace import App
        fallback=[]
        for name,script in (('Messages','n810-aprs-messages.py'),('Services','n810-aprs-services.py'),('Nets','n810-nets.py'),('APRS','n810-aprs-view.py'),('Directory','n810-aprs-directory.py'),('Walk','n810-aprs-walk.py')):
            path=Path.home()/script
            if path.is_file():fallback.append(App(name+' (terminal)',(sys.executable,str(path)),0,(1,1,min(96,width-1),min(28,height-1)),(40,12)))
        terminal_fallbacks=tuple(fallback)
    if terminal_fallbacks:
        originals={w.name:w for w in windows}
        for app in terminal_fallbacks:
            source=originals.get(app.name.removesuffix(' (terminal)'))
            rect=source.rect if source else app.rect
            windows.append(Window(app.name,*rect,visible=False,opened=False))
    if native_defaults:
        for name in ('Messages','Nets','Services','Walk','CW','Radio Feed','Heard'):
            if not any(w.name==name for w in windows):windows.append(Window(name,1,1,min(86,width-1),min(28,height-1),visible=False,opened=False))
    def local_domain_installed(name):
        here=Path(__file__).resolve().parent
        return any((root/'domains'/name/'__init__.py').is_file()
                   for root in (here/'vendor/apps',here.parents[1]/'packet-console'))
    app_state=args.app_state or Path.home()/'.local/state/current-world'
    workbench_enabled=args.workbench or not args.minimal and local_domain_installed('workbench')
    if workbench_enabled:
        windows.append(Window('Workbench',1,1,min(96,width-1),min(30,height-1),visible=False,opened=False))
    reader_enabled=args.reader or not args.minimal and local_domain_installed('reader')
    library_enabled=bool(args.library or args.library_root or not args.minimal and local_domain_installed('library'))
    for name,enabled in (('Reader',reader_enabled),('Library',library_enabled)):
        if enabled:windows.append(Window(name,1,1,min(100,width-1),min(32,height-1),visible=False,opened=False))
    def make_workbench(_host):
        from workbench_app import WorkbenchApp
        return WorkbenchApp(app_state/'workbench')
    def make_reader(_host):
        from document_apps import ReaderApp
        return ReaderApp(app_state/'reader')
    def make_library(_host):
        from document_apps import LibraryApp
        return LibraryApp(args.library_root)
    for name,enabled,factory,preferred,minimum in (
            ('Workbench',workbench_enabled,make_workbench,(96,30),(34,16)),
            ('Reader',reader_enabled,make_reader,(100,32),(36,16)),
            ('Library',library_enabled,make_library,(100,32),(36,16))):
        if enabled:
            registered_apps.register(dict(id=name.lower(),title=name,factory=factory,
                preferred_size=preferred,minimum_size=minimum))
    station_app=next((app for app in workspace if app.name=='Directory'),None)
    station_enabled=station_app is not None or args.station_db is not None
    if station_enabled:
        windows.extend([Window('Stations',0,0,min(72,width),min(34,height),visible=False,opened=False),Window('Station Map',max(0,width-min(120,width)),0,min(120,width),min(48,height),visible=False,opened=False)])
    mirror_plan=None;mirror_name=None
    if args.mirror:
        from mirror import plan
        mirror_plan=plan(width,height,args.mirror_depth,args.mirror_delay)
        mirror_name=f'Mirror {args.mirror_depth+1}' if mirror_plan.child else 'The last window'
        windows.append(Window(mirror_name,*mirror_plan.rect,lines=mirror_plan.lines))
    host = Host(width,height+panel.overlay_bottom,windows,ascii=args.ascii, animate=not args.no_animation, move_mode=args.move or 'outline', resize_mode=args.resize or 'outline',background_async=not args.background_inline)
    host.pointer_trace=pointer_trace
    host.origin=(ox,oy);host.reserved_bottom=panel.overlay_bottom
    host.session_shells={'Terminal'}
    host.minimum_sizes={a.name:(a.minimum[0]+2,a.minimum[1]+2) for a in workspace}
    host.minimum_sizes.update({a.name:(a.minimum[0]+2,a.minimum[1]+2) for a in terminal_fallbacks})
    if station_enabled:host.minimum_sizes.update({'Stations':(42,12),'Station Map':(42,12)})
    host.set_style(args.style or 'rounded')
    host.set_palette(args.palette or 'ice')
    host.background_enabled = True
    host.set_effect(args.effect or 'terrain')
    host.scene_seed=int.from_bytes(os.urandom(4),'little')
    store=Store(args.session,enabled=not args.no_save and not args.smoke and not args.minimal,remember_layout=True)
    # Read saved settings independently of writing changes back. Minimal/smoke
    # remain fresh launch modes; --no-save alone is a read-only session.
    if not args.smoke and not args.minimal:store.load(host,panel)
    if args.timezone:
        from time_display import validate_zone
        try:validate_zone(args.timezone)
        except ValueError as error:parser.error(str(error))
        host.timezone_name=args.timezone
    import time_display
    time_display.configure(host.timezone_name)
    windows=list(host.windows)
    for p in panel.panels:
        if 'connectivity' in p.widgets and 'clock' in p.widgets and 'spacer' in p.widgets and p.widgets.index('connectivity')<p.widgets.index('spacer'):
            p.widgets.remove('connectivity');p.widgets.insert(p.widgets.index('clock'),'connectivity')
    # The experimental pager starts disabled.
    host.set_pager(False)
    if args.style:host.set_style(args.style)
    if args.panel_mode:panel.set_mode(args.panel_mode)
    if args.window_controls:host.set_window_controls(args.window_controls)
    if args.terminal_opacity is not None:host.set_terminal_opacity(args.terminal_opacity)
    if args.mouse_trails:host.set_mouse_trails(True)
    if args.wm_escape:host.set_wm_escape(args.wm_escape)
    if args.palette:host.set_palette(args.palette)
    if args.effect:host.set_effect(args.effect)
    if args.screensaver:
        host.set_effect(args.effect or 'flurry')
    if args.arrival_seconds is not None:
        host.arrival_duration=max(.25,min(12,args.arrival_seconds))
        if host.effect=='terrain' and not args.no_animation:host.animate=True
    if args.scene_seed is not None:
        if not 0<=args.scene_seed<2**32:parser.error('--scene-seed must be 0..4294967295')
        host.scene_seed=args.scene_seed
    if args.light:host.light_mode=args.light
    if args.moon_phase:host.moon_phase=args.moon_phase
    if args.move:host.move_mode=args.move
    if args.resize:host.resize_mode=args.resize
    if args.no_animation:host.animate=False
    if args.minimal:
        host.background_enabled=False;host.shadow_enabled=False;host.window_opacity=1
        host.animate=False;host.move_mode=host.resize_mode='live';host.show_connectivity=bool(args.device_radio or args.radio_state or args.receive_feed)
    if trial:trial.apply(host)
    if args.flurry_library:
        from flurry_compute import Provider
        host.flurry_provider=Provider(args.flurry_library,args.flurry_sha256)
    if args.static_world:host.static_world_age=host.nature_age()
    native_started=time.monotonic()
    native_selection={'mode':'disabled' if args.no_native else 'explicit','library':str(args.native) if args.native else None}
    if not args.no_native:
        if args.native is None:
            from native_runtime import select as select_native
            native_selection=select_native();args.native=Path(native_selection['library']) if native_selection['library'] else None
        if args.native:host.enable_native(args.native)
        else:host.native_error=native_selection.get('reason')
    startup['native_select_load_seconds']=time.monotonic()-native_started
    startup['native_ready_seconds']=time.monotonic()-_BOOT_STARTED
    if args.panel:
        first=panel.panels[0]
        other=next((p for p in panel.panels if p is not first and p.dock==args.panel),None)
        if other:other.dock=first.dock
        first.dock=args.panel
    ox,oy,width,height=panel.layout(*(trial.viewport(geometry.columns,geometry.rows) if trial else (geometry.columns,geometry.rows)))
    host.reserved_bottom=panel.overlay_bottom;host.resize(width,height+panel.overlay_bottom);host.origin=(ox,oy)
    if args.native_stations and not station_enabled:parser.error('--native-stations requires --station-db or a workspace containing Directory')
    if native_defaults and workspace and not store.loaded:
        # Seed only a new operator profile. Restored layouts own their focus.
        for window in host.windows:window.opened=window.visible=False
        host.activate('Radio Feed')
    elif args.native_stations and not store.loaded:
        for name in ('APRS','Directory'):
            if name in host.focus_order:host.window(name).visible=host.window(name).opened=False
        host.window('Station Map').opened=host.window('Station Map').visible=False
        host.activate('Stations')
    if args.legacy_aprs and not store.loaded:host.activate(terminal_name)
    if mirror_name:host.activate(mirror_name)
    if args.kitchen_sink or args.app_preview:
        app_gallery.open_workspace(host)
        if args.kitchen_sink:host.activate('Kitchen Sink')
    if args.scene_preset:host.scenery={**host.scenery,'preset':args.scene_preset}
    if args.scene_quality:host.scenery={**host.scenery,'quality':args.scene_quality}
    if store.error:print(store.error,file=sys.stderr)
    inbox = Inbox()
    shared_controls=scene_controls(host)
    host.app_forms=demo_apps.forms(host,shared_controls) if demo_apps is not None else {}
    registered_apps.bind(host)
    if app_gallery is not None:host.app_forms.update(app_gallery.forms(host))
    radio=None;system_state=None
    if 'Radio Manager' in host.focus_order:
        from radio_manager import State,RadioManager,RadioQuick
        if args.receive_feed:
            from console_source import Source
            db=args.station_db or (station_app.argv[station_app.argv.index('--db')+1] if station_app else None)
            source_root=args.receive_sources or (Path(station_app.argv[1]).parent if station_app else None)
            radio=State(source=Source(args.receive_feed,args.receive_snapshot,retained=args.radio_state,directory=db,sources=source_root,bridge=args.receive_bridge))
        elif args.device_radio:
            from device_radio_source import DeviceSource
            radio=State(source=DeviceSource(directory=args.station_db))
        else:radio=State(args.radio_state)
        from radio_read_client import RadioRead,read_endpoint
        endpoint=read_endpoint(args.device_radio,args.radio_read_socket,remote=bool(args.receive_feed))
        if endpoint is not None:radio.read_client=RadioRead(endpoint)
        radio.update(True)
        host.app_forms['Radio Manager']=RadioManager(radio,Path.home()/'.local/state/current-world/radio-drafts')
        host.app_forms['Radio']=RadioQuick(radio,host.app_forms['Radio Manager'],lambda:host.activate('Radio Manager'))
        from system_view import State as SystemState,System
        system_state=SystemState(radio);system_state.update()
        host.app_forms['System']=System(system_state)
    from draw_metrics import RenderDebug
    host.app_forms['Render Debug']=RenderDebug(lambda:metrics.render if metrics else None,
        lambda:host.shown(host.window('Render Debug')) and not host.window('Render Debug').rolled,
        lambda:(host.width,host.height,'6 Hz target' if host.background_enabled and host.effect in ('flurry','flux','terrain') else 'event driven',host._native is not None,host.native_error,
                host.flurry_provider.status() if host.flurry_provider else {'backend':'python','reason':'not requested'}),host=host)
    applications=[]
    for name,requested in (('Workbench',args.workbench),('Reader',args.reader),
                           ('Library',bool(args.library or args.library_root))):
        if requested:host.activate(name)
    station_directory=None;context=None
    native_catalog=None;messages_form=None
    if native_defaults and radio:
        from native_catalog import Catalog
        from native_services import Services
        from native_nets import Nets
        from native_messages import Messages
        from native_walk import Walk
        from native_cw import CW
        from native_feed import RadioFeed
        from native_heard import Heard
        native_catalog=Catalog(radio);native_catalog.update()
        messages_form=Messages('N0CALL');messages_form.update(native_catalog.lines,outbox=native_catalog.outbox,records=native_catalog.bss_records)
        if native_catalog.error:messages_form.notice='Offline';messages_form.diagnostics=str(native_catalog.error)
        host.app_forms.update({'Messages':messages_form,'Services':Services(native_catalog.service_view),'Nets':Nets(native_catalog.net_view),
                               'Walk':Walk(native_catalog.walk_view),'CW':CW(),'Radio Feed':RadioFeed(native_catalog.feed_view),'Heard':Heard(native_catalog.heard_view)})
        host.window_cleanup['CW']=host.app_forms['CW'].close
    if native_defaults or args.audio_socket or args.audio_provider:
        from audio_monitor import AudioMonitor
        host.app_forms['Audio Monitor']=AudioMonitor(args.audio_socket,provider=args.audio_provider)
        host.window_cleanup['Audio Monitor']=host.app_forms['Audio Monitor'].dismiss
        if args.audio_socket:host.activate('Audio Monitor')
    if station_enabled:
        from station_workspace import Context,Directory,Stations,StationMap
        context=Context();sources=Path(station_app.argv[1]).parent if station_app else Path(__file__).resolve().parent/'vendor/stations'
        if not sources.is_dir():sources=Path(__file__).resolve().parents[2]/'packet-console'
        db=args.station_db or station_app.argv[station_app.argv.index('--db')+1]
        station_directory=Directory(db,sources,context);station_directory.update(True)
        def show_station_map():
            map_form.focus_selection();host.activate('Station Map')
        # Prepared maps bind the bundled map source, independently of legacy app adapters.
        map_sources=Path(__file__).resolve().parent/'vendor/stations'
        if not (map_sources/'n810-map-next.py').is_file():map_sources=sources
        map_form=StationMap(context,map_sources,lambda:host.activate('Stations'),maps=args.station_maps)
        if native_catalog:map_form.update_tracks(native_catalog.evidence)
        host.app_forms.update({'Stations':Stations(station_directory,show_station_map),'Station Map':map_form})
        host.app_renderers=list(getattr(host,'app_renderers',()))+[map_form.renderer]
    from font_preview import FontPreview
    font_preview=FontPreview(host);host.app_forms['Font Preview']=font_preview
    for name,form in host.app_forms.items():
        if hasattr(form,'restore_session'):form.restore_session(getattr(host,'app_view_state',{}).get(name,{}))
    # Only CLOSED apps remain uncreated. Restore all saved opened owners,
    # including rolled or off-desktop panes, after their saved form state.
    for name in ('Workbench','Reader','Library'):
        if name in registered_apps.forms and host.window(name).opened:
            registered_apps.forms[name].open(activate=False)
    def close_apps():
        for application in applications:application.close()
        for form in host.app_forms.values():
            if hasattr(form,'close'):form.close()
        if radio:radio.close()
    def bind():
        for name, fields, limit, predicate in plans:
            w = host.window(name)
            if name not in getattr(host,'app_forms',{}) and host.shown(w) and not w.rolled:
                records = world.read(name)
                lines = tuple(' | '.join(str(r[i]) for i in fields) for r in records)
                host.content(name, lines, lines)
    bind()
    if demo_apps is not None:demo_apps.update(host,time.monotonic())
    if args.smoke:
        output, changed, computed = host.flush(width*height)
        print(json.dumps({'views': list(world.rows), 'shared_record': None if not plans else world.read('Conversations')[0] is world.read('Connectivity')[0], 'changed_cells':changed, 'composed_cells':computed, 'output_bytes':len(output.encode()), 'terminal':geometry._asdict()}))
        inbox.close()
        close_apps()
        if host.terrain_renderer is not None:host.terrain_renderer.close()
        for renderer in getattr(host,'app_renderers',()):renderer.close()
        return
    if not sys.stdin.isatty():
        inbox.close()
        close_apps()
        if host.terrain_renderer is not None:host.terrain_renderer.close()
        for renderer in getattr(host,'app_renderers',()):renderer.close()
        raise SystemExit('Interactive mode requires a terminal; use --smoke for a local check.')
    old = termios.tcgetattr(sys.stdin)
    selector = selectors.DefaultSelector()
    selector.register(sys.stdin,selectors.EVENT_READ)
    selector.register(inbox.readable,selectors.EVENT_READ)
    from renderer_wakeup import bind_completion_wakeup,needs_completion_poll
    for renderer in getattr(host,'app_renderers',()):bind_completion_wakeup(renderer,inbox)
    dx = dy = counter = 0
    weather_index = 1
    clock_widget=Clock()
    calendar_view=CalendarView()
    link=Link(False,'synthetic')
    from terminal_pointer_timing import IngressDecoder
    from pointer_events import deliver_pointer,prepare_gestures
    decoder = IngressDecoder(Input(passthrough=True,phone_keys=args.phone_keys,extended_keys=True))
    control=None;control_directory=None;host_environment=None
    terminals={};shell_names={'Terminal'};manager_mode=False;terminal_pointer=None;touch=None;touch_error=None
    keyboard=None;keyboard_router=None;keyboard_error=None
    from terminal_keys import TerminalKeys
    terminal_keys=TerminalKeys(time.monotonic,enabled=os.environ.get("TERM")!="linux" and args.keyboard_device is None and args.keyboard_fd is None)
    def app_pointer(form,event,column,row,width,route):
        before=pointer_trace.state(form) if pointer_trace.path else None
        handled=native_pointer(form,column,row,width,event[1],event[4],event=event) if args.navigation_trial else deliver_pointer(form,event,column,row,width)
        pointer_trace.record(host,form,event,column,row,width,route,before,handled)
        return handled
    pointer_trace.input_source=lambda:touch.diagnostics() if touch is not None else None
    def cancel_touch():
        nonlocal terminal_pointer
        if terminal_pointer is not None:terminal_pointer.pointer(0,0,0,True);terminal_pointer=None
        if touch is not None:touch.cancel(host)
        host.finish(False);host.pointer_origin=None;panel.cancel()
        for name,form in host.app_forms.items():
            if hasattr(form,'reset_double_tap'):form.reset_double_tap()
            if getattr(form,'pointer_captured',False):
                if hasattr(form,'cancel_pointer'):form.cancel_pointer()
                else:form.pointer(0,0,host.window(name).w-2,0,True)
    tabs = [(w.name, w.name+' ') for w in windows]
    resized = False
    def on_resize(signum, frame):
        nonlocal resized
        resized = True
        try: inbox.writable.send(b'r')
        except BlockingIOError: pass
    def cycle(options,current,setter,direction):
        choices=tuple(options)
        setter(choices[(choices.index(current)+direction)%len(choices)])
    def dock(direction):
        nonlocal resized
        if panel.mode=='auto':panel.set_mode(panel.resolved_mode(geometry.columns))
        for _ in range(1 if direction>0 else 3):panel.rotate()
        resized=True
    def panel_count(direction):
        nonlocal resized
        resized=(panel.add() if direction>0 else panel.remove_empty()) or resized
    def panel_presentation(direction):
        nonlocal resized
        cycle(MODES,panel.mode,panel.set_mode,direction);resized=True
    def toggle_animation(direction):
        host.settle();host.set_preference('animate',not host.animate)
    def toggle_backdrop(direction):
        host.set_background_enabled(not host.background_enabled)
    settings_items=[
        ('Frame style',lambda:host.style,lambda d:cycle(STYLES,host.style,host.set_style,d)),
        ('Colors',lambda:host.palette,lambda d:cycle(PALETTES,host.palette,host.set_palette,d)),
        ('Background',lambda:host.effect,lambda d:cycle(EFFECTS,host.effect,host.set_effect,d)),
        ('Backdrop enabled',lambda:'on' if host.background_enabled else 'off',toggle_backdrop),
        ('Animation',lambda:'on' if host.animate else 'off',toggle_animation),
        ('Animation time',lambda:slider(round(host.animation_duration*1000)),lambda d:host.set_preference('animation_duration',max(.04,min(.32,round(host.animation_duration+d*.04,2))))),
        ('Move drawing',lambda:host.move_mode,lambda d:host.set_preference('move_mode','live' if host.move_mode=='outline' else 'outline')),
        ('Resize drawing',lambda:host.resize_mode,lambda d:host.set_preference('resize_mode','live' if host.resize_mode=='outline' else 'outline')),
        ('Panel dock',lambda:panel.selected.dock,dock),
        ('Panels (+ / -)',lambda:str(len(panel.panels)),panel_count),
        ('Focused click',lambda:'minimize' if host.focused_button_minimizes else 'keep open',lambda d:host.set_preference('focused_button_minimizes',not host.focused_button_minimizes)),
        ('Compositing',lambda:'opaque text; shaded overview',lambda d:None),
    ]
    settings_items.insert(4,('Overview shade',lambda:f'[{"="*round(host.overview_opacity*8):<8}] {round(host.overview_opacity*100)}%',lambda d:host.set_overview_opacity(round(max(0,min(1,host.overview_opacity+d*.1)),2))))
    rows={row[0]:row for row in settings_items}
    title_controls=('Title controls',lambda:'auto ('+host.control_side()+')' if host.window_controls=='auto' else host.window_controls,lambda d:cycle(('auto','left','right'),host.window_controls,host.set_window_controls,d))
    window_rows=[c.row() for c in shared_controls['windows']]
    def close_settings():
        nonlocal manager_mode
        host.close('Settings')
        focused=host.focus
        app_focused=focused in (set(terminals)|set(host.app_forms)|{'Calendar'}) and host.shown(host.window(focused)) and not host.window(focused).rolled
        manager_mode=not app_focused if args.navigation_trial else True
    from scenery import Library as SceneryLibrary,rows as scenery_rows
    scenery_library=SceneryLibrary(args.scenery_library)
    settings=SettingsManager([
        ('Appearance',(' ▄▀▄ ',' ▀▄▀ ','  Aa '),'Colors, fonts and presentation',[('Style',[rows['Colors']]),('Windows',[window_rows[1],('Show underlying text',lambda:'on' if host.show_underlying_text else 'off',lambda d:host.set_show_underlying_text(not host.show_underlying_text))]),('Fonts',font_preview.settings_rows())]),
        ('Window Manager',('╭───╮','│   │','╰───╯'),'Frames, focus and effects',[
            ('Style',[rows['Frame style'],title_controls,window_rows[0]]),
            ('Behavior',[rows['Focused click'],rows['Move drawing'],rows['Resize drawing'],('Resize borders',lambda:'on' if host.resize_edges else 'off',lambda d:host.set_preference('resize_edges',not host.resize_edges)),('Desktop wheel',lambda:'on' if host.desktop_scroll else 'off',lambda d:host.set_preference('desktop_scroll',not host.desktop_scroll))]),
            ('Compositor',[rows['Overview shade']]+[c.row() for c in shared_controls['shadows']]),
            ('Motion',[rows['Animation'],rows['Animation time'],('Mouse trails',lambda:'on' if host.mouse_trails else 'off',lambda d:host.set_mouse_trails(not host.mouse_trails))]+[c.row() for c in shared_controls['arrival']])]),
        ('Desktop',('  /\\ ', ' /~~\\', '/\\/\\'),'Backgrounds and landscape',[
            ('Background',[rows['Background'],rows['Backdrop enabled']]),
            ('Scenery',scenery_rows(host,scenery_library)),
            ('Nature',[c.row() for c in shared_controls['sky']]+[('Scene speed',lambda:f'{host.nature_rate:g}x',lambda d:cycle((1,10,30,60),host.nature_rate,host.set_nature_rate,d)),('Forest seed',lambda:str(host.scene_seed),lambda d:None)]),
            ('Flux',[c.row() for c in shared_controls['flux']]),
            ('Flurry',[c.row() for c in shared_controls['flurry']]),
            ('View',[c.row() for c in shared_controls['view']]+[('Desktop pager',lambda:'on' if host.show_pager else 'off',lambda d:host.set_pager(not host.show_pager)),('Pager position',lambda:host.pager_position,lambda d:cycle(('bottom left','bottom right','top left','top right'),host.pager_position,lambda v:host.set_preference('pager_position',v),d))])]),
        ('Applications',(' ┃≡ ',' ┃≡ ',' ┃≡ '),'Lists, status and time',[
            ('Lists',[
                ('Scrollbars',lambda:host.list_scrollbars,lambda d:cycle(('auto','on','off'),host.list_scrollbars,lambda v:host.set_preference('list_scrollbars',v),d)),
                ('Position counts',lambda:host.list_counts,lambda d:cycle(('auto','on','off'),host.list_counts,lambda v:host.set_preference('list_counts',v),d)),
                ('Status detail',lambda:host.status_verbosity,lambda d:cycle(('compact','detailed'),host.status_verbosity,lambda v:host.set_preference('status_verbosity',v),d))]),
            ('Map gestures',[map_form.double_tap_row()] if station_enabled else []),
            ('Time',[
                ('Time zone',lambda:host.timezone_name,lambda d:cycle(tuple(dict.fromkeys(('UTC','America/Los_Angeles','Europe/London','Asia/Tokyo',host.timezone_name))),host.timezone_name,lambda v:host.set_preference('timezone_name',v),d))])]),
        ('Panel',('┌─┬─┐','├─┼─┤','└─┴─┘'),'Position and widgets',[
            ('Layout',[('Edit panels',lambda:'off (locked)' if panel.locked else 'on',lambda d:panel.set_locked(not panel.locked)),('Presentation',lambda:panel.mode, panel_presentation),rows['Panel dock'],rows['Panels (+ / -)']]),
            ('Items',[('Clock',lambda:'on' if host.show_clock else 'off',lambda d:host.set_preference('show_clock',not host.show_clock)),('Connectivity',lambda:'on' if host.show_connectivity else 'off',lambda d:host.set_preference('show_connectivity',not host.show_connectivity)),('Demo link',lambda:'up' if link.connected else 'down',lambda d:inbox.submit(lambda:Link(not link.connected,'synthetic')))])]),
        ('Terminal',('╭───╮','│>_ │','╰───╯'),'Shell background',[
            ('Appearance',[Slider('Background opacity',lambda:host.terminal_opacity,host.set_terminal_opacity,0,1,.05,lambda v:f'{v*100:.0f}%').row()]),
            ('Keys',[Choice('WM escape',lambda:host.wm_escape,host.set_wm_escape,WM_ESCAPES).row(),('Send escape',lambda:'WM then Ctrl-V',lambda d:None)])]),
        ('About',(' ╭─╮ ',' │i│ ',' ╰─╯ '),'Session and framework',[
            ('Session',[rows['Compositing'],('Layout memory',lambda:'on' if store.enabled else 'off (--no-save / minimal)',lambda d:None)]),
            ('Build',[(label,lambda value=value:value,lambda d:None) for label,value in build_identity.details()])])]+list(registered_apps.settings_categories()),close=close_settings)
    def open_registered_settings(category):
        settings.category=category;host.activate('Settings')
    registered_apps.settings_opener=open_registered_settings
    from scenery_app import SceneryApp
    host.app_forms['Scenery']=SceneryApp(host,scenery_library,lambda:host.close('Scenery'))
    host.app_forms['Scenery'].restore_session(getattr(host,'app_view_state',{}).get('Scenery',{}))
    from help_browser import HelpBrowser
    help_browser=HelpBrowser(forms=host.app_forms,global_pages=host.help_pages(),close=lambda:host.close('Help'))
    help_browser.restore_session(getattr(host,'app_view_state',{}).get('Help',{}))
    host.app_forms['Help']=help_browser
    def show_help():
        nonlocal help_browser,manager_mode
        if host.focus=='Help' and host.shown(host.window('Help')):
            host.close('Help');return
        previous=host.focus;state=help_browser.session_state()
        help_browser=HelpBrowser(forms={name:form for name,form in host.app_forms.items() if name!='Help'},global_pages=host.help_pages(),close=lambda:host.close('Help'))
        help_browser.restore_session(state);help_browser.open_context(previous)
        host.app_forms['Help']=help_browser;store.bind_app('Help',help_browser)
        store.changed('app','Help');host.activate('Help');manager_mode=False
    if args.scenery_tune:
        host.set_effect('terrain');host.set_preference('background_enabled',True)
        settings.category='Desktop';settings.pages['Desktop'].section=1
        host.activate('Settings')
    if app_gallery is not None:
        host.app_forms['Kitchen Sink'].sections.insert(0,('Apps',[Button(app.name,lambda name=app.name:host.activate(name)).row() for app in app_gallery.APPS]))
        host.app_forms['Kitchen Sink'].sections.extend([
            ('Panes',[Button('Edit app layout',lambda:host.activate('Layout Edit')).row(),Button('Open Pane Lab',lambda:host.activate('Pane Lab')).row()]),
            ('Docks',settings_items[9:12])])
    entries=[('Desktop overview','overview'),('Keyboard help','help'),('Edit panels','panels:edit')]
    if not args.minimal:entries.extend([('App layout preview','demo-workspace'),('Flurry background','screensaver')])
    legacy_names={app.name for app in terminal_fallbacks}
    shadow_names={app.name for app in workspace if app.name not in host.app_forms} if native_defaults else set()
    legacy_entries=[(w.name,'window:'+w.name) for w in windows if w.name in legacy_names]
    launcher=Launcher([(w.name,'terminal:new' if w.name=='Terminal' else 'window:'+w.name) for w in windows if w.name not in legacy_names|shadow_names|set(registered_apps.by_title)]+list(registered_apps.menu_entries())+entries,groups={'Legacy':legacy_entries} if legacy_entries else {})
    from entity_actions import ContextActions
    entity_actions=ContextActions();context_commands={}
    entity_actions.register('observation','Inspect record',lambda entity:entity.payload['inspect'](entity.payload['identity']))
    if station_directory:
        def station_action(entity,action):
            if not station_directory.select(entity.key):host.activate('Stations');return
            if action=='open':host.activate('Stations');return
            map_form.focus_selection()
            if action=='follow':map_form.tracks.follow(entity.key)
            host.activate('Station Map')
        for label,action in (('Open station','open'),('Show on map','map'),('Follow on map','follow')):
            entity_actions.register('station',label,lambda entity,action=action:station_action(entity,action))
    def open_launcher(pointer=None):
        nonlocal manager_mode
        manager_mode=True
        host.finish(False);panel.cancel()
        if pointer is not None:host.launcher_anchor=(*pointer,1,1)
        else:
            button=next((hit for p in panel.panels for hit in p.hits if hit[3]=='key:,'),None)
            host.launcher_anchor=(button[0]-ox,button[1]-oy,button[2],1) if button else None
        launcher.open()

    def open_entity_menu(entities,pointer):
        actions=entity_actions.entries(entities)
        if not actions:return False
        open_launcher(pointer);context_commands.clear()
        for index,(_,command) in enumerate(actions):context_commands['context:'+str(index)]=command
        launcher.open_context('Actions',[(label,'context:'+str(index)) for index,(label,_) in enumerate(actions)])
        return True

    def launch(action):
        nonlocal manager_mode,metrics
        if action.startswith('app:'):
            registered_apps.open(action[4:]);manager_mode=False;return
        if action.startswith('context:'):
            command=context_commands.get(action)
            if command:command()
            manager_mode=False;context_commands.clear();return
        if action=='panels:edit':panel.set_locked(False);manager_mode=True;return
        if action=='terminal:new':
            number=1;name='Terminal'
            while name in host.focus_order and host.window(name).opened:
                number+=1;name=f'Terminal {number}'
            if name not in host.focus_order:
                ww,hh=min(82,host.width),min(26,host.work_height)
                offset=(number-1)%5
                window=Window(name,min(max(0,(host.width-ww)//2)+offset*2,host.width-ww),min(offset,host.work_height-hh),ww,hh,visible=False,opened=False)
                host.add_window(window,transient=True);windows.append(window);shell_names.add(name);host.session_shells.add(name)
                host.session_changed('structure')
            host.window(name).desktop=host.desktop
            action='window:'+name
        if action.startswith('window:'):
            name=action[7:]
            if name in registered_apps.by_title:
                registered_apps.open(registered_apps.by_title[name]);manager_mode=False;return
            if name=='Help':show_help();return
            if name=='Render Debug' and metrics is None:
                from draw_metrics import Metrics
                metrics=Metrics()
            if name=='Walk' and radio and radio.source and hasattr(radio.source,'request_walks'):radio.source.request_walks(time.time())
            if name=='CW' and name in host.app_forms:
                if host.app_forms[name]._closed:
                    from native_cw import CW
                    host.app_forms[name]=CW()
                host.window_cleanup[name]=host.app_forms[name].close
            if name in {a.name for a in workspace+terminal_fallbacks} and name not in host.app_forms and name not in terminals:
                from terminal_host import Terminal
                app=next(a for a in workspace+terminal_fallbacks if a.name==name)
                terminals[name]=Terminal(host,name,app.argv,selector,env=host_environment,metrics=metrics)
            elif name in shell_names and name not in terminals:
                from terminal_host import Terminal,shell_argv
                host.window(name).desktop=host.desktop
                terminals[name]=Terminal(host,name,shell_argv(),selector,env=host_environment,metrics=metrics,show_cursor=True,blend_background=True)
            elif name in terminals and (terminals[name].closed or terminals[name].eof):
                old=terminals[name];old.close()
                from terminal_host import Terminal
                terminals[name]=Terminal(host,name,old.argv,selector,env=old.environment,cwd=old.cwd,metrics=metrics,show_cursor=old.show_cursor,blend_background=old.blend_background)
            if name=='Settings':settings.overview()
            host.activate(name);manager_mode=False
            if name in terminals:
                # Activation must not flush keystrokes queued during the handoff.
                tty.setraw(sys.stdin,when=termios.TCSANOW);manager_mode=False
        elif action=='screensaver':
            host.set_effect('flurry')
        elif action=='demo-workspace' and demo_apps is not None:demo_apps.open_workspace(host)
        elif action=='overview':host.toggle_overview()
        elif action=='help':show_help()
    presentation=Presentation()
    screensaver_last=None
    demo_tick=-1
    stopping=False
    def on_stop(signum,frame):
        nonlocal stopping
        stopping=True
        try:inbox.writable.send(b'q')
        except BlockingIOError:pass
    stop_handlers={sig:signal.signal(sig,on_stop) for sig in (signal.SIGHUP,signal.SIGTERM)}
    previous_resize = signal.signal(signal.SIGWINCH,on_resize)
    first_frame=True
    mouse_tracking=None
    mirror_due=time.monotonic()+mirror_plan.delay if mirror_plan and mirror_plan.child else None
    def sync_keyboard():
        prepare_gestures(host,panel,launcher,manager_mode=manager_mode)
        active=not (manager_mode or launcher.active or host.overview or host.screensaver or host.drag or host.help_lines or host.settings_lines)
        window=host.window(host.focus) if host.focus else None
        form=host.app_forms.get(host.focus) if active and window is not None and host.shown(window) and not window.rolled else None
        if keyboard_router is not None:keyboard_router.select(form)
        terminal_keys.select(form)
        host.input_status=dict(hardware=keyboard_router.status() if keyboard_router is not None else None,error=keyboard_error,terminal=terminal_keys.status())
        report=host.input_status['hardware']
        if report is not None:
            source='evdev down='+str(report['down'])+' suppressed='+str(report['suppressed'])+' modifiers='+str(report['modifiers'])
            routing='foreground='+str(report['foreground'])+' target='+str(report['target'])
        else:
            report=host.input_status['terminal'];source='terminal releases='+str(report['confirmed'])+' focused='+str(report['focused'])
            routing='foreground='+str(report['router']['foreground'])+' target='+str(report['router']['target'])
        host.input_diagnostics=dict(source=source,routing=routing,error=keyboard_error or '')
    try:
        if args.keyboard_device is not None or args.keyboard_fd is not None:
            try:
                from keyboard_runtime import KeyboardRouter,console_foreground,take_keyboard
                keyboard=take_keyboard(args.keyboard_device,fd=args.keyboard_fd)
                keyboard_router=KeyboardRouter(keyboard,foreground=lambda:console_foreground(sys.stdin.fileno()))
                selector.register(keyboard,selectors.EVENT_READ)
            except (OSError,ValueError) as error:
                if keyboard is not None:keyboard.close()
                keyboard=None;keyboard_router=None;keyboard_error=str(error)
                print('Hardware motion keyboard unavailable; using terminal keys: '+keyboard_error,file=sys.stderr)
        if args.touch_device:
            try:
                from touch_evdev import TouchSource,display
                if args.touch_acquisition=='process':
                    from touch_process import ProcessTouchSource
                    TouchSource=ProcessTouchSource
                pixels=tuple(map(int,args.touch_display.lower().split('x')))
                if len(pixels)!=2:raise ValueError('touch display must be WIDTHxHEIGHT')
                touch=TouchSource(args.touch_device,args.touch_calibration,display(*pixels,args.touch_rotation),geometry.columns,geometry.rows)
                selector.register(touch,selectors.EVENT_READ)
            except (OSError,ValueError) as error:parser.error('touch unavailable: '+str(error))
        if args.legacy_aprs:tty.setraw(sys.stdin,when=termios.TCSANOW)
        else:tty.setcbreak(sys.stdin)
        sys.stdout.write(console_wake()+'\x1b[?1049h\x1b[?25l\x1b[2J\x1b[?1002h\x1b[?1006h')
        sys.stdout.write(terminal_keys.start());sys.stdout.flush()
        if args.legacy_aprs:
            from terminal_host import Terminal
            command=[sys.executable,str(args.legacy_aprs.resolve()),'--socket',args.aprs_socket,'--maps',str(args.aprs_maps.resolve()),'--map-engine','next','--tui-theme','color']
            if args.aprs_history:command+=['--history',str(args.aprs_history.resolve())]
            terminals[terminal_name]=Terminal(host,terminal_name,command,selector,metrics=metrics)
        if workspace or native_defaults:
            from terminal_host import Terminal
            from desktop_control import Control
            control_directory=tempfile.TemporaryDirectory(prefix='cw-ui-')
            def activate_owned(name):
                nonlocal model_inputs
                name={'Stations':'Directory','Heard Stations':'Directory'}.get(name,name)
                if name not in host.focus_order:raise RuntimeError('Application is not registered: '+name)
                launch('window:'+name)
                model_inputs=True
            from desktop_actions import dispatch as app_command
            def control_command(request):
                nonlocal model_inputs
                result=app_command(host,launch,build_identity.IDENTITY,request)
                if request.get('command') not in ('status','radio-status'):model_inputs=True
                return result
            control=Control(Path(control_directory.name)/'desktop.sock',selector,activate_owned,
                            command=control_command)
            host.control_path=str(control.path)
            environment=dict(os.environ,TERM='xterm-256color',COLORTERM='truecolor',N810_DESKTOP_SOCKET=str(control.path))
            host_environment=environment
            for key in ('TMUX','TMUX_PANE'):environment.pop(key,None)
            for app in workspace:
                if host.window(app.name).opened and app.name not in host.app_forms:terminals[app.name]=Terminal(host,app.name,app.argv,selector,env=environment,metrics=metrics)
            if workspace and not store.loaded and not args.native_stations:host.activate(workspace[0].name)
            tty.setraw(sys.stdin,when=termios.TCSANOW)
        # Restore shell slots, never shell history or previously executed commands.
        shell_names.update(host.session_shells)
        for name in host.session_shells:
            if host.window(name).opened:
                from terminal_host import Terminal,shell_argv
                terminals[name]=Terminal(host,name,shell_argv(),selector,env=host_environment,metrics=metrics,show_cursor=True,blend_background=True)
        if any(name in terminals for name in shell_names):tty.setraw(sys.stdin,when=termios.TCSANOW)
        if args.terminal and not host.window('Terminal').opened:launch('terminal:new')
        if args.scenery_app:host.activate('Scenery')
        if native_catalog:
            from native_catalog import reconcile_views
            reconcile_views(host)
        host.reconcile_interaction()
        store.bind(host,panel,time.monotonic())
        startup['ui_ready_seconds']=time.monotonic()-_BOOT_STARTED
        from model_deadlines import ModelDeadlines
        model_schedule=ModelDeadlines();model_view=None;model_inputs=True;model_deferred=False;model_full_deferred=False
        events=()
        while True:
            if stopping:break
            iteration_start=metrics.begin() if metrics else None
            input_events = decoder.feed(b'', expire=not events)
            quit_now = False
            for key, _ in events:
                if keyboard is not None and key.fileobj is keyboard:
                    try:input_events.extend(keyboard.drain())
                    except (OSError,ValueError) as error:
                        keyboard_error=str(error);selector.unregister(keyboard);keyboard_router.close();keyboard=None
                    continue
                if control is not None and (key.data is control or key.data in control.clients):
                    key.data.ready(_);continue
                if touch is not None and key.fileobj is touch:
                    try:
                        input_events.extend(drain_touch_ready(touch,pointer_trace))
                    except (OSError,ValueError) as error:
                        cancel_touch();selector.unregister(touch);touch.close();touch=None;touch_error=str(error)
                    continue
                if key.data in terminals.values():
                    key.data.ready(_);continue
                if key.fileobj is inbox.readable:
                    for ok, value in inbox.drain():
                        if ok:
                            host.set_weather(value) if isinstance(value,Weather) else world.apply(value) if not isinstance(value,Link) else None
                            if isinstance(value,Link):link=value
                        else:
                            host.content('Conversations', str(value), ('Provider error: '+str(value),))
                    continue
                if key.fileobj is sys.stdin:
                    raw=os.read(sys.stdin.fileno(),4096)
                    if not raw:
                        terminal_keys.cancel()
                        if keyboard_router is not None:keyboard_router.cancel()
                        quit_now=True
                    else:input_events.extend(decoder.feed(raw))
            if input_events:
                wake=console_wake()
                if wake:
                    sys.stdout.write(wake);sys.stdout.flush()
            # Debug can enable metrics during dispatch. Finish only the sample
            # started here, on the same metrics owner, even if it changes later.
            input_timing=None
            if metrics and input_events:
                metrics.input(terrain_pending=bool(host.terrain_renderer and host.terrain_renderer.pending and not host.terrain_renderer.pending.done()))
                input_timing=(metrics,metrics.begin())
            for event in input_events:
                sync_keyboard()
                prepare_gestures(host,panel,launcher,event,manager_mode=manager_mode)
                if event[0]=='keyboard_flags':
                    sys.stdout.write(terminal_keys.flags(event[1]));sys.stdout.flush();continue
                if event[0]=='focus' and not event[1]:cancel_touch()
                event=terminal_keys.event(event)
                if event is None:continue
                if event[0]=='touch_cancel' or event[0]=='mouse' and not event[4] and event[1] in (0,1,2):terminal_keys.cancel()
                if keyboard_router is not None and keyboard_router.event(event):continue
                if keyboard_router is not None and (event[0]=='touch_cancel' or event[0]=='mouse' and not event[4] and event[1] in (0,1,2)):
                    keyboard_router.cancel()
                if event[0]=='touch_cancel':cancel_touch();continue
                if event[0] == 'mouse':
                    _, button, x, y, released = event
                    pressed=not released and button in (0,1,2)
                    host.report_mouse(x-ox,y-oy)
                    if launcher.active:
                        if button==0 and not released:
                            left,top,mw,mh=host.launcher_bounds()
                            row=y-oy-top-2
                            if left<=x-ox<left+mw and 0<=row<len(launcher.matches()):
                                launcher.index=row
                                action=launcher.key('\r')
                                if action:launch(action)
                            else:launcher.active=False
                        continue
                    if host.help_lines:continue
                    if host.drag and host.pointer_origin is not None and (released or button&32):
                        # A title/edge gesture remains owned by the window manager
                        # while crossing app contents or a docked panel.
                        host.pointer(button,x-ox,y-oy,released)
                        continue
                    if terminal_pointer is not None and (released or button&32):
                        terminal=terminal_pointer;w=host.window(terminal.name)
                        terminal.pointer(button,max(0,min(w.w-3,x-ox-w.x-1)),max(0,min(w.h-3,y-oy-w.y-1)),released)
                        if released:terminal_pointer=None
                        continue
                    captured=next(((name,form) for name,form in host.app_forms.items() if getattr(form,'pointer_captured',False)),None)
                    if captured and (released or button&32):
                        name,form=captured;w=host.window(name)
                        app_pointer(form,event,x-ox-w.x-1,y-oy-w.y-1,w.w-2,'captured')
                        continue
                    if pressed:
                        sx,sy=x-ox,y-oy
                        target=next((w for w in reversed(host.windows) if host.shown(w) and w.x<=sx<w.x+w.w and w.y<=sy<w.y+w.rect[3]),None)
                        manager_mode=not (target and target.name in (set(terminals)|set(host.app_forms)|{'Settings','Calendar'}) and not target.rolled and target.x<sx<target.x+target.w-1 and target.y<sy<target.y+target.h-1 and not panel.at(x,y))
                    if button==2 and not released:
                        hit=next((w for w in reversed(host.windows) if host.shown(w) and w.x<=x-ox<w.x+w.w and w.y<=y-oy<w.y+w.rect[3]),None)
                        if hit and hit.name in terminals and not hit.rolled and hit.x<x-ox<hit.x+hit.w-1 and hit.y<y-oy<hit.y+hit.h-1 and terminals[hit.name].pointer(button,x-ox-hit.x-1,y-oy-hit.y-1,False):
                            host.select(hit.name);terminal_pointer=terminals[hit.name];continue
                        form=host.app_forms.get(hit.name) if hit and not hit.rolled else None
                        if form is not None and hasattr(form,'entities_at') and hit.x<x-ox<hit.x+hit.w-1 and hit.y<y-oy<hit.y+hit.h-1:
                            entities=form.entities_at(x-ox-hit.x-1,y-oy-hit.y-1)
                            if open_entity_menu(entities,(x-ox,y-oy)):
                                host.select(hit.name);continue
                        open_launcher((x-ox,y-oy))
                        continue
                    if panel.at(x,y) or panel.drag or panel.pending_drag:
                        if released and host.pointer_origin and not panel.drag:
                            host.pointer(button,x-ox,y-oy,True)
                        elif button & 64 and not released:
                            host.relative_desktop(1 if button & 1 else -1)
                        else:
                            action=panel.pointer(button,x,y,released)
                            if action=='panel:done':panel.set_locked(True)
                            elif action=='layout':resized=True
                            elif action:
                                if action=='key:,':open_launcher()
                                elif action=='key:?':show_help()
                                elif action=='key:d':host.toggle_overview()
                                elif action=='wm:toggle':manager_mode=not manager_mode
                                elif action=='wm:previous':host.cycle_focus(True);manager_mode=False
                                elif action=='wm:app-back':
                                    if host.overview:host.toggle_overview()
                                    elif host.focus=='Station Map':launch('window:Stations')
                                elif action.startswith('key:'):input_events.append(('key',action[4:]))
                                elif action.startswith('@'):host.switch(int(action[1:]))
                                elif action.startswith('launch:'):launch(action[7:])
                                elif action.startswith('radio:'):launch('window:Radio')
                                elif action.startswith('system:'):launch('window:System')
                                else:
                                    if action in terminals and (terminals[action].closed or terminals[action].eof):launch('window:'+action)
                                    else:
                                        host.task_click(action)
                                        if action in set(terminals)|set(host.app_forms)|{'Settings','Calendar'} and host.shown(host.window(action)) and not host.window(action).rolled:manager_mode=False
                    else:
                        sx,sy=x-ox,y-oy
                        if host.overview or host.screensaver:
                            host.pointer(button,sx,sy,released);continue
                        hit=next((w for w in reversed(host.windows) if host.shown(w) and w.x<=sx<w.x+w.w and w.y<=sy<w.y+w.rect[3]),None)
                        if hit and hit.name in terminals and not hit.rolled and hit.x<sx<hit.x+hit.w-1 and hit.y<sy<hit.y+hit.h-1 and not host.drag:
                            if pressed:host.select(hit.name)
                            if terminals[hit.name].pointer(button,sx-hit.x-1,sy-hit.y-1,released) and not released and button in (0,1,2):terminal_pointer=terminals[hit.name]
                        elif hit and hit.name in host.app_forms and hasattr(host.app_forms[hit.name],'pointer') and not hit.rolled and hit.x<sx<hit.x+hit.w-1 and hit.y<sy<hit.y+hit.h-1 and not host.drag:
                            if pressed:host.select(hit.name)
                            form=host.app_forms[hit.name]
                            app_pointer(form,event,sx-hit.x-1,sy-hit.y-1,hit.w-2,'hit')
                        elif hit and hit.name=='Calendar' and not hit.rolled and hit.x<sx<hit.x+hit.w-1 and hit.y<sy<hit.y+hit.h-1 and not host.drag:
                            if button==0 and not released:
                                host.select('Calendar');calendar_view.key('left' if sx<hit.x+hit.w//2 else 'right')
                            elif button&64 and not released:calendar_view.key('right' if button&1 else 'left')
                        elif hit and hit.name=='Settings' and not hit.rolled and hit.x<sx<hit.x+hit.w-1 and hit.y<sy<hit.y+hit.h-1 and not host.drag:
                            if pressed:host.select('Settings')
                            if args.navigation_trial:native_pointer(settings,sx-hit.x-1,sy-hit.y-1,hit.w-2,button,released)
                            else:settings.pointer(sx-hit.x-1,sy-hit.y-1,hit.w-2,button,released)
                        else:host.pointer(button,sx,sy,released)
                    continue
                char = event[1]
                if keyboard_router is not None and keyboard_router.suppress_tty(char):continue
                if phone_action(char,host,launcher,open_launcher):
                    manager_mode=char=='wm-menu' or host.overview
                    continue
                if args.navigation_trial and char in ('f6','shift-f6'):
                    launcher.active=False
                    if host.help_lines:host.toggle_help()
                    host.cycle_focus(char=='shift-f6');manager_mode=False;continue
                if launcher.active:
                    action=launcher.key(char)
                    if action:launch(action)
                    continue
                if host.help_lines:
                    if char in ('?','help','\x1b'):host.toggle_help()
                    elif char in ('right','down'):host.help_step(1)
                    elif char in ('left','up'):host.help_step(-1)
                    continue
                if host.screensaver and char!='q':
                    host.screensaver=False;host.set_effect(host.screensaver_effect)
                    for p in panel.panels:p.cache=None
                    continue
                if char=='\x1b' and not panel.locked:
                    panel.set_locked(True);continue
                if (terminals or host.app_forms) and char==WM_ESCAPES[host.wm_escape]:manager_mode=not manager_mode;continue
                if manager_mode and char=='\x16':
                    if host.focus in terminals:terminals[host.focus].key(WM_ESCAPES[host.wm_escape])
                    manager_mode=False;continue
                if host.focus in terminals and not manager_mode and not host.overview and not host.drag and host.shown(host.window(host.focus)):
                    if char in ('f6','shift-f6'):host.cycle_focus(char=='shift-f6')
                    else:terminals[host.focus].key(char)
                    continue
                if char=='context-menu' and not manager_mode and not host.overview and not host.drag:
                    form=host.app_forms.get(host.focus)
                    if form is not None and hasattr(form,'selected_entities'):
                        window=host.window(host.focus)
                        if open_entity_menu(form.selected_entities(),(window.x+2,window.y+2)):continue
                if not manager_mode and not host.overview and not host.drag:
                    form=host.app_forms.get(host.focus)
                    if host.focus=='Settings':form=settings
                    elif host.focus=='Calendar':form=calendar_view
                    if form is not None and host.shown(host.window(host.focus)):
                        if char in ('f6','shift-f6'):host.cycle_focus(char=='shift-f6')
                        else:
                            handled=native_key(form,char) if args.navigation_trial else form.key(char)
                            if not handled and char in ('?','help'):show_help()
                        # A declined app key is unused, never a WM command.
                        continue
                if char == 'q':
                    quit_now = True
                elif char in ('\t','backtab','f6','shift-f6'): host.cycle_focus(char in ('backtab','shift-f6'))
                elif char in ('X','Z'):
                    name=host.overview_selection if host.overview else host.focus
                    if name:(host.close if char=='X' else host.maximize)(name)
                elif char in ('[','desktop-left'): host.relative_desktop(-1)
                elif char in (']','desktop-right'): host.relative_desktop(1)
                elif char in '{}': host.relative_desktop(-1 if char == '{' else 1,carry=True)
                elif char in (',',' '):
                    open_launcher()
                elif char in ('?','help'): show_help()
                elif char == 'P':
                    if not panel.locked:panel.rotate();resized=True
                elif char == 'D':
                    if not panel.locked and panel.remove_empty():resized=True
                elif char == 'N':
                    if not panel.locked and panel.add():resized=True
                elif char == 'x': host.toggle_tint()
                elif char == 'd': host.toggle_overview()
                elif char == 'w':
                    weather_index=(weather_index+1)%len(PRESETS)
                    observation=PRESETS[weather_index]
                    inbox.submit(lambda observation=observation: observation)
                elif char == 'e': host.set_effect(EFFECTS[(EFFECTS.index(host.effect)+1)%len(EFFECTS)])
                elif char == 't': host.set_style(tuple(STYLES)[(tuple(STYLES).index(host.style)+1)%len(STYLES)])
                elif char == 'c': host.set_palette(tuple(PALETTES)[(tuple(PALETTES).index(host.palette)+1)%len(PALETTES)])
                elif char == 'b':
                    host.set_background_enabled(not host.background_enabled)
                elif char == 'a':
                    host.settle()
                    host.set_preference('animate',not host.animate)
                elif char == 'M':
                    host.finish(False)
                    host.set_preference('move_mode','live' if host.move_mode == 'outline' else 'outline')
                elif char == 'R':
                    host.finish(False)
                    host.set_preference('resize_mode','live' if host.resize_mode == 'outline' else 'outline')
                elif char in ('1','2','3'): host.switch(int(char)-1)
                elif char in '!@#' and host.focus: host.send_to(host.focus, '!@#'.index(char))
                elif char == 'o' and host.focus: host.roll(host.focus)
                elif char == 'p' and host.focus: host.pin(host.focus)
                elif char in ('m','r'):
                    host.finish(False)
                    host.begin(char == 'r',host.overview_selection if host.overview else None); dx = dy = 0
                elif char in ('h','j','k','l','left','right','up','down') and host.drag:
                    dx += (char in ('l','right'))-(char in ('h','left'))
                    dy += (char in ('j','down'))-(char in ('k','up'))
                    host.motion(dx,dy)
                elif char in '\r\n':
                    if host.overview and host.drag is None and host.overview_selection:launch('window:'+host.overview_selection)
                    else:host.finish(True)
                elif char == '\x1b':
                    arranging=host.drag is not None
                    host.finish(False)
                    panel.cancel()
                    if host.help_lines: host.toggle_help()
                    if host.overview and not arranging: host.toggle_overview()
                elif char == 'v' and host.focus:
                    host.finish(False)
                    host.visibility(host.focus)
                elif char == 'u':
                    counter += 1
                    n = counter
                    inbox.submit(lambda n=n: [Record(1,'N0CALL','APRS observed',f'Synthetic observation {n}')])
            if input_timing is not None:input_timing[0].end('input_handlers',input_timing[1])
            sync_keyboard()
            # Control socket accept/read/write and status are observations.
            # Mutating control callbacks mark the model explicitly; real input,
            # provider/worker wakeups and existing deadlines retain their paths.
            # PTY readiness already patches terminal UI damage. EOF still
            # refreshes lifecycle state and the panel exit hint.
            model_events=any((control is None or key.data is not control and getattr(key.data,'owner',None) is not control)
                             and (touch is None or key.fileobj is not touch)
                             and (key.data not in terminals.values() or key.data.eof) for key,_ in events)
            model_inputs=model_inputs or model_events or bool(input_events)
            if quit_now: break
            view=(host.desktop,host.focus,host.overview,host.screensaver,host.mouse_trails)
            due_owners=model_schedule.due(time.monotonic())
            if 'panel' in due_owners:due_owners.add('form:Calendar')
            full_models=first_frame or model_inputs or model_full_deferred or resized or view!=model_view or 'all' in due_owners
            source_models=full_models or 'sources' in due_owners
            # Source dependencies remain conservative: one source revision may
            # affect several views. Fast form deadlines do not enter this path.
            full_models=full_models or source_models
            panel_models=full_models or 'panel' in due_owners
            refresh_models=full_models or bool(due_owners) or model_deferred
            serviced_owners=set()
            if not first_frame and (host.ui_damage or launcher.active):
                # WM/input updates already changed the retained model. Present
                # their damage before polling/rebuilding unrelated applications.
                host.set_launcher(launcher.lines())
                model_deferred=model_deferred or refresh_models
                model_full_deferred=model_full_deferred or full_models
                refresh_models=False
            model_start=metrics.begin() if metrics and refresh_models else None
            if mirror_due is not None and time.monotonic()>=mirror_due:
                if first_frame or host.terrain_loading or host.terrain_arrival is not None:
                    mirror_due=time.monotonic()+.05
                else:
                    mirror_due=None
                    if host.window(mirror_name).opened:
                        mw=host.window(mirror_name)
                        check=Panels(mode=panel.mode)
                        _,_,child_width,child_height=check.layout(max(1,mw.w-2),max(1,mw.h-2))
                        if child_width<40 or child_height<12:
                            from mirror import koan
                            host.content(mirror_name,('koan',mw.w,mw.h),koan(mw.w,mw.h))
                        else:
                            from terminal_host import Terminal
                            command=[sys.executable,str(Path(__file__).resolve()),'--mirror','--mirror-depth',str(args.mirror_depth+1),'--mirror-delay',str(args.mirror_delay),'--wm-escape',host.wm_escape,'--window-controls',host.window_controls,'--panel-mode',panel.mode]
                            if args.minimal:command.append('--minimal')
                            if args.no_animation:command.append('--no-animation')
                            if args.effect:command+=['--effect',args.effect]
                            if args.ascii:command.append('--ascii')
                            if args.palette:command+=['--palette',args.palette]
                            terminals[mirror_name]=Terminal(host,mirror_name,command,selector,metrics=metrics)
                            tty.setraw(sys.stdin,when=termios.TCSANOW)
            if mouse_tracking!=host.mouse_trails:
                mouse_tracking=host.mouse_trails
                sys.stdout.write('\x1b[?1002l\x1b[?1003h' if mouse_tracking else '\x1b[?1003l\x1b[?1002h')
            if host.screensaver!=screensaver_last:
                screensaver_last=host.screensaver
                for p in panel.panels:p.cache=None
                host.front=[None]*(host.width*host.height);host.invalidate((0,0,host.width,host.height))
            if resized:
                resized = False
                geometry = measure(sys.stdout.fileno())
                if trial:trial.viewport(geometry.columns,geometry.rows)
                if touch is not None:
                    cancel_touch()
                    if geometry.columns>=24 and geometry.rows>=6:touch.resize(geometry.columns,geometry.rows)
                    else:
                        selector.unregister(touch);touch.close();touch=None;touch_error='viewport too small'
                if geometry.columns >= 24 and geometry.rows >= 6:
                    ox,oy,width,height=panel.layout(*(trial.viewport(geometry.columns,geometry.rows) if trial else (geometry.columns,geometry.rows)))
                    host.reserved_bottom=panel.overlay_bottom;host.resize(width,height+panel.overlay_bottom)
                    host.origin=(ox,oy)
                    for p in panel.panels:p.cache=None
                    # Buffered ANSI uses the old geometry. Drop it and close
                    # any synchronized output before clearing the new viewport.
                    sys.stdout.write(presentation.close()+'\x1b[2J')
            if refresh_models:
                if metrics:
                    from draw_metrics import enable_renderer_timing
                    enable_renderer_timing(host)
                section_start=metrics.begin() if metrics else None
                if panel_models:
                    tabs = [(f'@{i}', f'{i+1}{"*" if i == host.desktop else ""} ') for i in range(3)] + [(w.name,host.window_label(w)) for w in host.task_windows()]
                    next_menu=launcher.lines()
                    host.set_launcher(next_menu)
                sw=host.window('Settings')
                if (full_models or 'form:Settings' in due_owners) and host.shown(sw) and not sw.rolled:
                    settings.width=max(8,sw.w-2);settings.height=max(4,sw.h-2)
                    lines=metrics.model_call('Settings','lines',settings.lines) if metrics else settings.lines()
                    spans=metrics.model_call('Settings','spans',settings.spans) if metrics else settings.spans()
                    if args.navigation_trial:lines,spans=native_presentation(settings,lines,spans,sw.w-2,sw.h-2)
                    host.content('Settings',lines,lines,spans)
                cw=host.window('Calendar')
                if (full_models or 'form:Calendar' in due_owners) and host.shown(cw) and not cw.rolled:
                    lines=metrics.model_call('Calendar','lines',calendar_view.lines,time.time()) if metrics else calendar_view.lines(time.time())
                    spans=()
                    if args.navigation_trial:lines,spans=native_presentation(calendar_view,lines,spans,cw.w-2,cw.h-2)
                    host.content('Calendar',lines,lines,spans)
                if metrics:metrics.end('model_header',section_start);section_start=metrics.begin()
                if source_models:
                    if radio:metrics.model_call('radio','update',radio.update) if metrics else radio.update()
                    if native_catalog and (metrics.model_call('catalog','update',native_catalog.update) if metrics else native_catalog.update()):
                        from native_catalog import reconcile_views
                        reconcile_views(host)
                        if station_directory:map_form.update_tracks(native_catalog.evidence)
                        try:messages_form.update(native_catalog.lines,outbox=native_catalog.outbox,records=native_catalog.bss_records)
                        except (ValueError,KeyError,TypeError):messages_form.notice='Messages unavailable'
                        if native_catalog.error:messages_form.notice='Offline';messages_form.diagnostics=str(native_catalog.error)
                        elif messages_form.notice=='Offline':messages_form.notice='Receive only'
                    if system_state:metrics.model_call('system','update',system_state.update) if metrics else system_state.update()
                    metrics.model_call('world','bind',bind) if metrics else bind()
                if full_models:
                    for name,terminal in terminals.items():
                        if not host.window(name).opened:terminal.close()
                        elif not terminal.closed:
                            terminal.child.poll();terminal.resize()
                            metrics.model_call(name,'present',terminal.present) if metrics else terminal.present()
                    if int(time.monotonic())!=demo_tick:
                        demo_tick=int(time.monotonic())
                        if demo_apps is not None:demo_apps.update(host,demo_tick)
                from app_widgets import configure_views
                time_display.configure(host.timezone_name)
                configure_views(host.list_scrollbars,host.list_counts,host.status_verbosity)
                if metrics:metrics.end('model_sources',section_start);section_start=metrics.begin()
                for index,application in enumerate(applications):
                    owner='application:'+str(index)
                    if full_models or owner in due_owners:
                        metrics.model_call('application-'+str(index),'poll',application.poll) if metrics else application.poll()
                        serviced_owners.add(owner)
                        # Application-owned forms share the application's view.
                        for name,form in host.app_forms.items():
                            if form is getattr(application,'view',None):due_owners.add('form:'+name)
                if metrics:metrics.end('model_applications',section_start);section_start=metrics.begin()
                for name in host.app_forms:
                    if not (full_models or 'form:'+name in due_owners):continue
                    serviced_owners.add('form:'+name)
                    w=host.window(name)
                    if hasattr(host.app_forms[name],'set_active'):
                        metrics.model_call(name,'set_active',host.app_forms[name].set_active,w.opened) if metrics else host.app_forms[name].set_active(w.opened)
                    if hasattr(host.app_forms[name],'poll'):
                        metrics.model_call(name,'poll',host.app_forms[name].poll) if metrics else host.app_forms[name].poll()
                    if not host.shown(w) and getattr(host.app_forms[name],'pointer_captured',False) and hasattr(host.app_forms[name],'cancel_pointer'):
                        host.app_forms[name].cancel_pointer()
                    if host.shown(w) and not w.rolled:
                        if name=='Render Debug' and metrics is None:
                            from draw_metrics import Metrics
                            metrics=Metrics()
                        form=host.app_forms[name]
                        if hasattr(form,'width'):form.width=max(8,w.w-2)
                        if hasattr(form,'height'):form.height=max(3,w.h-2)
                        lines=metrics.model_call(name,'lines',form.lines) if metrics else form.lines()
                        spans=(metrics.model_call(name,'spans',form.spans) if metrics else form.spans()) if hasattr(form,'spans') else ()
                        if args.navigation_trial:lines,spans=native_presentation(form,lines,spans,w.w-2,w.h-2)
                        layer=(metrics.model_call(name,'layer',form.layer) if metrics else form.layer()) if hasattr(form,'layer') else None
                        present_form_content(host,name,form,lines,spans,layer,metrics)
                if metrics:metrics.end('model_apps',section_start);section_start=metrics.begin()
                if panel_models:
                    settings.width=max(8,sw.w-2)
                    time_display.configure(host.timezone_name)
                    date_label,time_label=clock_widget.read(time.time())
                    native_launches={'Directory':('Stations','Stations'),'APRS':('Station Map','Map')} if station_app and args.native_stations else {}
                    radio_entries,radio_styles=radio.panel(width,args.ascii) if radio and (radio.path or radio.source) else ([],{})
                    if receive_status:
                        receive_status.update(time.monotonic())
                        if not receive_status.online:
                            radio_entries=[('receive:offline','! RX offline / retrying  ')]+radio_entries
                            radio_styles['receive:offline']='warning'
                    if system_state and radio_entries:
                        system_entries,system_styles=system_state.panel(width,args.ascii)
                        radio_entries=system_entries+radio_entries;radio_styles.update(system_styles)
                    back=('wm:app-back','back  ') if host.overview or host.focus=='Station Map' else ('wm:previous','prev  ')
                    desktop_buttons=[('key:,','menu  '),('key:?','?  ')]+tabs[:3]+[back,('key:d','windows  ')] if width>=80 else [('key:,','menu  '),back,('key:d','windows  ')]
                    widgets={'desktops':desktop_buttons,
                             'apps':[(('launch:window:'+native_launches.get(a.name,(a.name,a.name))[0]),native_launches.get(a.name,(a.name,a.name))[1]) for a in workspace]+[('launch:terminal:new','Terminal'),('launch:window:Settings','Settings')] if panel.mode!='bar' else [],
                             'clock':[('Calendar',(date_label.replace(' ','')+' ' if width>=120 else '')+time_label+' ')] if host.show_clock else [],
                             'connectivity':(radio_entries if radio_entries else [('Connectivity',link_label(link,args.ascii))] if not workspace else []) if host.show_connectivity or receive_status and not receive_status.online else [],
                             'windows':tabs[3:],
                             'appearance':[],
                             'weather':[]}
                    widgets['clock']=build_identity.panel_entries(width,widgets['clock'],widgets['connectivity'],desktop_buttons)+widgets['clock']
                    if host.focus in terminals:
                        prefix=host.wm_escape.replace('ctrl-','Ctrl-').replace('backslash','\\')
                        hint=f' WM: X close Z max | {prefix} app | Ctrl-V send ' if manager_mode else f' App exited | {prefix} WM ' if terminals[host.focus].eof else f' App keys | {prefix} WM '
                        widgets['windows']+=[('wm:toggle',hint)]
                    if touch_error:widgets['windows']+=[('key:?',' touch off ')]
                if full_models:serviced_owners.update(model_schedule.deadlines)
                serviced_owners.update(owner for owner in ('sources','panel','all') if owner in due_owners)
                model_inputs=False;model_view=view;model_deferred=False;model_full_deferred=False
                if metrics:metrics.end('model_panel',section_start)
            if metrics:
                if model_start is not None:metrics.end('model_layout',model_start)
                elif not refresh_models:metrics.add('model_layout_reused_chunks')
                metrics.add('flush_calls');metrics.add('damage_cells_before_flush',len(host.damage))
            pointer_trace.sample(host)
            host.observe_composition=metrics is not None
            if metrics and args.metrics:
                try:metrics.save_live(args.metrics.with_suffix('.live.json'),host,dict(build_identity.IDENTITY),presentation=presentation)
                except (OSError,ValueError,TypeError) as error:metrics.metadata['live_report_error']=str(error)
            # Keep optional metrics serialization/I/O outside draw timing.
            if metrics:phase_start=metrics.begin()
            camera_frame=host.camera_motion is not None
            static_ui=not host.background_enabled and not (host.drag or host.animations or host.slide or host.camera_motion or host.terrain_loading or host.terrain_arrival is not None)
            output,changed,computed=host.flush(width*height if host._native is not None or static_ui or first_frame and args.minimal or host.terrain_loading or host.terrain_arrival is not None else 2048,max_seconds=None if static_ui or first_frame and args.minimal else .012)
            if metrics and host.terrain_renderer and host.terrain_renderer.completed and 'terrain_ready_seconds' not in startup:
                startup['terrain_ready_seconds']=time.monotonic()-_BOOT_STARTED
                events=host.terrain_renderer.trace.snapshot()
                startup['terrain_build_events']=[{'kind':e.kind,'count':e.count,'seconds':e.when-_BOOT_STARTED} for e in events]
            if metrics:
                compose_seconds=time.monotonic()-phase_start[0]
                metrics.end('host_compose',phase_start)
                metrics.add('composed_cells',computed);metrics.add('changed_cells',changed)
                if computed:
                    metrics.add('compose_batches_'+host.render_backend)
                    metrics.add('scanned_cells_'+host.render_backend,computed)
                    if host.render_reason:metrics.add('fallback_'+host.render_reason)
                    metrics.add('frame_completions' if not host.damage else 'partial_frames')
                if first_frame:metrics.add('first_frame_seconds',time.monotonic()-metrics.started)
            first_frame=False
            if output:
                for p in panel.panels:
                    if p.presentation=='dock':p.cache=None
            panel_output=panel.render(widgets,{**{w.name:host.window_status(w) for w in windows},**radio_styles},
                {'launch:terminal:new':'>_','launch:window:Settings':'[i]',**{a.name:a.icon for a in workspace}})
            host.minimize_targets=panel.minimize_targets((w.name for w in windows),host.origin)
            output+=f'\x1b[{geometry.rows};1H\x1b[2K' if host.screensaver else panel_output
            if metrics:phase_start=metrics.begin()
            output=presentation.write(output,not host.damage,time.monotonic(),max_hold=.08,atomic=os.environ.get('TERM')=='linux' or camera_frame or host.effect=='terrain' and host.background_enabled,urgent=host.ui_painted)
            if output:
                sys.stdout.write(output)
                sys.stdout.flush()
                if not host.damage:
                    for form in host.app_forms.values():
                        if hasattr(form,'presented'):form.presented(time.monotonic())
                if metrics and not host.damage:
                    startup.setdefault('first_coherent_output_seconds',time.monotonic()-_BOOT_STARTED)
                    if not host.terrain_loading and host.terrain_arrival is None and host.terrain_renderer and host.terrain_renderer.completed:
                        if 'first_final_terrain_output_seconds' not in startup:
                            startup['first_final_terrain_output_seconds']=time.monotonic()-_BOOT_STARTED
                            if args.metrics:
                                try:args.metrics.with_suffix('.startup.json').write_text(json.dumps(startup,indent=2)+'\n')
                                except OSError:pass
                if not host.damage and host.terrain_arrival is not None and host.arrival_progress==0 and not host.arrival_presented:
                    # Time the reveal from its first completed presentation.
                    host.terrain_arrival=host.clock();host.arrival_presented=True
            if metrics:
                write_seconds=time.monotonic()-phase_start[0]
                debug_window=host.window('Render Debug')
                ignore=host.bounds(debug_window) if host.shown(debug_window) else None
                def scene_index(i):
                    if ignore is None:return True
                    x,y,w,h=ignore
                    return not (x<=i%host.width<x+w and y<=i//host.width<y+h)
                scene=any(scene_index(i) for i in host.composed_indices)
                host.composed_indices=() # Release batch indices before waiting for input.
                metrics.render.batch(scene,not host.damage,len(output.encode('utf-8')),compose_seconds,write_seconds,host.render_backend,host.render_reason,host.effect_frame_id if host.background_enabled else None)
                metrics.end('terminal_write',phase_start)
                metrics.add('output_bytes',len(output.encode('utf-8')))
                if output:metrics.add('terminal_write_calls')
                if output:metrics.add('output_frames');metrics.wrote()
            now=time.monotonic()
            if trial and trial.update(metrics.render,host,radio.source if radio else None):break
            metrics.model_call('session','save',store.save,now) if metrics else store.save(now)
            if receive_status:receive_status.update(now)
            owner_delays={}
            def owner_delay(owner,delay):
                if delay is not None:owner_delays[owner]=min(owner_delays.get(owner,delay),delay)
            owner_delay('sources',1. if native_catalog or system_state or demo_apps is not None or receive_status else None)
            timeout=0 if host.damage else .016 if host.animations or host.slide or host.camera_motion or host.edge or host.terrain_loading or host.terrain_arrival is not None else .04 if decoder.pending else .1 if host.background_enabled else None
            model_intervals=[] if metrics else None
            for index,application in enumerate(applications):
                interval=metrics.model_call('application-'+str(index),'interval',application.poll_interval) if metrics else application.poll_interval()
                if metrics and interval is not None and len(model_intervals)<64:model_intervals.append(dict(owner='application-'+str(index),seconds=interval))
                if interval is not None:
                    timeout=interval if timeout is None else min(timeout,interval)
                    owner_delay('application:'+str(index),interval)
            for name,form in host.app_forms.items():
                interval=(metrics.model_call(name,'interval',form.poll_interval) if metrics else form.poll_interval()) if hasattr(form,'poll_interval') else None
                if metrics and interval is not None and len(model_intervals)<64:model_intervals.append(dict(owner=name,seconds=interval,visible=host.shown(host.window(name))))
                if interval is not None:
                    timeout=interval if timeout is None else min(timeout,interval)
                    owner_delay('form:'+name,interval)
            if receive_status:timeout=1 if timeout is None else min(timeout,1)
            if radio and (radio.path or radio.source or radio.read_client):
                radio_delay=radio.delay()
                if radio_delay is not None:
                    timeout=radio_delay if timeout is None else min(timeout,radio_delay)
                    owner_delay('sources',radio_delay)
            for name,form in host.app_forms.items():
                if getattr(form,'_future',None) is not None:
                    timeout=.05 if timeout is None else min(timeout,.05);owner_delay('form:'+name,.05)
            if host.pointer_trail and host.pointer_trail.active:timeout=.033 if timeout is None else min(timeout,.033)
            if mirror_due is not None:
                delay=max(0,mirror_due-time.monotonic());timeout=delay if timeout is None else min(timeout,delay)
            if host.overview or app_gallery is not None and any(host.shown(w) for w in windows if w.name in app_gallery.NAMES):
                app_delay=max(.01,1-time.monotonic()%1)
                timeout=app_delay if timeout is None else min(timeout,app_delay)
                owner_delay('all',app_delay)
            if host.show_clock:
                clock_delay=clock_widget.delay(time.time())
                timeout=clock_delay if timeout is None else min(timeout,clock_delay)
                owner_delay('panel',clock_delay)
            for name,form in host.app_forms.items():
                if host.shown(host.window(name)) and (getattr(form,'spin',False) or getattr(form,'transition',None)):
                    timeout=.04 if timeout is None else min(timeout,.04);owner_delay('form:'+name,.04)
            if needs_completion_poll(getattr(host,'app_renderers',())):
                timeout=.025 if timeout is None else min(timeout,.025);owner_delay('all',.025)
            if any(t.eof and t.child.returncode is None for t in terminals.values()):
                timeout=.05 if timeout is None else min(timeout,.05);owner_delay('all',.05)
            delay=store.delay(now)
            if delay is not None:timeout=delay if timeout is None else min(timeout,delay)
            model_schedule.arm(owner_delays,now,serviced_owners)
            model_delay=model_schedule.delay(time.monotonic())
            if metrics:
                from draw_metrics import pending_model_renderers
                metrics.model_schedule=dict(model_delay=model_delay,selector_timeout=timeout,form_intervals=model_intervals,
                    pending_renderers=pending_model_renderers(host),renderer_count=len(getattr(host,'app_renderers',())),
                    form_count=len(host.app_forms),future_forms=[name for name,form in __import__('itertools').islice(host.app_forms.items(),64) if getattr(form,'_future',None) is not None])
            if model_delay is not None:timeout=model_delay if timeout is None else min(timeout,model_delay)
            if launcher.active:
                timeout=0 if host.launcher_damage(1,inside=False) else .04 if decoder.pending else .1
            elif model_deferred and not host.ui_damage:
                # Chrome has drained; run the deferred form update before the
                # event loop can sleep waiting for another unrelated input.
                timeout=0
            if metrics and iteration_start is not None:metrics.end('main_phase',iteration_start)
            # Check VT ownership even when no keys arrive after a VT switch.
            if keyboard is not None:timeout=.1 if timeout is None else min(timeout,.1)
            pointer_trace.sample(host)
            events = selector.select(timeout)
    finally:
        pointer_trace.sample(host);pointer_trace.close()
        if keyboard_router is not None:keyboard_router.close()
        if trial:
            try:trial.finish(sys.exc_info()[1],metrics.render if metrics else None)
            except OSError as error:print('Could not save trial receipt: '+str(error),file=sys.stderr)
        if touch is not None:
            cancel_touch();touch.close()
        if metrics:
            for t in terminals.values():t.exit_status=t.child.poll()
            metrics.add('apps_exited_before_desktop',sum(t.eof or t.exit_status is not None for t in terminals.values()))
        for terminal in terminals.values():terminal.close()
        host.finish(False)
        session_audit_ok=store.audit(time.monotonic())
        registered_report=registered_apps.snapshot()
        close_apps()
        if control is not None:control.close()
        if control_directory is not None:control_directory.cleanup()
        signal.signal(signal.SIGWINCH,previous_resize)
        for sig,handler in stop_handlers.items():signal.signal(sig,handler)
        try:termios.tcsetattr(sys.stdin,termios.TCSADRAIN,old)
        except (OSError,termios.error):pass
        try:sys.stdout.write(terminal_keys.close()+presentation.close()+'\x1b[?1003l\x1b[?1002l\x1b[?1006l\x1b[0m\x1b[?25h\x1b[?1049l'); sys.stdout.flush()
        except (OSError,BrokenPipeError):pass
        selector.close(); inbox.close()
        if host.terrain_renderer is not None:host.terrain_renderer.close()
        for renderer in getattr(host,'app_renderers',()):renderer.close()
        if store.error:print(store.error,file=sys.stderr)
        if not session_audit_ok:print('Desktop session audit found missed notifications: '+', '.join(store.missed_notifications),file=sys.stderr)
        scene_status=dict(selection=scene_selection,**scene_acceleration.status())
        if args.scene_report:
            try:args.scene_report.write_text(json.dumps(scene_status,indent=2)+'\n')
            except OSError as error:print('Could not save scene report: '+str(error),file=sys.stderr)
        if metrics:
            from draw_metrics import renderer_timings
            metrics.metadata={'renderer_timings':renderer_timings(host),'startup':startup,'effective_scene':__import__('draw_metrics').scene_state(host),'engine_identity':dict(build_identity.IDENTITY),'engine_root':str(Path(__file__).resolve().parent),'domain_root':str(Path(station_app.argv[1]).parent) if station_app else None,'scene_acceleration':scene_status,'session_loaded':store.loaded,'session_error':store.error,'session_audit_ok':session_audit_ok,'session_audit_missed':list(store.missed_notifications),'session_work':dict(store.stats),'scenery':host.scenery,'native_selection':native_selection,'native_requested':str(args.native) if args.native else None,'native_loaded':host._native is not None,'native_error':host.native_error,'last_backend':host.render_backend,'last_fallback_reason':host.render_reason,'native_buffer_bytes':host._native.bytes if host._native else 0,'mixed_python_cells':host._native.mixed_python_cells if host._native else 0,
                              'logical_geometry':[host.width,host.height],'terminal_geometry':[geometry.columns,geometry.rows],
                              'registered_apps':registered_report,'geometry_compute':__import__('geometry_compute').status() if host.effect=='terrain' or any(row['created'] for row in registered_report.values()) else None,'effect':host.effect,'static_world_age':host.static_world_age,'background_enabled':host.background_enabled,'background_schedule_hz':6 if host.background_enabled else None,
                              'numeric_backend':(host.flurry_provider.status()['backend'] if host.flurry_provider else 'python') if host.effect=='flurry' else 'not_measured','seed':host.scene_seed,'flurry_strands':host.flurry_strands,
                              'flurry_sway':host.flurry_sway,'flurry_speed':host.flurry_speed,
                              'flurry_compute':host.flurry_provider.status() if host.flurry_provider else {'backend':'python','reason':'not requested'}}
            try:
                if args.metrics:metrics.save(args.metrics,terminals.values())
            except OSError as error:print('Could not save draw metrics: '+str(error),file=sys.stderr)

if __name__ == '__main__': main()
