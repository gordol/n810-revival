"""Versioned desktop preferences; no application history or animation snapshots."""
from runtime_codec import pack,unpack
import os
import re
from pathlib import Path
import tempfile
from copy import deepcopy
import time
from panel import Panel,DOCKS
from effects import NAMES

RETIRED=frozenset(('Terrain Profile','Weather','Moon Lab','Notes','Activity','Diagnostics',
    'Messages (terminal)','Services (terminal)','Nets (terminal)',
    'APRS (terminal)','Directory (terminal)','Walk (terminal)'))

WINDOW_FIELDS=('x','y','w','h','desktop','visible','rolled','pinned','opened')
PREFS=('application_menu_mode','app_preferences','scenery','font_preview_id','show_underlying_text','timezone_name','list_scrollbars','list_counts','status_verbosity','pager_position','show_pager','resize_edges','desktop_scroll','wm_escape','mouse_trails','terminal_opacity','window_controls','terrain_grid','season','show_foliage','show_animals','show_flowers','show_lookout','arrival_duration','snap_windows','flux_performance','flux_arms','flux_density','flux_glow','window_opacity','flurry_sway','flurry_speed','flurry_strands','style','palette','animate','animation_duration','move_mode','resize_mode',
       'tinted','background_enabled','focused_button_minimizes','overview_opacity','scene_seed','nature_epoch','nature_rate','light_mode','moon_phase','parallax','overview_zoom','terrain_shadows','shadow_enabled','shadow_size','shadow_opacity','shadow_direction','show_clock','show_connectivity')


def default_path():
    return Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'current-world/session.msgpack'


def capture(host,panels):
    shells=set(getattr(host,'session_shells',()))
    names=(set(host.focus_order)-host.transient_windows)|shells
    overrides=getattr(host,'render_debug_preferences',{})
    windows={}
    for name in host.focus_order:
        if name in names:
            window=host.window(name)
            windows[name]={key:getattr(window,key) for key in WINDOW_FIELDS}
    return {'version':1,'shared_background':True,'panel_mode':panels.mode,'panels_locked':panels.locked,'desktop':host.desktop,'effects':[host.screensaver_effect]*3 if host.screensaver else list(host.desktop_effects),
            'preferences':{key:deepcopy(overrides.get(key,getattr(host,key))) for key in PREFS},
            'windows':windows,
            'app_views':{name:form.session_state() for name,form in getattr(host,'app_forms',{}).items() if hasattr(form,'session_state')},
            'stack':[w.name for w in host.windows if w.name in names],'focus':host.focus if host.focus in names else None,
            'panels':[{'dock':p.dock,'widgets':list(p.widgets)} for p in panels.panels],
            'maximized':{name:list(rect) for name,rect in host.maximized.items() if name in names},'shells':sorted(shells-{'Terminal'}),'selected_panel':panels.panels.index(panels.selected)}


WINDOW_ALIASES={'RNode Bluetooth':'RNode connections','Walk':'APRS Walk Logs'}


def renamed_windows(data,known):
    """Migrate explicit app-title changes without mutating the saved document."""
    aliases={old:new for old,new in WINDOW_ALIASES.items() if old in data.get('windows',{}) and new in known}
    if not aliases:return data
    def renamed(items):
        result={}
        for name,value in items.items():
            target=aliases.get(name,name)
            if target in result:raise ValueError('conflicting saved windows: '+target)
            result[target]=value
        return result
    return dict(data,windows=renamed(data['windows']),
        stack=[aliases.get(name,name) for name in data['stack']],
        focus=aliases.get(data['focus'],data['focus']),
        maximized=renamed(data.get('maximized',{})),app_views=renamed(data.get('app_views',{})))


def restore(data,host,panels,layout=True):
    from core import STYLES,PALETTES
    from panel import MODES
    data=renamed_windows(data,set(host.focus_order))
    views=data.get('app_views',{})
    if not isinstance(views,dict) or len(views)>32 or len(pack(views))>8192:raise ValueError('invalid app view preferences')
    if data.get('panel_mode','bar') not in MODES:raise ValueError('invalid panel presentation')
    if type(data.get('panels_locked',True)) is not bool:raise ValueError('invalid panel lock preference')
    # Validate the complete known schema before changing the running model.
    if data.get('version')!=1:raise ValueError('unsupported desktop session version')
    if type(data.get('shared_background',False)) is not bool:raise ValueError('invalid background ownership')
    if type(data['desktop']) is not int or not 0<=data['desktop']<3:raise ValueError('invalid desktop')
    if len(data['effects'])!=3 or any(e not in NAMES for e in data['effects']):raise ValueError('invalid effects')
    removed=(set(data['windows'])&RETIRED)-set(host.focus_order)
    if removed:
        data=dict(data,windows={k:v for k,v in data['windows'].items() if k not in removed},
                  stack=[k for k in data['stack'] if k not in removed],
                  focus=None if data['focus'] in removed else data['focus'],
                  maximized={k:v for k,v in data.get('maximized',{}).items() if k not in removed},
                  app_views={k:v for k,v in data.get('app_views',{}).items() if k not in removed})
    prefs=dict(data['preferences'])
    from app_registry import validate_app_preferences
    prefs['app_preferences']=validate_app_preferences(prefs.get('app_preferences',{}))
    prefs.setdefault('font_preview_id','console-8x16')
    if not isinstance(prefs['font_preview_id'],str) or not re.fullmatch(r'[a-z0-9-]{1,64}',prefs['font_preview_id']):raise ValueError('invalid font preview ID')
    from input import WM_ESCAPES
    for key in ('show_pager','resize_edges','desktop_scroll'):prefs.setdefault(key,getattr(host,key))
    from launcher import MENU_MODES
    prefs.setdefault('application_menu_mode','Alphabetical')
    if prefs['application_menu_mode'] not in MENU_MODES:raise ValueError('invalid application menu mode')
    prefs.setdefault('wm_escape','ctrl-]')
    if prefs['wm_escape'] not in WM_ESCAPES:raise ValueError('invalid WM escape')
    prefs.setdefault('mouse_trails',False)
    prefs.setdefault('terminal_opacity',1.)
    prefs.setdefault('window_controls','auto')
    if prefs['window_controls'] not in ('auto','left','right'):raise ValueError('invalid window controls')
    prefs.pop('window_fill',None)  # Remove the temporary unfilled-window review preference.
    prefs.setdefault('arrival_duration',2.0)
    # Retune the previous shipped default; retain other chosen durations.
    if prefs['arrival_duration'] in (1.2,2.5,8.0,3.2):prefs['arrival_duration']=2.0
    prefs.setdefault('snap_windows',True)
    prefs.setdefault('flux_performance','balanced')
    if prefs['flux_performance'] not in ('balanced','fast demo'):raise ValueError('invalid Flux performance mode')
    prefs.setdefault('flux_arms',2)
    if type(prefs['flux_arms']) is not int or not 0<=prefs['flux_arms']<=4:raise ValueError('invalid flux arms')
    prefs.setdefault('flux_density',1.0)
    prefs.setdefault('flux_glow',.15)
    prefs.setdefault('window_opacity',.88)
    prefs.setdefault('show_underlying_text',False)
    prefs.setdefault('flurry_strands',48)
    prefs.setdefault('flurry_sway',.6)
    prefs.setdefault('flurry_speed',1.0)
    if type(prefs['flurry_strands']) is not int or not 8<=prefs['flurry_strands']<=192:raise ValueError('invalid flurry strands')
    prefs.setdefault('overview_opacity',.65)
    prefs.setdefault('light_mode','dynamic')
    prefs.setdefault('season','auto')
    prefs.setdefault('terrain_grid',.08)
    from scenery import Config,validate as validate_scenery
    prefs.setdefault('scenery',Config()._asdict())
    validate_scenery(prefs['scenery'])
    for key in ('show_foliage','show_animals','show_flowers'):prefs.setdefault(key,True)
    prefs['show_lookout']=False
    if prefs['season'] not in ('auto','spring','summer','autumn','winter'):raise ValueError('invalid season')
    prefs.setdefault('moon_phase','auto')
    for key in ('parallax','overview_zoom','terrain_shadows','shadow_enabled','shadow_size','shadow_opacity','shadow_direction'):prefs.setdefault(key,getattr(host,key))
    for key in ('scene_seed','nature_epoch','nature_rate','light_mode','moon_phase','parallax','overview_zoom','terrain_shadows','shadow_enabled','shadow_size','shadow_opacity','shadow_direction','show_clock','show_connectivity'):prefs.setdefault(key,getattr(host,key))
    prefs.setdefault('timezone_name','UTC')
    from time_display import validate_zone
    validate_zone(prefs['timezone_name'])
    for key in ('list_scrollbars','list_counts','status_verbosity'):prefs.setdefault(key,getattr(host,key))
    if prefs['list_scrollbars'] not in ('auto','on','off') or prefs['list_counts'] not in ('auto','on','off') or prefs['status_verbosity'] not in ('compact','detailed'):raise ValueError('invalid app presentation')
    prefs.setdefault('pager_position',host.pager_position)
    if prefs['pager_position'] not in ('bottom left','bottom right','top left','top right'):raise ValueError('invalid pager position')
    if set(prefs)!=set(PREFS):raise ValueError('invalid preferences')
    if prefs['style'] not in STYLES or prefs['palette'] not in PALETTES:raise ValueError('invalid appearance')
    for key in ('move_mode','resize_mode'):
        if prefs[key] not in ('outline','live'):raise ValueError('invalid drawing mode')
    if type(prefs['animation_duration']) not in (float,int) or not .04<=prefs['animation_duration']<=.32:raise ValueError('invalid animation duration')
    if type(prefs['overview_opacity']) not in (float,int) or not 0<=prefs['overview_opacity']<=1:raise ValueError('invalid overview opacity')
    if type(prefs['scene_seed']) is not int or not 0<=prefs['scene_seed']<2**32:raise ValueError('invalid scene seed')
    if type(prefs['nature_epoch']) not in (float,int) or not 0<=prefs['nature_epoch']<1e12:raise ValueError('invalid nature epoch')
    from scenery import PHASES
    if prefs['moon_phase'] not in PHASES:raise ValueError('invalid moon phase')
    if prefs['light_mode'] not in ('dynamic','day','night'):raise ValueError('invalid light mode')
    if prefs['nature_rate'] not in (1,10,30,60):raise ValueError('invalid nature speed')
    for key in ('show_underlying_text','show_pager','resize_edges','desktop_scroll','mouse_trails','show_foliage','show_animals','show_flowers','show_lookout','snap_windows','animate','tinted','background_enabled','focused_button_minimizes','show_clock','show_connectivity'):
        if type(prefs[key]) is not bool:raise ValueError('invalid toggle')
    for key,low,high in (('terminal_opacity',0,1),('terrain_grid',0,.35),('arrival_duration',.25,12),('flux_density',.5,4),('flux_glow',0,1),('window_opacity',0,1),('flurry_sway',0,1),('flurry_speed',.25,2),('parallax',0,.03),('overview_zoom',1,2.5),('shadow_size',1,4),('shadow_opacity',0,.85)):
        if type(prefs[key]) not in (int,float) or not low<=prefs[key]<=high:raise ValueError('invalid scene control')
    if prefs['shadow_direction'] not in ('SE','S','SW','W','NW','N','NE','E'):raise ValueError('invalid shadow direction')
    if type(prefs['shadow_enabled']) is not bool or type(prefs['terrain_shadows']) is not bool:raise ValueError('invalid shadow toggle')
    shells=data.get('shells',[])
    if not isinstance(shells,list) or len(shells)>12 or len(set(shells))!=len(shells) or any(not isinstance(name,str) or re.fullmatch(r'Terminal [2-9]|Terminal [1-9][0-9]{1,2}',name) is None for name in shells):raise ValueError('invalid shell slots')
    known=set(host.focus_order)|set(shells)
    saved=set(data['windows'])
    if saved-known:raise ValueError('saved applications unavailable: '+', '.join(sorted(saved-known)))
    if not set(shells)<=saved or set(data['stack'])!=saved or len(data['stack'])!=len(saved):raise ValueError('window contracts changed')
    if data['focus'] is not None and data['focus'] not in known:raise ValueError('invalid focus')
    for row in data['windows'].values():
        if set(row)!=set(WINDOW_FIELDS):raise ValueError('invalid window fields')
        for key in ('x','y','w','h','desktop'):
            if type(row[key]) is not int or not 0<=row[key]<=100000:raise ValueError('invalid geometry')
        if row['w']<12 or row['h']<4 or row['desktop']>=3:raise ValueError('invalid window bounds')
        for key in ('visible','rolled','pinned','opened'):
            if type(row[key]) is not bool:raise ValueError('invalid window state')
    maximized=data.get('maximized',{})
    if not isinstance(maximized,dict) or not set(maximized)<=saved or any(not isinstance(rect,list) or len(rect)!=4 or any(type(v) is not int or not 0<=v<=100000 for v in rect) or rect[2]<12 or rect[3]<4 for rect in maximized.values()):raise ValueError('invalid maximized windows')
    rows=data['panels']
    if not 1<=len(rows)<=4 or len({p['dock'] for p in rows})!=len(rows):raise ValueError('invalid panel count/docks')
    widgets=[]
    for row in rows:
        if row['dock'] not in DOCKS or not isinstance(row['widgets'],list):raise ValueError('invalid panel')
        widgets+=row['widgets']
    required={'desktops','windows','appearance','weather'}
    if len(widgets)!=len(set(widgets)) or not required<=set(widgets) or not set(widgets)<=required|{'clock','connectivity','spacer','apps'}:raise ValueError('invalid widget ownership')
    if type(data['selected_panel']) is not int or not 0<=data['selected_panel']<len(rows):raise ValueError('invalid selected panel')
    for key,value in prefs.items():setattr(host,key,value)
    panels.set_mode(data.get('panel_mode','bar'))
    panels.set_locked(data.get('panels_locked',True))
    if not layout:
        effect=data['effects'][data['desktop']]
        host.desktop_effects=[effect]*3
        host.repair_focus()
        return
    from core import Window
    for name in shells:
        if name not in host.focus_order:host.add_window(Window(name,0,0,12,4),transient=True)
    if hasattr(host,'session_shells'):host.session_shells={'Terminal',*shells}
    for name,row in data['windows'].items():
        for key,value in row.items():setattr(host.window(name),key,value)
    host.windows=[host.window(name) for name in data['stack']+list(name for name in host.focus_order if name not in saved)]
    host.maximized={name:tuple(rect) for name,rect in maximized.items()}
    effect=data['effects'][data['desktop']]
    if not data.get('shared_background',False):
        if effect=='pnw' or any(e in ('pnw','terrain') for e in data['effects']) or data['effects']==['matrix','snow','leaves']:effect='terrain'
    host.desktop=data['desktop'];host.desktop_effects=[effect]*3;host.focus=data['focus']
    host.app_view_state=views
    panels.panels=[]
    for row in rows:
        p=Panel(row['dock']);p.widgets=list(row['widgets']);panels.panels.append(p)
    for name in ('clock','connectivity'):
        if name not in widgets:panels.panels[0].widgets.insert(1,name)
    if 'spacer' not in widgets:
        owner=next(p for p in panels.panels if 'clock' in p.widgets)
        owner.widgets.remove('clock');owner.widgets.extend(('spacer','clock'))
    panels.selected=panels.panels[data['selected_panel']]
    host.repair_focus()


class Store:
    def __init__(self,path,enabled=True,remember_layout=True):
        self.path=Path(path)
        if self.path.suffix=='.json':self.path=self.path.with_suffix('.msgpack')
        self.enabled=enabled;self.error=None;self.loaded=False
        self.remember_layout=remember_layout;self.layout_defaults=None
        self.current=None;self.saved=None;self.deadline=None
        self.host=None;self.panels=None;self.dirty=set();self.missed_notifications=[]
        self.stats=dict(seed_captures=0,default_captures=0,audit_captures=0,
                        collect_batches=0,app_serializations=0,writes=0,notifications=0)

    def bind(self,host,panels,now=None):
        """Seed once, then accept explicit owner changes rather than render ticks."""
        host.session_stats=self.stats
        host.session_error=self.error
        if not self.enabled:return
        self.host,self.panels=host,panels
        self.stats['seed_captures']+=1
        self.observe(capture(host,panels),time.monotonic() if now is None else now)
        host.session_callback=self.changed
        panels.bind_session(lambda:self.changed('panels'))
        for name,form in getattr(host,'app_forms',{}).items():self.bind_app(name,form)

    def bind_app(self,name,form):
        if not self.enabled or not hasattr(form,'session_state'):return
        if not callable(getattr(form,'bind_session',None)):
            raise TypeError('Persisted app requires change notifications: '+name)
        form.bind_session(lambda:self.changed('app',name))

    def changed(self,scope,key=None):
        if not self.enabled or self.host is None:return
        if scope not in ('window','preference','desktop','structure','panels','app'):
            raise ValueError('Unknown session change scope: '+str(scope))
        self.dirty.add((scope,key))
        self.stats['notifications']+=1
        # Repeated/no-op notifications cannot postpone a pending real save.
        if self.deadline is None:self.deadline=time.monotonic()+.35

    def _section(self,state,scope,key):
        host,panels=self.host,self.panels
        if scope=='preference':
            if key not in PREFS:raise ValueError('Unknown saved preference: '+str(key))
            prefs=dict(state['preferences'])
            prefs[key]=deepcopy(getattr(host,'render_debug_preferences',{}).get(key,getattr(host,key)))
            state['preferences']=prefs
        elif scope=='app':
            views=dict(state['app_views']);form=host.app_forms.get(key)
            if form is None or not hasattr(form,'session_state'):views.pop(key,None)
            else:
                self.stats['app_serializations']+=1
                views[key]=deepcopy(form.session_state())
            state['app_views']=views
        elif scope in ('window','structure'):
            shells=set(getattr(host,'session_shells',()))
            names=(set(host.focus_order)-host.transient_windows)|shells
            windows=dict(state['windows']) if scope=='window' else {}
            for name in ((key,) if scope=='window' else host.focus_order):
                if name in names:
                    window=host.window(name)
                    windows[name]={field:getattr(window,field) for field in WINDOW_FIELDS}
                else:windows.pop(name,None)
            state['windows']=windows
            state['shells']=sorted(shells-{'Terminal'})
            self._section(state,'desktop',None)
        elif scope=='desktop':
            names=(set(host.focus_order)-host.transient_windows)|set(getattr(host,'session_shells',()))
            state.update(desktop=host.desktop,
                         effects=[host.screensaver_effect]*3 if host.screensaver else list(host.desktop_effects),
                         stack=[w.name for w in host.windows if w.name in names],
                         focus=host.focus if host.focus in names else None,
                         maximized={name:list(rect) for name,rect in host.maximized.items() if name in names})
        elif scope=='panels':
            state.update(panel_mode=panels.mode,panels_locked=panels.locked,
                         panels=[{'dock':p.dock,'widgets':list(p.widgets)} for p in panels.panels],
                         selected_panel=panels.panels.index(panels.selected))

    def collect(self,now,force=False):
        if not self.enabled or not self.dirty:return True
        if not force and (self.deadline is None or now<self.deadline):return False
        batch=self.dirty;self.dirty=set()
        self.stats['collect_batches']+=1
        state=dict(self.current)
        try:
            for scope,key in batch:self._section(state,scope,key)
            if not self.remember_layout and self.layout_defaults:
                for key in ('desktop','windows','stack','focus','panels','selected_panel','maximized','shells'):
                    state[key]=self.layout_defaults[key]
        except Exception as error:
            self.dirty.update(batch);self.deadline=now+.35
            self.error='Cannot collect desktop: '+str(error)
            return False
        self.current=state
        self.deadline=now if state!=self.saved else (now+.35 if self.dirty else None)
        return True

    def audit(self,now):
        """One exit consistency check, before owners are disposed. Never idle work."""
        if not self.enabled or self.host is None:return True
        for _ in range(64):
            if not self.collect(now,force=True):return False
            if not self.dirty:break
        else:
            self.error='Desktop exit collection did not quiesce'
            return False
        self.stats['audit_captures']+=1
        final=deepcopy(capture(self.host,self.panels))
        if not self.remember_layout and self.layout_defaults:
            for key in ('desktop','windows','stack','focus','panels','selected_panel','maximized','shells'):
                final[key]=self.layout_defaults[key]
        missed=[key for key in final if final[key]!=self.current.get(key)]
        self.missed_notifications.extend(missed)
        if missed:self.observe(final,now)
        self.save(now,force=True)
        return not missed

    def load(self,host,panels):
        self.stats['default_captures']+=1
        self.layout_defaults=capture(host,panels)
        try:
            source=self.path
            if not source.exists() and source.suffix=='.msgpack':source=source.with_suffix('.json')
            if source.stat().st_size>65536:raise ValueError('desktop file too large')
            raw=source.read_bytes()
            if raw.lstrip().startswith(b'{'):
                from legacy_state import decode
                data=decode(raw)
            else:data=unpack(raw,65536)
            restore(data,host,panels,layout=self.remember_layout)
            self.loaded=True
        except FileNotFoundError:return
        except (OSError,ValueError,TypeError,KeyError,AttributeError) as error:
            self.error=f'Cannot load desktop: {error}; original file preserved'
            self.enabled=False

    def observe(self,state,now):
        if not self.enabled:return
        if not self.remember_layout and self.layout_defaults:
            state=dict(state)
            for key in ('desktop','windows','stack','focus','panels','selected_panel','maximized','shells'):
                state[key]=self.layout_defaults[key]
        if state!=self.current:
            self.current=deepcopy(state)
            self.deadline=now+.35 if state!=self.saved else None

    def save(self,now,force=False):
        if not self.enabled:return
        if not self.collect(now,force):return
        if not force and (self.deadline is None or now<self.deadline):return
        if self.current is None or self.current==self.saved:return
        temporary=None
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            fd,temporary=tempfile.mkstemp(prefix='.desktop-',dir=self.path.parent)
            with os.fdopen(fd,'wb') as stream:
                stream.write(pack(self.current));stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,self.path)
            self.stats['writes']+=1
            self.saved=self.current;self.deadline=now+.35 if self.dirty else None
        except OSError as error:
            self.error=f'Cannot save desktop: {error}';self.enabled=False
        finally:
            if temporary and os.path.exists(temporary):os.unlink(temporary)

    def delay(self,now):
        return max(0,self.deadline-now) if self.enabled and self.deadline is not None else None
