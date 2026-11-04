"""Small current-state runtime and retained cell compositor. Standard library only."""
from collections import namedtuple
from functools import lru_cache
from cell_text import RICH, Glyphs
import json
import _socket as socket
import time
import math
from paint import FRAME_DEFERRED, chrome_ink, frame_template, frame_ink, foreground, background as paint_background, Scene, shade_ink, pane_ink, window_text_ink, window_pane_ink, control_ink, ink, inherit_background, terminal_background
from weather import Weather, PRESETS, Surfaces, wind_field
from effects import NAMES as EFFECTS, frame as effect_frame, matrix_plan

STYLES = {
    'thin': ('┌','┐','└','┘','─','│'),
    'rounded': ('╭','╮','╰','╯','─','│'),
    'double': ('╔','╗','╚','╝','═','║'),
    'bare': (' ',' ',' ',' ',' ',' '),
}
PALETTES = {
    'ice': ('37','96','38;2;128;153;159','93'),
    'amber': ('37','93','38;2;163;143;111','97'),
    'paper': ('37','97','90','36'),
    'violet': ('37','95','38;2;155;135;175','96'),
    'rose': ('37','91','38;2;166;135;151','93'),
    'ocean': ('37','94','38;2;125;150;175','92'),
}
FLUX_MAX_FPS=30
FLUX_CPU_SHARE=.5
FLUX_FAST_CPU_SHARE=.65

Record = namedtuple('Record', 'id operator medium text')
Cell = namedtuple('Cell', 'char color')


@lru_cache(maxsize=4096)
def surface_cell(char,color):
    # Retained RGB surfaces are independent of app glyphs and reused across cells.
    return Cell(char,color)

Particle = namedtuple('Particle', 'x y born desktop glyph')
Wake = namedtuple('Wake', 'name rect dx dy born desktop')
BLANK = Cell(' ', 0)
DESKTOP_BLANK=Cell(' ',13)


@lru_cache(maxsize=128)
def window_chrome(name,width,style,ascii,rolled,pinned,maximized,side='right'):
    tl,tr,_,_,horizontal,_=('+','+','+','+','-','|') if ascii else STYLES[style]
    labels=(('roll','v' if rolled else '^'),('pin','*' if pinned else 'p'),('minimize','-' if ascii else '−'),('maximize','=' if maximized else '+'),('close','x'))
    if width>=19:labels=tuple((action,'['+label+']') for action,label in labels)
    if width<9:labels=labels[-min(2,max(0,width-3)):]
    if side=='left':
        order={'close':0,'minimize':1,'maximize':2,'pin':3,'roll':4}
        labels=tuple(sorted(labels,key=lambda item:order[item[0]]))
        head=tl+' '+''.join(label for _,label in labels)+' '
        title=(head+name+' ')[:width-1].ljust(width-1,horizontal)+tr
        controls=[];x=2
        for action,label in labels:controls.append((action,x,min(width,x+len(label))));x+=len(label)
        return title,tuple(controls)
    tail=''.join(label for _,label in labels)+' '+tr;prefix=max(0,width-len(tail))
    title=((tl+' '+name+' ')[:prefix].ljust(prefix,horizontal)+tail)[:width]
    controls=[];x=prefix
    for action,label in labels:controls.append((action,x,min(width,x+len(label))));x+=len(label)
    return title,tuple(controls)


class Handle:
    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def __getitem__(self, index):
        return self.value[index]

    def __getattr__(self, name):
        return getattr(self.value, name)


def compile_model(text):
    spec = json.loads(text)
    if set(spec) != {'model', 'provider', 'views'}:
        raise ValueError('declaration requires model, provider, views')
    if spec['model'] != list(Record._fields):
        raise ValueError('model fields must match provider record contract')
    if spec['provider'] != 'OperatorFeed@1':
        raise ValueError('unknown provider; expected OperatorFeed@1')
    plans = []
    names = set()
    for v in spec['views']:
        if set(v) != {'name', 'fields', 'limit', 'filter'} or v['name'] in names:
            raise ValueError('view requires unique name, fields, limit, filter')
        names.add(v['name'])
        if not isinstance(v['limit'], int) or not 1 <= v['limit'] <= 128:
            raise ValueError(v['name'] + ': limit must be 1..128')
        try:
            fields = tuple(Record._fields.index(f) for f in v['fields'])
            predicate = tuple((Record._fields.index(k), value) for k, value in v['filter'].items())
        except ValueError as e:
            raise ValueError(v['name'] + ': unknown field') from e
        plans.append((v['name'], fields, v['limit'], predicate))
    return tuple(plans)


class World:
    """Scheduler thread owns mutation; views retain references to current records."""
    def __init__(self, plans, capacity=128):
        self.records = {}
        self.capacity = capacity
        self.plans = plans
        self.rows = {p[0]: () for p in plans}
        self.dirty = set(self.rows)
        self.recomputed = dict.fromkeys(self.rows, 0)
        self.revision = 0

    def apply(self, batch):
        if len(batch) > 32:
            raise ValueError('batch exceeds 32 records')
        for record in batch:
            handle = self.records.get(record.id)
            old = handle.value if handle else None
            if old == record:
                continue
            if old is None and len(self.records) >= self.capacity:
                raise ValueError('current-state capacity exceeded')
            if handle is None:
                self.records[record.id] = Handle(record)
            else:
                handle.value = record
            changed = {i for i in range(len(record)) if old is None or old[i] != record[i]}
            for name, fields, limit, predicate in self.plans:
                matches = lambda r: r is not None and all(r[i] == value for i, value in predicate)
                if (matches(old) or matches(record)) and changed.intersection((*fields, *(i for i, _ in predicate))):
                    self.dirty.add(name)
            self.revision += 1

    def read(self, name):
        if name in self.dirty:
            _, fields, limit, predicate = next(p for p in self.plans if p[0] == name)
            self.rows[name] = tuple(r for r in self.records.values()
                                    if all(r[i] == value for i, value in predicate))[-limit:]
            self.dirty.remove(name)
            self.recomputed[name] += 1
        return self.rows[name]


class Inbox:
    """Bounded blocking adapter submissions; completion wakes the event loop."""
    def __init__(self, capacity=4, notification_capacity=256):
        from threading import Lock
        self._notification_lock = Lock()
        self._notifications = set()
        self._notification_overflow = False
        self.notification_capacity = max(1, notification_capacity)
        self._closed = False
        self.readable, self.writable = socket.socketpair()
        self.readable.setblocking(False)
        self.writable.setblocking(False)
        self.results = None
        self.pool = None
        self.pending = 0
        self.capacity = capacity

    def _wake(self):
        try:
            self.writable.send(b'x')
        except OSError:
            pass  # Full socket is already readable; closed socket is shutdown.

    def notify(self, key):
        """Post bounded readiness from workers; repeated owner keys coalesce.

        Uses a lock: Python signal handlers must use writable.send directly.
        """
        with self._notification_lock:
            if self._closed:
                return False
            wake = not self._notifications and not self._notification_overflow
            if len(self._notifications) < self.notification_capacity:
                self._notifications.add(key)
            elif key not in self._notifications:
                self._notification_overflow = True
            if wake:
                self._wake()
        return True

    def drain_notifications(self):
        """Main thread takes owner readiness after drain() clears socket bytes."""
        with self._notification_lock:
            keys = ('all',) if self._notification_overflow else tuple(self._notifications)
            self._notifications.clear()
            self._notification_overflow = False
        return keys

    def submit(self, fn):
        if self._closed or self.pending >= self.capacity:
            return False
        if self.pool is None:
            import queue
            from concurrent.futures import ThreadPoolExecutor
            self.results=queue.Queue(self.capacity);self.pool=ThreadPoolExecutor(max_workers=1)
        self.pending += 1
        future = self.pool.submit(fn)
        def done(f):
            try:
                result = (True, f.result())
            except Exception as e:
                result = (False, e)
            self.results.put_nowait(result)
            self._wake()
        future.add_done_callback(done)
        return True

    def drain(self):
        raw_wake = False
        try:
            while chunk := self.readable.recv(1024):
                raw_wake = raw_wake or any(byte != ord('x') for byte in chunk)
        except BlockingIOError:
            pass
        if raw_wake:
            with self._notification_lock:
                if len(self._notifications) < self.notification_capacity:
                    self._notifications.add('all')
                else:
                    self._notification_overflow = True
        results = []
        while self.results is not None and not self.results.empty():
            results.append(self.results.get_nowait())
            self.pending -= 1
        return results

    def close(self):
        with self._notification_lock:
            self._closed = True
            self._notifications.clear()
            self._notification_overflow = False
        if self.pool is not None:self.pool.shutdown(wait=True, cancel_futures=True)
        self.readable.close()
        self.writable.close()


def _prepare_effect(width,height,ascii,name,step,weather,seed,age,strands,sway,speed,density,glow,arms,provider):
    result=effect_frame(name,width,height,step,ascii,weather,seed,age,strands,sway,speed,density,glow,arms,provider)
    return result if isinstance(result,Scene) else Scene(result,{})


class Window:
    __slots__=('name','x','y','w','h','visible','lines','version','builds','rolled','pinned','desktop','opened','layer','spans','styles','_opaque_cache','_opaque_plane_cache')
    def __init__(self,name,x,y,w,h,visible=True,lines=(),version=None,builds=0,rolled=False,pinned=False,desktop=0,opened=True,layer=None,spans=(),styles=None):
        self.name,self.x,self.y,self.w,self.h=name,x,y,w,h
        self.visible,self.lines,self.version,self.builds=visible,lines,version,builds
        self.rolled,self.pinned,self.desktop,self.opened=rolled,pinned,desktop,opened
        self.layer,self.spans,self.styles=layer,spans,{} if styles is None else styles
        self._opaque_cache=None;self._opaque_plane_cache=None
    def __eq__(self,other):
        if self is other:return True
        if not isinstance(other,Window):return NotImplemented
        return all(getattr(self,k)==getattr(other,k) for k in self.__slots__ if k not in ('_opaque_cache','_opaque_plane_cache'))

    @property
    def rect(self):
        return self.x, self.y, self.w, 1 if self.rolled else self.h


class Host:
    def __init__(self, width, height, windows, ascii=False, animate=False, move_mode="outline", resize_mode="outline", clock=time.monotonic, wall_clock=time.time, background_async=False):
        self.full_window_apps=set()
        self.terrain_renderer = None
        self.terrain_loading=False
        self._loading_frame=None;self._loading_frame_key=None;self._loading_wire=None;self._loading_patch=set();self._loading_draw=None
        self._frame_windows=None
        self.loading_step=-1
        self.build_snapshot=()
        self.build_wire=None
        self.build_wire_started=0
        self.build_wire_progress=0
        self.arrival_duration=2.0
        self.arrival_plan=None
        self.screensaver=False
        self.flux_performance='balanced'
        self.flux_arms=2
        self.flux_density=1.0
        self.flux_glow=.15
        self.flurry_provider=None
        self.flurry_strands=48
        self.flurry_sway=.6
        self.flurry_speed=1.0
        self.screensaver_effect='terrain'
        self.width, self.height = width, height
        if move_mode not in ('outline', 'live') or resize_mode not in ('outline', 'live'):
            raise ValueError('drag mode must be outline or live')
        self.animate = animate
        self.move_mode, self.resize_mode = move_mode, resize_mode
        self.clock = clock
        self.effect_epoch = clock()
        self.wall_clock=wall_clock
        self.show_clock=True
        self.show_connectivity=True
        self.scene_seed=0
        self.nature_epoch=wall_clock()
        self.nature_rate=1.0
        self.static_world_age=None
        self.light_mode='dynamic'
        self.season='auto'
        self.terrain_grid=.08
        from scenery import Config
        self.scenery=Config()._asdict()
        self.app_preferences={}
        self.show_foliage=True
        self.show_animals=True
        self.show_flowers=True
        self.show_lookout=False
        self.moon_phase='auto'
        self.parallax=.005
        self.overview_zoom=1.65
        self.terrain_shadows=True
        self.shadow_enabled=True
        self.shadow_size=1
        self.shadow_opacity=.4
        self.shadow_direction='SE'
        self.terrain_arrival=None
        self.arrival_progress=0.0
        self.arrival_presented=False
        self.animations = {}
        self.visual = {}
        self.minimize_targets = {}
        self.ascii = ascii
        self.glyphs = RICH
        self.pointer_origin = None
        self.desktop = 0
        self.desktop_count = 3
        self.desktop_focus = {}
        self.windows = list(windows)
        self._windows_by_name={w.name:w for w in self.windows}
        self.focused_button_minimizes = False
        self.focus = next((w.name for w in reversed(windows) if w.visible and w.opened and (w.pinned or w.desktop==self.desktop)),None)
        self._native=None
        self.native_error=None
        self.render_backend='idle';self.render_reason=None
        self.front = [None] * (width * height)
        self.damage = set(range(width * height))
        self.ui_damage=set();self._background_invalidating=False
        self.ui_painted=False
        self.drag = None
        self.latest = None
        self.composed = 0
        self.opaque_rows_built=0
        self.origin = (0,0)
        self.tinted = True
        self.palette = 'ice'
        self.style = 'rounded'
        self.window_controls='auto'
        self.backdrop = {}
        self.scene_bases = {}
        self.background_enabled = False
        self.background_async=background_async;self._effect_scene=None
        self.observe_composition=False
        self.compose_phases={}
        self.effect_generation=0
        self.effect_frame_id=None
        self._flux_period=1/FLUX_MAX_FPS;self._flux_due=0.;self._flux_started=0.
        self._flux_generation_cpu=0.;self._flux_paint_cpu=0.;self._flux_budget_frame=None
        self._flux_external_budget=False
        self.background_step = -1
        self.particles = []
        self.wakes = []
        self.leaf_piles = {}
        self.loose_leaves = []
        self.weather = PRESETS[1]
        self.surfaces = Surfaces()
        self.desktop_effects = ['matrix']*3
        self.overview_opacity = .65
        self.window_opacity = .88
        self.show_underlying_text = False
        self.font_preview_id = 'console-8x16'
        self.terminal_opacity=1.
        self.terminal_layers=set()
        self.minimum_sizes={}
        self.reserved_bottom=0
        self.resize_edges=True;self.desktop_scroll=True;self.resize_anchor=(False,True,True)
        self.show_pager=False;self.pager=None;self.pager_position='bottom left'
        self.mouse_trails=False;self.pointer_trail=None
        self.application_menu_mode='Alphabetical'
        self.wm_escape='ctrl-]'
        self.timezone_name='UTC'
        self.list_scrollbars='auto';self.list_counts='auto';self.status_verbosity='compact'
        self.cell=self._cell
        self.window_fill=True
        self.snap_windows = True
        self._overview_rendering=False
        self.overview = False
        self.overview_selection=None
        self.maximized={}
        self.window_cleanup={}
        self.close_errors={}
        self.overview_drag = None
        self.overview_target = None
        self.overview_grab = None
        self.overview_preview = None
        self.slide = None
        self.camera_motion = None
        self.focus_order = tuple(w.name for w in windows)
        self.transient_windows=set()
        self.edge = None
        self.edge_armed = True
        self.help_lines = ()
        self.launcher_lines = ()
        self._launcher_dirty=set()
        self._launcher_presented_bounds=None
        self.launcher_anchor = None
        self.settings_lines = ()
        self.animation_duration = .16
        self.help_page = 0

    def enable_native(self,path):
        """Optional native opaque-text path; a missing library keeps portable rendering."""
        if self._native is not None and self.front is self._native.front:
            self.front=list(self.front)
        try:
            from native_cells import Compositor
            self._native=Compositor(path,Cell);self.native_error=None
            if hasattr(self._native.lib,'damage_new'):
                from native_scene import Damage
                self.damage=Damage(self._native.lib,self.width*self.height,self.damage)
                self.ui_damage=Damage(self._native.lib,self.width*self.height,self.ui_damage)
            return True
        except (ImportError,OSError,ValueError,AttributeError) as error:
            self.native_error=str(error);self._native=None
            return False

    def _ansi_colors(self):
        return PALETTES[self.palette]+('38;5;22','38;5;240','32','38;5;132','38;5;136','38;5;24','38;5;109','38;5;244','38;5;29','37','38;5;238','38;5;240','37')

    def nature_age(self):
        if self.static_world_age is not None:return self.static_world_age
        return max(0,self.wall_clock()-self.nature_epoch)*self.nature_rate

    def set_nature_rate(self,rate):
        if rate not in (1,10,30,60):raise ValueError('invalid nature rate')
        age=self.nature_age()
        self.set_preference('nature_epoch',self.wall_clock()-age/rate)
        self.set_preference('nature_rate',rate)
        self.background_step=-1

    def set_weather(self, observation):
        if not isinstance(observation,Weather) or not all(math.isfinite(v) for v in (observation.wind_x,observation.wind_y,observation.temperature)):
            raise ValueError('invalid weather observation')
        if observation.precipitation not in ('none','rain','snow') or not 0<=observation.intensity<=1 or not 0<=observation.cloud<=1:
            raise ValueError('invalid precipitation/cloud observation')
        self.weather=observation
        self.background_step=-1

    def stir(self, name, old, new):
        dx,dy = new[0]-old[0],new[1]-old[1]
        if not (dx or dy): return
        now = self.clock()
        # One recent impulse per window, at most eight retained wakes.
        self.wakes = [w for w in self.wakes if w.name != name and now-w.born < 1.5][-7:]
        self.wakes.append(Wake(name,old,max(-6,min(6,dx)),max(-3,min(3,dy)),now,self.desktop))

    def breeze(self, cells):
        now = self.clock()
        self.wakes = [w for w in self.wakes if now-w.born < 1.5]
        if self.effect not in ('rain','snow','leaves','flowers','matrix'): return cells
        output = {}
        for (x,y),cell in cells.items():
            dx=dy=0.0
            for wake in self.wakes:
                if wake.desktop != self.desktop: continue
                age = now-wake.born
                # Delayed response followed by decay provides a soft release.
                strength = (1-math.exp(-age*12))*math.exp(-age*2.7)
                wx,wy,ww,wh = wake.rect
                distance = max(wx-x,0,x-(wx+ww),wy-y,0,y-(wy+wh))
                influence = max(0,1-distance/8)*strength
                dx += wake.dx*influence
                dy += wake.dy*influence
            xx,yy = round(x+dx),round(y+dy)
            if 0 <= xx < self.width and 0 <= yy < self.height: output[xx,yy] = cell
        return output

    def collect_leaves(self, cells, step):
        now = self.clock()
        self.loose_leaves = [p for p in self.loose_leaves if now-p.born < 2]
        def release(x,y):
            if len(self.loose_leaves) < 48:
                self.loose_leaves.append(Particle(x,y,now,self.desktop,'~'))
        # Piles store their last frame geometry, so movement sheds from that spot.
        for name,(rect,columns,desktop) in list(self.leaf_piles.items()):
            if desktop != self.desktop: continue
            w = self.window(name)
            if self.bounds(w) != rect or not self.shown(w):
                for x in columns: release(x,rect[1]-1)
                del self.leaf_piles[name]
        output = dict(cells)
        for (x,y),value in cells.items():
            for w in reversed(self.windows):
                if not self.shown(w): continue
                wx,wy,ww,wh = self.bounds(w)
                if wx <= x < wx+ww and y == wy-1 and wy > 0:
                    rect,columns,desktop = self.leaf_piles.setdefault(w.name,(self.bounds(w),set(),self.desktop))
                    if len(columns) < 16 and sum(len(p[1]) for p in self.leaf_piles.values()) < 64:
                        columns.add(x)
                    break
        for name,(rect,columns,desktop) in self.leaf_piles.items():
            if desktop != self.desktop: continue
            wx,wy,ww,wh = rect
            # A slow intermittent spill keeps a pile from becoming permanent.
            if columns and step%12 == 0:
                x=min(columns);columns.remove(x)
                release(wx-1,wy)
            for x in columns: output[x,wy-1] = Cell('~',8)
        for p in self.loose_leaves:
            if p.desktop != self.desktop: continue
            age=now-p.born
            x=p.x+round(math.sin(age*4+p.x)*age)
            y=p.y+int(age*5)
            if 0 <= x < self.width and 0 <= y < self.height:
                output[x,y] = Cell('~' if int(age*6)%2 else '/',8)
        return output

    @property
    def work_height(self):return max(4,self.height-self.reserved_bottom)

    def activate(self,name):
        self.finish(False)
        was_overview=self.overview
        w=self.window(name)
        if name in self.full_window_apps and name not in self.maximized:self.maximize(name)
        before=w.rect;mw,mh=self.minimum_sizes.get(name,(0,0))
        w.w=min(self.width,max(w.w,mw));w.h=min(self.work_height,max(w.h,mh))
        w.x=max(0,min(w.x,self.width-w.w));w.y=max(0,min(w.y,self.work_height-w.h))
        if before!=w.rect:self.invalidate(before);self.invalidate(w.rect)
        w.opened=True
        if not w.pinned and w.desktop!=self.desktop:self.switch(w.desktop)
        if was_overview:self.toggle_overview()
        if not w.visible:self.visibility(name)
        if w.rolled:self.roll(name)
        self.select(name)
        self.session_changed('window',name)

    def reconcile_interaction(self):
        """Notify an existing view when it loses interaction; no owner creation."""
        forms=getattr(self,'app_forms',{})
        form=forms.get(self.focus);current=None
        if form is not None and not self.overview:
            w=self.window(self.focus)
            if w.opened and w.visible and not w.rolled and (w.pinned or w.desktop==self.desktop):
                current=(self.desktop,self.focus,form)
        previous=getattr(self,'_interaction_owner',None)
        if previous==current:return
        self._interaction_owner=current
        if previous is None:return
        _,name,form=previous
        # LazyApplication.owner is None until explicitly opened. Looking up its
        # existing owner/view never calls _ensure or changes resource lifetime.
        owner=vars(form).get('owner',form) if hasattr(form,'__dict__') else form
        target=getattr(owner,'view',owner) if owner is not None else None
        callback=getattr(target,'interaction_deactivated',None)
        if callable(callback):
            try:callback()
            except Exception as error:
                if not hasattr(self,'interaction_errors'):self.interaction_errors={}
                self.interaction_errors[name]=str(error)[:200]

    def session_changed(self,scope,key=None):
        self.reconcile_interaction()
        callback=getattr(self,'session_callback',None)
        if callback:callback(scope,key)

    def set_preference(self,key,value):
        from session import PREFS
        if key not in PREFS:raise ValueError('Unknown saved preference: '+str(key))
        if getattr(self,key)==value:return
        if key=='scenery':value=dict(value)
        if key=='app_preferences':
            from app_registry import validate_app_preferences
            value=validate_app_preferences(value)
        setattr(self,key,value)
        self.session_changed('preference',key)

    def titlebar(self,w,width):
        return window_chrome(w.name,width,self.style,self.ascii,w.rolled,w.pinned,w.name in self.maximized,self.control_side())

    def add_window(self,window,transient=False):
        if window.name in self.focus_order:raise ValueError('duplicate window name')
        self.windows.append(window);self._windows_by_name[window.name]=window;self.focus_order+=window.name,
        if transient:self.transient_windows.add(window.name)
        if self.shown(window):self.invalidate(window.rect)
        self.session_changed('structure')

    def control_side(self):
        # Cell width is available on every backend; no device-name/font guessing.
        return ('left' if self.width>=160 else 'right') if self.window_controls=='auto' else self.window_controls

    def set_window_controls(self,side):
        if side not in ('auto','left','right'):raise ValueError('unknown window control placement')
        if self.window_controls==side:return
        self.set_preference('window_controls',side)
        if self.overview:self.invalidate((0,0,self.width,self.height))
        else:
            for w in self.windows:
                if self.shown(w):self.invalidate((w.x,w.y,w.w,1))

    def set_show_underlying_text(self,enabled):
        enabled=bool(enabled)
        if self.show_underlying_text==enabled:return
        self.set_preference('show_underlying_text',enabled);self.invalidate((0,0,self.width,self.height))

    def set_terminal_opacity(self,value):
        if not 0<=value<=1:raise ValueError('terminal opacity must be between 0 and 1')
        if value==self.terminal_opacity:return
        self.set_preference('terminal_opacity',value)
        for name in self.terminal_layers:
            w=self.window(name)
            if self.shown(w):self.invalidate(w.rect)
        if self.overview:self.invalidate((0,0,self.width,self.height))

    def set_mouse_trails(self,enabled):
        self.set_preference('mouse_trails',bool(enabled))
        self.cell=self._cell
        if self.pointer_trail:
            for x,y in self.pointer_trail.overlay:self.invalidate((x,y,1,1))
        if enabled:
            from pointer_fx import PointerTrail
            self.pointer_trail=PointerTrail()
        else:self.pointer_trail=None

    def set_wm_escape(self,name):
        from input import WM_ESCAPES
        if name not in WM_ESCAPES:raise ValueError('unknown WM escape')
        self.set_preference('wm_escape',name)

    def set_pager(self,enabled):
        self.set_preference('show_pager',bool(enabled))
        if self.show_pager and self.pager is None:
            from desktop_pager import Pager
            self.pager=Pager()
        if self.pager:
            for x,y in self.pager.update(self):self.invalidate((x,y,1,1))
            if not self.show_pager:self.pager=None

    def report_mouse(self,x,y):
        if self.mouse_trails:
            if self.pointer_trail is None:self.set_mouse_trails(True)
            if 0<=x<self.width and 0<=y<self.height:self.pointer_trail.move(x,y,self.clock())

    def close(self,name):
        w=self.window(name)
        if not w.opened:return
        self.finish(False);self.invalidate(self.bounds(w))
        if name in self.maximized:
            x,y,width,height=self.maximized.pop(name)
            w.w,w.h=min(width,self.width),min(height,self.work_height)
            w.x,w.y=max(0,min(x,self.width-w.w)),max(0,min(y,self.work_height-w.h))
        self.animations.pop(name,None);self.visual.pop(name,None)
        w.opened=w.visible=False;w.rolled=False
        cleanup=self.window_cleanup.pop(name,None)
        if cleanup is not None:
            try:cleanup()
            except Exception as error:self.close_errors[name]=str(error)
        self.terminal_layers.discard(name)
        w.layer=None;w._opaque_cache=w._opaque_plane_cache=None
        if self._native is not None:self._native.planes.pop(name,None)
        self.repair_focus()
        if self.overview:
            if self.overview_selection==name:self.overview_selection=next((v.name for v in self.exposed_windows()),None)
            self.invalidate((0,0,self.width,self.height))
        self.session_changed('window',name)

    def maximize(self,name):
        self.finish(False);self.settle();w=self.window(name)
        self.invalidate(w.rect);w.rolled=False
        if name in self.maximized:
            x,y,width,height=self.maximized.pop(name)
            w.w,w.h=min(width,self.width),min(height,self.work_height)
            w.x,w.y=max(0,min(x,self.width-w.w)),max(0,min(y,self.work_height-w.h))
        else:
            self.maximized[name]=(w.x,w.y,w.w,w.h)
            w.x=w.y=0;w.w,w.h=self.width,self.work_height
        self.invalidate(w.rect)
        if self.overview:self.invalidate((0,0,self.width,self.height))
        self.session_changed('window',name)

    def task_windows(self):
        return tuple(self.window(name) for name in self.focus_order
                     if self.window(name).opened and (self.window(name).pinned or self.window(name).desktop==self.desktop))

    def task_click(self,name):
        w=self.window(name)
        if self.focused_button_minimizes and self.focus==name and self.shown(w) and not w.rolled and not self.overview:
            self.visibility(name)
        else:self.activate(name)

    def set_launcher(self,lines):
        lines=tuple(lines)
        if lines==self.launcher_lines:return
        previous=self.launcher_bounds() if self.launcher_lines else None
        self.launcher_lines=lines
        for rect in (previous,self.launcher_bounds() if lines else None):self._invalidate_launcher(rect)

    def _invalidate_launcher(self,rect):
        if rect is None:return
        x,y,width,height=rect
        indices=tuple(yy*self.width+xx
                      for yy in range(max(0,y),min(self.height,y+height))
                      for xx in range(max(0,x),min(self.width,x+width)))
        self.damage.update(indices);self.ui_damage.update(indices);self._launcher_dirty.update(indices)

    def launcher_bounds(self):
        width=min(36,self.width)
        height=min(len(self.launcher_lines),self.height)
        if self.launcher_anchor is None:return 0,max(0,self.height-height),width,height
        x,y,w,h=self.launcher_anchor
        if x<0:x=0
        elif x>=self.width:x=self.width-width
        if y<0:y=0
        elif y>=self.height:y=self.height-height
        elif y+h+height<=self.height:y+=h
        else:y-=height
        return max(0,min(self.width-width,x)),max(0,min(self.height-height,y)),width,height

    def window_status(self,w):
        if not w.visible:return 'minimized'
        if w.rolled:return 'rolled'
        return 'focused' if self.focus==w.name and self.shown(w) else 'open'

    def window_label(self,w):
        status=self.window_status(w)
        icons={'focused':'*','open':'o','rolled':'^','minimized':'-'} if self.ascii else {'focused':'●','open':'○','rolled':'▔','minimized':'·'}
        name=w.name if len(w.name)<=12 else w.name[:9]+'...' if self.ascii else w.name[:11]+'…'
        return icons[status]+' '+name+' '

    def cycle_focus(self, backward=False):
        if self.overview:
            names=[w.name for w in self.exposed_windows()]
            if names:
                index=names.index(self.overview_selection) if self.overview_selection in names else -1
                self.overview_selection=names[(index+(-1 if backward else 1))%len(names)]
                self.invalidate((0,0,self.width,self.height))
            return
        names = [name for name in self.focus_order if self.shown(self.window(name))]
        if names:
            index = names.index(self.focus) if self.focus in names else -1
            self.finish(False)
            self.select(names[(index+(-1 if backward else 1))%len(names)])

    def relative_desktop(self, direction, carry=False):
        name = self.focus if carry else None
        target = (self.desktop+direction)%self.desktop_count
        if name: self.send_to(name,target)
        self.switch(target)
        if name: self.select(name)

    def edge_motion(self, x, y):
        if not self.drag or self.drag[3]: return
        direction = -1 if x <= 0 else 1 if x >= self.width-1 else 0
        if not direction:
            self.edge = None
            self.edge_armed = True
        elif self.edge_armed and (not self.edge or self.edge[0] != direction):
            self.edge = (direction,self.clock(),x,y)

    def toggle_help(self):
        if self.help_lines:
            self.help_lines=()
        else:
            self.help_page=0
            self.help_content()
        self.invalidate((0,0,self.width,self.height))

    def help_pages(self):
        pages=(
            ('HELP 1/3 — Navigation and windows',
             'F6 / Shift-F6      Next / previous window',
             'Shift-F10         Actions for selected record/station',
             'Tab in apps        App pane/control; [ / ] app-owned',
             'WM escape          '+self.wm_escape+' toggles window commands',
             ', or right-click  Application menu',
             '1 2 3              Choose desktop',
             '[ / ]              Previous / next desktop',
             'Ctrl-Left/Right    Same, if terminal passes it',
             'd                  Desktop overview / expose',
             'm / r              Start move / resize',
             'Then arrows/hjkl   Adjust; Enter save; Esc cancel',
             'o / p / v          Roll up / pin / minimize',
             'X / Z              Close / maximize-restore (WM mode)',
             'Window list        ● focused ○ open ▔ rolled · hidden',
             '{ / }              Carry window to adjacent desktop',
             'q in WM mode       Quit (outside this help)'),
            ('HELP 2/3 — Appearance and demo effects',
             'Frame style        Settings > Window Manager > Style',
             'c                  Color palette',
             'e                  Desktop background effect',
             'w                  Synthetic weather preset',
             'b                  Background on / off',
             'x                  Dark background treatment',
             'a                  Animation on / off',
             'M                  Outline / live movement',
             'R                  Outline / live resize',
             'u                  Synthetic conversation update'),
            ('HELP 3/3 — Mouse and panels',
             'Drag title         Move; bottom-right corner resize',
             'Title wheel        Roll up / expand',
             'Title [x] / [+][=] Close / maximize-restore',
             'Hold at side edge  Carry window to next desktop',
             'Panel wheel        Switch desktop',
             'Drag [::widget]    Move widget between panels',
             'N                  Add panel at a free edge',
             'Click panel        Select panel for docking',
             'P                  Dock selected panel',
             'D                  Remove selected empty panel',
             'Overview           Click focus; drag into desktop'))
        return tuple((page[0],page[1:]) for page in pages)

    def help_content(self):
        title,lines=self.help_pages()[self.help_page]
        self.help_lines=(title,*lines,'', 'Left/Right: help page   ? / F1 / Esc: close')

    def help_step(self,direction):
        self.help_page=(self.help_page+direction)%3
        self.help_content()
        self.invalidate((0,0,self.width,self.height))

    @property
    def effect(self):
        return self.desktop_effects[self.desktop]

    def set_effect(self, name):
        if name not in EFFECTS: raise ValueError('unknown effect')
        expected='terrain' if name=='terrain' else 'effect:'+name
        if self.terrain_renderer is not None and getattr(self.terrain_renderer,'mode','terrain')!=expected and hasattr(self.terrain_renderer,'suspend'):
            self.terrain_renderer.suspend()
        self._effect_scene=None
        self._flux_period=1/FLUX_MAX_FPS;self._flux_due=0.;self._flux_budget_frame=None
        self.effect_frame_id=None;self._flux_generation_cpu=0.;self._flux_paint_cpu=0.
        self.camera_motion=None
        self.desktop_effects = [name]*self.desktop_count
        self.background_step = -1
        self.terrain_loading=False
        self.terrain_arrival=None
        self.particles.clear()
        self.leaf_piles.clear()
        self.loose_leaves.clear()
        self.surfaces.clear()
        self.background({})
        self.session_changed('desktop')

    def set_background_enabled(self,enabled):
        if type(enabled) is not bool:raise ValueError('background toggle must be boolean')
        self.set_preference('background_enabled',enabled)
        self._effect_scene=None
        self.background_step=-1
        if not enabled:
            if self.terrain_renderer is not None and hasattr(self.terrain_renderer,'suspend'):
                self.terrain_renderer.suspend()
            self.terrain_loading=False;self.terrain_arrival=None
            self._loading_frame=None;self._loading_frame_key=None;self._loading_wire=None
            self._loading_patch.clear();self._loading_draw=None
            self.build_snapshot=();self.build_wire=None;self.arrival_plan=None
        self.background({})
        # Loading/arrival overlays can exist before any base cells do. Their
        # removal still needs a repaint when both old/new backdrops are empty.
        self.invalidate((0,0,self.width,self.height))

    def toggle_tint(self):
        self.set_preference('tinted',not self.tinted)
        self.front=[None]*(self.width*self.height)
        self.invalidate((0,0,self.width,self.height))

    def set_glyphs(self, profile):
        if not isinstance(profile,Glyphs):raise TypeError('expected Glyphs profile')
        if self.glyphs.key==profile.key:return
        self.glyphs=profile
        for w in self.windows:w._opaque_cache=None;w._opaque_plane_cache=None
        if self._native is not None:self._native.planes.clear()
        self.front=[None]*(self.width*self.height)
        self.invalidate((0,0,self.width,self.height))

    def set_style(self, name):
        if name not in STYLES: raise ValueError('unknown style')
        if self.style == name: return
        self.set_preference('style',name)
        self.invalidate((0,0,self.width,self.height))

    def set_palette(self, name):
        if name not in PALETTES: raise ValueError('unknown palette')
        if self.palette == name: return
        self.set_preference('palette',name)
        # Stored cells use palette roles; palette changes invalidate physical colors.
        self.front = [None] * (self.width*self.height)
        self.invalidate((0,0,self.width,self.height))

    def background(self, cells):
        if hasattr(cells,'mark_changes') and hasattr(self.damage,'handle') and cells.width==self.width and cells.height==self.height:
            cells.mark_changes(self.damage,self.backdrop);self.backdrop=cells;return
        from camera_motion import Frame
        if isinstance(cells,Frame) or isinstance(self.backdrop,Frame):
            # Sampling the entire camera frame here would repeat the compositor's
            # work and block input before its bounded damage batches can run.
            self.backdrop=cells
            self.invalidate((0,0,self.width,self.height))
            return
        if isinstance(cells,Scene) and isinstance(self.backdrop,Scene) and cells.base is self.backdrop.base:
            keys=self.backdrop.overlay.keys()|cells.overlay.keys()
        else:keys=self.backdrop.keys()|cells.keys()
        for xy in keys:
            if self.backdrop.get(xy) != cells.get(xy):
                # Window shadows blend the source at this same screen cell.
                # A changed background pixel does not move shadow geometry.
                x,y=xy
                if 0<=x<self.width and 0<=y<self.height:self.damage.add(y*self.width+x)
        self.backdrop = cells

    def scene_cells(self,scene):
        if hasattr(scene,'as_cells'):return scene.as_cells(Cell)
        if not isinstance(scene,Scene):return {xy:Cell(*v) for xy,v in scene.items()}
        key=id(scene.base)
        if key not in self.scene_bases:
            if len(self.scene_bases)>=4:self.scene_bases.pop(next(iter(self.scene_bases)))
            self.scene_bases[key]=(scene.base,{xy:Cell(*v) for xy,v in scene.base.items()})
        return Scene(self.scene_bases[key][1],{xy:Cell(*v) for xy,v in scene.overlay.items()})

    def set_overview_opacity(self,value):
        if not 0<=value<=1:raise ValueError('opacity must be 0..1')
        self.set_preference('overview_opacity',value)
        self.front=[None]*(self.width*self.height)
        self.invalidate((0,0,self.width,self.height))

    def toggle_overview(self):
        self.finish(False)
        previous=self.camera_motion.current if self.camera_motion else self.camera_pose()
        self.settle()
        self.overview = not self.overview
        self.reconcile_interaction()
        self.start_camera_motion(previous)
        self.overview_selection=self.focus if self.focus else next((w.name for w in self.exposed_windows()),None)
        self.background_step = -1
        self.overview_drag = None
        self.overview_preview = None
        self.invalidate((0,0,self.width,self.height))

    def camera_pose(self):
        from camera_motion import pose
        return pose(self.desktop,self.overview,self.parallax,self.overview_zoom)

    def start_camera_motion(self, previous):
        if self.animate and self.effect=='terrain' and not self.terrain_loading and self.backdrop and previous!=self.camera_pose():
            from camera_motion import Motion
            self.camera_motion=Motion(self.backdrop,previous,self.camera_pose(),self.width,self.height,max(.18,self.animation_duration))

    def camera_background(self, cells):
        motion=self.camera_motion
        if motion is None:return cells
        if not self.animate or motion.end!=self.camera_pose():
            self.camera_motion=None
            return cells
        completed=self.terrain_renderer.completed if self.terrain_renderer else None
        expected=(self.desktop if self.parallax else 1,self.overview if self.overview_zoom!=1 else False)
        if completed and completed[0][4:6]==expected and motion.target is None:
            motion.target=cells;motion.began=self.clock()
        return self.backdrop

    def advance_camera(self):
        motion=self.camera_motion
        if motion is None or motion.began is None or self.damage:return
        step=int((self.clock()-motion.began)*30)
        if step==motion.step:return
        motion.step=step
        self.background(motion.frame(self.clock()))
        if self.clock()-motion.began>=motion.duration:self.camera_motion=None

    def mini_bounds(self, desktop):
        step = self.width//3
        width=max(3,step-1)
        height = max(3,min(self.height-2,round((width-2)*self.height/self.width)+2))
        return desktop*step,1,width,height

    def overview_windows(self,desktop):
        if self._overview_rendering:return self._overview_frame_groups[desktop]
        # Stable registration order keeps focus changes from rearranging previews.
        return [self.window(name) for name in self.focus_order if self.window(name).opened and self.window(name).desktop==desktop]

    def overview_layout(self,desktop):
        from overview import arrange
        windows=tuple((w.name,w.x,w.y,w.w,w.rect[3],w.visible) for w in self.overview_windows(desktop))
        return dict(arrange(self.mini_bounds(desktop),(self.width,self.height),windows))

    def mini_window(self,w,desktop):
        if self._overview_rendering:return self._overview_frame_minis.get((w.name,desktop),(0,0,0,0))
        x,y,width,height=self.mini_bounds(desktop)
        return (x+1+w.x*(width-2)//self.width,y+1+w.y*(height-2)//self.height,
                max(2,w.w*(width-2)//self.width),max(1,w.rect[3]*(height-2)//self.height))

    def exposed_windows(self):
        if self._overview_rendering:return self._overview_frame_windows
        return [self.window(name) for name in self.focus_order if self.window(name).opened]

    def expose_window(self,w):
        if self._overview_rendering:return self._overview_frame_expose.get(w.name,(0,0,0,0))
        from overview import arrange
        top=self.mini_bounds(0)[1]+self.mini_bounds(0)[3]+1
        step=self.width//self.desktop_count
        bounds=(w.desktop*step,top,max(3,step-1),max(3,self.height-top))
        windows=tuple((v.name,v.x,v.y,v.w,v.rect[3],v.visible) for v in self.overview_windows(w.desktop))
        return dict(arrange(bounds,(self.width,self.height),windows)).get(w.name,(0,0,0,0))

    def overview_destination(self,x,y):
        desktop=min(2,max(0,x//max(1,self.width//3)))
        xx,yy,ww,hh=self.mini_bounds(desktop)
        if yy<=y<yy+hh and xx<=x<xx+ww:
            return desktop, max(0,min(self.width-1,round((x-xx-1)*self.width/max(1,ww-2)))),max(0,min(self.height-1,round((y-yy-1)*self.height/max(1,hh-2))))
        top=self.mini_bounds(0)[1]+self.mini_bounds(0)[3]+1
        if y>=top:
            return desktop,max(0,min(self.width-1,round((x-xx-1)*self.width/max(1,ww-2)))),max(0,min(self.height-1,round((y-top-1)*self.height/max(1,self.height-top-2))))
        return self.desktop,max(0,min(self.width-1,x)),max(0,min(self.height-1,y))

    def resize(self, width, height):
        if width < 12 or height < 4:
            raise ValueError('workspace requires at least 12 by 4 cells')
        self.finish(False)
        self.settle()
        self.pointer_origin = None
        self.slide = None
        self.width, self.height = width, height
        available_height=self.work_height
        for w in self.windows:
            before=(w.x,w.y,w.w,w.h)
            if w.name in self.maximized:
                w.x=w.y=0;w.w,w.h=width,available_height
                if (w.x,w.y,w.w,w.h)!=before:self.session_changed('window',w.name)
                continue
            mw,mh=self.minimum_sizes.get(w.name,(0,0))
            w.w = min(width,max(w.w,mw))
            w.h = min(available_height,max(w.h,mh))
            w.x = max(0,min(w.x,width-w.w))
            w.y = max(0,min(w.y,available_height-(1 if w.rolled else w.h)))
            if (w.x,w.y,w.w,w.h)!=before:self.session_changed('window',w.name)
        self.front = [None]*(width*height)
        if hasattr(self.damage,'handle'):
            from native_scene import Damage
            self.damage=Damage(self.damage.lib,width*height,range(width*height));self.ui_damage=Damage(self.damage.lib,width*height)
        else:self.damage = set(range(width*height))
        self.minimize_targets.clear()
        self.particles.clear()
        self.wakes.clear()
        self.surfaces.clear()

    def bounds(self, w):
        if self.drag and self.drag[0] == w.name:
            mode = self.resize_mode if self.drag[3] else self.move_mode
            if mode == 'live': return self.drag[2]
        return self.visual.get(w.name, w.rect)

    def transition(self, w, start, end):
        self.invalidate(start)
        self.invalidate(end)
        if self.animate and start != end:
            self.visual[w.name] = start
            self.animations[w.name] = (start, end, self.clock())
        else:
            self.animations.pop(w.name, None)
            self.visual.pop(w.name, None)

    def background_delay(self):
        """Flux wakes on completion or its next frame, never idle worker polls."""
        if not self.background_enabled:return None
        if self.effect!='flux':return .1
        if self.launcher_lines or self.drag:return None
        pending=getattr(self.terrain_renderer,'pending',None)
        if self.background_async and pending is not None:
            return 0. if pending.done() else None
        return max(0.,self._flux_due-self.clock())

    def _flux_painted(self,cpu_seconds):
        if self.effect_frame_id is None or self.effect_frame_id==self._flux_budget_frame:return
        self._flux_paint_cpu+=cpu_seconds
        if self.damage:return
        # Balanced is the everyday default; fast demo explicitly spends more CPU.
        share=FLUX_FAST_CPU_SHARE if self.flux_performance=='fast demo' else FLUX_CPU_SHARE
        target=max(1/FLUX_MAX_FPS,(self._flux_generation_cpu+self._flux_paint_cpu)/share)
        self._flux_period=max(target,self._flux_period*.8)
        self._flux_due=self._flux_started+self._flux_period
        self._flux_budget_frame=self.effect_frame_id
        self._flux_paint_cpu=0.

    def tick(self, advance_background=True):
        if self.pointer_trail:
            for x,y in self.pointer_trail.update(self.clock(),self.width,self.height):self.invalidate((x,y,1,1))
            self.cell=self._pointer_cell if self.pointer_trail.overlay else self._cell
        if self.edge and self.drag and self.clock()-self.edge[1] >= .35:
            direction,_,x,y = self.edge
            name = self.drag[0]
            self.finish(True)
            self.relative_desktop(direction,carry=True)
            self.select(name)
            slide = self.slide
            self.begin()
            self.slide = slide
            self.pointer_origin = (x,y)
            self.edge_armed = False
            self.edge = None
        if self.slide:
            old, began, direction = self.slide
            self.invalidate((0,0,self.width,self.height))
            if self.clock()-began >= .18: self.slide = None
        if self.background_enabled and advance_background:
            elapsed=max(0,self.clock()-self.effect_epoch)
            # Fractional legacy steps retain Flux's speed at finer cadence.
            step = int(elapsed*FLUX_MAX_FPS)*6/FLUX_MAX_FPS if self.effect=='flux' else int(elapsed*6)
            pending=getattr(self.terrain_renderer,'pending',None)
            ready=self.effect=='flux' and self.background_async and pending is not None and pending.done()
            if self.effect=='flux' and pending is None and self.background_step>=0 and self.clock()<self._flux_due:
                self._tick_motion();return
            if step != self.background_step or ready:
                self.background_step = step
                if self.effect != 'matrix':
                    self.particles.clear()
                    if self.effect == 'terrain':
                        if self.terrain_renderer is None:
                            from model_scene import Renderer
                            self.terrain_renderer = Renderer()
                        from landscape_detail import Nature
                        from scenery import Config
                        nature=Nature(self.season,self.show_foliage,self.show_animals,self.show_flowers,self.show_lookout,self.scene_seed,self.terrain_grid,tuple(self.scenery[k] for k in Config._fields))
                        scene = self.terrain_renderer.frame(self.width,self.height,self.ascii,self.nature_age(),self.desktop,self.overview,self.light_mode,self.moon_phase,self.parallax,self.overview_zoom,self.terrain_shadows,nature)
                    elif self.background_async:
                        if self.terrain_renderer is None:
                            from frame_worker import Renderer
                            self.terrain_renderer=Renderer()
                        key=(self.width,self.height,self.ascii,self.effect,step,self.weather,self.scene_seed,self.nature_age(),self.flurry_strands,self.flurry_sway,self.flurry_speed,self.flux_density,self.flux_glow,self.flux_arms,self.flurry_provider)
                        if self.effect=='flux':
                            requested=getattr(self.terrain_renderer,'requested',None)
                            if ready and requested and requested[:4]+requested[5:7]+requested[8:]==key[:4]+key[5:7]+key[8:]:
                                # Harvest only; don't prefetch through the CPU budget.
                                key=requested
                            elif pending is None:self._flux_started=self.clock()
                        scene=self.terrain_renderer.effect_frame(key,_prepare_effect)
                        if scene is None or scene is self._effect_scene:
                            self._tick_motion();return
                        self._effect_scene=scene
                        step=self.terrain_renderer.fx_completed[0][4]
                        if self.effect=='flux':
                            trace=getattr(self.terrain_renderer,'trace',None)
                            cost=trace.progress().get('last_cpu_seconds') if trace is not None else 0.
                            self._flux_generation_cpu=cost if type(cost) in (int,float) and cost>=0 else 0.
                            self._flux_paint_cpu=0.
                    else:
                        if self.effect=='flux':
                            self._flux_started=self.clock();self._flux_generation_cpu=0.;self._flux_paint_cpu=0.
                        scene = effect_frame(self.effect,self.width,self.height,step,self.ascii,self.weather,seed=self.scene_seed,nature_age=self.nature_age(),flurry_strands=self.flurry_strands,flurry_sway=self.flurry_sway,flurry_speed=self.flurry_speed,flux_density=self.flux_density,flux_glow=self.flux_glow,flux_arms=self.flux_arms,flurry_provider=self.flurry_provider)
                    self.effect_generation+=1
                    self.effect_frame_id=(self.effect_generation,self.effect,step)
                    loading=self.effect=='terrain' and not scene.base if isinstance(scene,Scene) else False
                    if loading!=self.terrain_loading:
                        if self.terrain_loading and not loading and self.animate:
                            self.terrain_arrival=self.clock();self.arrival_progress=-1;self.arrival_presented=False
                        self.terrain_loading=loading;self.invalidate((0,0,self.width,self.height))
                    cells = self.scene_cells(scene)
                else:
                    cells = {}
                    now = self.clock()
                    self.particles = [p for p in self.particles if now-p.born < 1.1]
                    glyphs = '01:./+<>*'
                    # At most twelve short streams, with blank gaps between passes.
                    for column,(x,phase,speed,seed) in enumerate(matrix_plan(self.width,self.height,self.scene_seed)):
                        head=int(step*speed+phase)%(self.height+12)
                        # Rain meeting a visible window releases a small drop below it.
                        for window in reversed(self.windows):
                            if not self.shown(window): continue
                            wx,wy,ww,wh = self.bounds(window)
                            if wx <= x < wx+ww and wy-1 <= head < wy+wh:
                                if (step+column)%3 == 0 and len(self.particles) < 32:
                                    self.particles.append(Particle(x,wy+wh,now,self.desktop,glyphs[seed%len(glyphs)]))
                                    if wy > 0: cells[x,wy-1] = Cell('·' if not self.ascii else '.',6)
                                break
                        for age in range(3+column%3):
                            y = head-age
                            if 0 <= y < self.height:
                                glyph = glyphs[(seed+y*17+step//3)%len(glyphs)]
                                cells.setdefault((x,y),Cell(glyph,4 if age < 3 else 5))
                    for p in self.particles:
                        if p.desktop != self.desktop: continue
                        elapsed = now-p.born
                        y = p.y+int(elapsed*7)
                        for age in range(3):
                            yy = y-age
                            if p.y <= yy < self.height:
                                color = 6 if age == 0 and elapsed < .5 else 4 if age < 2 else 5
                                cells[p.x,yy] = Cell(p.glyph if age == 0 else ':',color)
                if self.effect in ('snow','rain'):
                    windows=[(w.name,self.bounds(w)) for w in self.windows if self.shown(w)]
                    values=self.surfaces.update({xy:tuple(c) for xy,c in cells.items()},windows,self.effect,self.weather.temperature,step,self.clock(),self.width,self.height)
                    cells={xy:Cell(*value) for xy,value in values.items()}
                if self.effect in ('snow','rain','leaves','flowers') and abs(self.weather.wind_x)>1:
                    # Scene retains a shared base; gusts belong to this frame's overlay.
                    gust_cells=cells.overlay if isinstance(cells,Scene) else cells
                    # Two dim, traveling gust strokes make ambient wind visible.
                    for i in range(2):
                        x=int(step*self.weather.wind_x/2+i*self.width/2)%self.width
                        y=(self.height//3+i*5)%self.height
                        for dx in range(3):
                            if x+dx<self.width:gust_cells[x+dx,y]=Cell('~' if dx==1 else '-',9)
                if self.effect == 'leaves': cells = self.collect_leaves(cells,step)
                cells=self.breeze(cells)
                self.background(self.camera_background(cells) if self.effect=='terrain' else cells)
        elif not self.background_enabled:
            self.particles.clear()
            self.wakes.clear()
            self.leaf_piles.clear()
            self.loose_leaves.clear()
            self.surfaces.clear()
        self._tick_motion()

    def _tick_motion(self):
        """Window/camera motion continues while a background frame is pending."""
        self.advance_camera()
        for name, (start, end, began) in list(self.animations.items()):
            t = min(1, max(0, (self.clock()-began)/self.animation_duration))
            eased = 1-(1-t)**3
            self.invalidate(self.visual[name])
            rect = tuple(round(a+(b-a)*eased) for a,b in zip(start,end))
            self.visual[name] = rect
            self.invalidate(rect)
            if t >= 1:
                del self.animations[name]
                del self.visual[name]
        self.repair_focus()
        if self.show_pager and self.pager is None:self.set_pager(True)
        if self.pager:
            for x,y in self.pager.update(self):self.invalidate((x,y,1,1))
            if not self.show_pager:self.pager=None

    def settle(self):
        self.camera_motion=None
        if self.slide:
            self.slide = None
            self.invalidate((0,0,self.width,self.height))
        for name in list(self.animations):
            w = self.window(name)
            self.invalidate(self.visual[name])
            self.invalidate(w.rect)
        self.animations.clear()
        self.visual.clear()

    def invalidate(self, rect, priority=True):
        x, y, w, h = rect
        margin=int(self.shadow_size) if self.shadow_enabled else 0
        left,right=max(0,x-margin),min(self.width,x+w+margin)
        top,bottom=max(0,y-margin),min(self.height,y+h+margin)
        if left>=right or top>=bottom:return
        targets=(self.damage,) if self._background_invalidating or not priority else (self.damage,self.ui_damage)
        if hasattr(self.damage,'mark'):
            for target in targets:target.mark(self.width,left,top,right-left,bottom-top)
            return
        if left==0 and right==self.width:
            for target in targets:target.update(range(top*self.width,bottom*self.width))
        else:
            for yy in range(top,bottom):
                base=yy*self.width
                for target in targets:target.update(range(base+left,base+right))

    def _invalidate_loading_points(self,points):
        """Batch already-clipped loading points, preserving exact shadow margins."""
        width,height=self.width,self.height
        margin=int(self.shadow_size) if self.shadow_enabled else 0
        if not margin:
            self.damage.update(y*width+x for x,y in points)
            return
        # Merge neighboring expanded spans on each source row, without filling
        # sparse gaps or changing unrelated window/decorations invalidation.
        rows={}
        for x,y in points:
            columns=rows.get(y)
            if columns is None:columns=[];rows[y]=columns
            columns.append(x)
        for row,columns in rows.items():
            columns.sort();left=right=None
            for x in columns:
                a,b=max(0,x-margin),min(width,x+margin+1)
                if left is not None and a<=right:
                    right=max(right,b)
                    continue
                if left is not None:
                    for yy in range(max(0,row-margin),min(height,row+margin+1)):
                        self.damage.update(range(yy*width+left,yy*width+right))
                left,right=a,b
            if left is not None:
                for yy in range(max(0,row-margin),min(height,row+margin+1)):
                    self.damage.update(range(yy*width+left,yy*width+right))


    def window(self, name):
        try:return self._windows_by_name[name]
        except KeyError:raise StopIteration from None

    def shown(self, w):
        return (w.visible or w.name in self.animations) and (w.pinned or w.desktop == self.desktop)

    def repair_focus(self):
        previous=self.focus
        if self.focus is None or not self.shown(self.window(self.focus)):
            self.focus = next((w.name for w in reversed(self.windows) if self.shown(w)), None)
            if self.focus: self.invalidate(self.window(self.focus).rect)
        if previous!=self.focus:self.session_changed('desktop')

    def focus_damage(self,w):
        if self.window_opacity<1 or not self.window_fill or w.layer:
            self.invalidate(w.rect);return
        x,y,width,height=self.bounds(w)
        for rect in ((x,y,width,1),(x,y+height-1,width,1),(x,y,1,height),(x+width-1,y,1,height)):self.invalidate(rect)
        for row,styles in w.styles.items():
            if any(role in ('selected','input') for _,_,role in styles):self.invalidate((x+1,y+1+row,width-2,1))

    def select(self, name):
        w=self.window(name)
        if not self.shown(w):return
        if self.focus==name and self.windows[-1] is w:return
        if self.focus:self.focus_damage(self.window(self.focus))
        # Raising an overlapping window exposes its body even if its text is unchanged.
        if any(self.shown(other) and other is not w and other.x<w.x+w.w and other.x+other.w>w.x and other.y<w.y+w.h and other.y+other.h>w.y for other in self.windows[self.windows.index(w)+1:]):self.invalidate(w.rect)
        self.windows.remove(w);self.windows.append(w);self.focus=name;self.focus_damage(w)
        self.session_changed('desktop')

    def switch(self, desktop):
        if not 0 <= desktop < self.desktop_count:
            raise ValueError('desktop out of range')
        if desktop==self.desktop:return
        self.finish(False)
        if self.overview:self.invalidate((0,0,self.width,self.height))
        previous=self.camera_motion.current if self.camera_motion else self.camera_pose()
        self.settle()
        self.pointer_origin = None
        old_desktop = self.desktop
        old_cells = None
        if self.animate and not self.overview and self.effect != 'terrain':
            windows=tuple(w for w in (self.windows if self._frame_windows is None else self._frame_windows) if self.shown(w))
            if self._native is not None:
                old_cells=self._native.scene_snapshot(self,windows,STYLES)
            if old_cells is None:
                geometry=tuple((w,*self.bounds(w)) for w in windows)
                old_cells=tuple(self.scene_cell(x,y,geometry=geometry) for y in range(self.height) for x in range(self.width))
        self.desktop_focus[self.desktop] = self.focus
        for w in self.windows:
            if self.shown(w): self.invalidate(w.rect)
        self.desktop = desktop
        self.start_camera_motion(previous)
        self.background_step = -1
        if old_cells:
            self.slide = (old_cells,self.clock(),1 if desktop > old_desktop else -1)
            self.invalidate((0,0,self.width,self.height))
        self.focus = self.desktop_focus.get(desktop)
        self.repair_focus()
        for w in self.windows:
            if self.shown(w): self.invalidate(w.rect)
        self.session_changed('desktop')

    def roll(self, name):
        self.finish(False)
        w = self.window(name)
        start = self.bounds(w)
        self.invalidate(start)
        w.rolled = not w.rolled
        # A title can be moved near the bottom while rolled up.
        if not w.rolled: w.y = max(0, min(w.y, self.work_height-w.h))
        self.transition(w, start, w.rect)
        self.session_changed('window',name)

    def pin(self, name):
        self.finish(False)
        w = self.window(name)
        self.invalidate(w.rect)
        w.pinned = not w.pinned
        if not w.pinned: w.desktop = self.desktop
        self.repair_focus()
        self.session_changed('window',name)

    def send_to(self, name, desktop):
        if not 0 <= desktop < self.desktop_count:
            raise ValueError('desktop out of range')
        self.finish(False)
        w = self.window(name)
        self.invalidate(w.rect)
        w.desktop, w.pinned = desktop, False
        self.repair_focus()
        self.session_changed('window',name)

    def content(self, name, version, lines,spans=(),layer=None):
        w=self.window(name);spans=tuple(spans)
        if version==w.version and spans==w.spans and layer is w.layer:return
        old_lines,old_styles,old_layer=w.lines,w.styles,w.layer
        lines=tuple(lines);styles={}
        for row,start,length,role in spans:styles.setdefault(row,[]).append((start,start+length,role))
        w.layer,w.spans,w.styles,w.version,w.lines=layer,spans,styles,version,lines
        w.builds+=1
        if not self.shown(w) or w.rolled:return
        if layer is not old_layer:
            self.invalidate(w.rect);return
        for row in range(min(w.h-2,max(len(old_lines),len(lines),max(styles,default=-1)+1,max(old_styles,default=-1)+1))):
            old=old_lines[row] if row<len(old_lines) else ''
            new=lines[row] if row<len(lines) else ''
            if old_styles.get(row)!=styles.get(row):self.invalidate((w.x+1,w.y+1+row,w.w-2,1))
            elif old!=new:
                width=w.w-2;a=old[:width].ljust(width);b=new[:width].ljust(width)
                different=[i for i in range(width) if a[i]!=b[i]]
                if different:self.invalidate((w.x+1+different[0],w.y+1+row,different[-1]-different[0]+1,1))

    def layer_patch(self, name, layer, indices):
        """Retain a producer-owned cell plane and invalidate its changed cells."""
        w=self.window(name)
        x,y,width,height,cells=layer
        if x<0 or y<0 or width<1 or height<1 or len(cells)!=width*height:raise ValueError('invalid layer')
        old=w.layer;w.layer=layer
        if not self.shown(w) or w.rolled:return
        if indices is None or old is None or old[:4]!=layer[:4]:
            for rect in ((old[:4],layer[:4]) if old is not None else (layer[:4],)):
                xx,yy,ww,hh=rect;ww=min(ww,w.w-2-xx);hh=min(hh,w.h-2-yy)
                if ww>0 and hh>0:self.invalidate((w.x+1+xx,w.y+1+yy,ww,hh))
            return
        for i in indices:
            if not 0<=i<len(cells):raise ValueError('layer index out of range')
            xx,yy=i%width,i//width
            if x+xx<w.w-2 and y+yy<w.h-2:self.invalidate((w.x+1+x+xx,w.y+1+y+yy,1,1))

    def visibility(self, name):
        self.finish(False)
        w = self.window(name)
        target = self.minimize_targets.get(name, (w.x, self.height-1, 12, 1))
        start = self.bounds(w) if w.visible or name in self.animations else target
        w.visible = not w.visible
        self.transition(w, start, w.rect if w.visible else target)
        self.repair_focus()
        self.session_changed('window',name)

    def begin(self, resize=False, name=None):
        self.settle()
        name=name or self.focus
        if name is None:return
        if name in self.maximized:self.maximize(name)
        w = self.window(name)
        if w.rolled and resize: return
        self.drag = [w.name, w.rect, w.rect, resize]
        self.resize_anchor=(False,True,True)
        self.invalidate((0,0,self.width,1))
        self.invalidate_drag(w.rect)

    def invalidate_drag(self,rect):
        """An outline changes its border, not the retained window interior."""
        if not self.drag or (self.resize_mode if self.drag[3] else self.move_mode)!='outline':
            self.invalidate(rect);return
        x,y,width,height=rect
        for xx,yy,w,h in ((x,y,width,1),(x,y+height-1,width,1),(x,y+1,1,height-2),(x+width-1,y+1,1,height-2)):
            left,right=max(0,xx),min(self.width,xx+w)
            top,bottom=max(0,yy),min(self.height,yy+h)
            if left>=right or top>=bottom:continue
            if hasattr(self.damage,'mark') and hasattr(self.ui_damage,'mark'):
                for target in (self.damage,self.ui_damage):target.mark(self.width,left,top,right-left,bottom-top)
            else:
                for row in range(top,bottom):
                    indices=range(row*self.width+left,row*self.width+right)
                    self.damage.update(indices);self.ui_damage.update(indices)

    def motion(self, dx, dy):
        # Replace the pending target; callers supply absolute displacement.
        self.latest = dx, dy

    def advance(self):
        if self.drag and self.latest is not None:
            name, original, proposed, resize = self.drag
            self.invalidate_drag(proposed)
            x, y, w, h = original
            dx, dy = self.latest
            if resize:
                mw,mh=self.minimum_sizes.get(name,(12,4))
                left,right,bottom=self.resize_anchor
                if left:
                    delta=max(-x,min(dx,w-mw));x+=delta;w-=delta
                elif right:w=min(self.width-x,max(mw,w+dx))
                if bottom:h=min(self.work_height-y,max(mh,h+dy))
            else:
                x, y = max(0, min(self.width-w, x+dx)), max(0, min(self.work_height-h, y+dy))
            if not resize and self.snap_windows:
                from window_layout import snap
                x,y,w,h=snap((x,y,w,h),(self.bounds(other) for other in self.windows if other.name!=name and self.shown(other)),(self.width,self.work_height))
            self.drag[2] = x, y, w, h
            if not resize and self.move_mode == 'live':
                self.stir(name,proposed,self.drag[2])
            self.invalidate_drag(self.drag[2])
            self.latest = None

    def finish(self, commit):
        self.edge = None
        self.advance()
        if self.drag:
            name, original, proposed, resize = self.drag
            self.invalidate(proposed)
            self.invalidate(original)
            if commit:
                if not resize and self.move_mode == 'outline': self.stir(name,original,proposed)
                w = self.window(name)
                self.invalidate(w.rect)
                w.x, w.y, w.w, height = proposed
                if not w.rolled: w.h = height
                self.session_changed('window',name)
            self.drag = None
            self.invalidate((0,0,self.width,1))

    def pointer(self, button, x, y, released=False):
        if self.screensaver:
            if not released and not button&32:
                self.screensaver=False;self.set_effect(self.screensaver_effect)
                self.invalidate((0,0,self.width,self.height))
            return
        if self.overview or (button & 64 and y >= self.height):
            if button & 64:
                if not released and button & 3 in (0,1):
                    self.switch((self.desktop+(1 if button & 1 else -1))%3)
                return
            desktop,px,py = self.overview_destination(x,y)
            if button & 32:
                if self.overview_drag:
                    self.overview_target = desktop
                    w=self.window(self.overview_drag[0])
                    gx,gy,ox,oy=self.overview_grab
                    nx=max(0,min(self.width-w.w,px-gx))
                    ny=max(0,min(self.work_height-w.rect[3],py-gy))
                    self.overview_preview=(desktop,nx,ny)
                    self.invalidate((0,0,self.width,self.height))
                return
            if released:
                if self.overview_drag:
                    name,origin=self.overview_drag
                    w=self.window(name)
                    moved=self.overview_preview is not None or desktop!=origin
                    if moved:
                        if desktop!=origin:self.send_to(name,desktop)
                        gx,gy,_,_=self.overview_grab
                        w.x=max(0,min(self.width-w.w,px-gx))
                        w.y=max(0,min(self.work_height-w.rect[3],py-gy))
                        self.session_changed('window',name)
                    else:
                        self.switch(origin)
                        self.toggle_overview()
                        if not w.visible:self.visibility(name)
                        self.select(name)
                    self.overview_drag=None
                    self.overview_preview=None
                self.invalidate((0,0,self.width,self.height))
            elif button == 0:
                self.overview_drag=None;self.overview_preview=None
                self.overview_target=desktop
                candidates=[]
                grab=None
                for w in self.overview_windows(desktop):
                    xx,yy,ww,hh=self.mini_window(w,desktop)
                    if xx<=x<xx+ww and yy<=y<yy+hh:
                        candidates.append((w,desktop))
                        grab=(max(0,min(w.w-1,round((x-xx)*w.w/max(1,ww)))),max(0,min(w.rect[3]-1,round((y-yy)*w.rect[3]/max(1,hh)))))
                        break
                if not candidates:
                    for w in self.exposed_windows():
                        xx,yy,ww,hh=self.expose_window(w)
                        if xx<=x<xx+ww and yy<=y<yy+hh:
                            candidates.append((w,w.desktop))
                            grab=(max(0,min(w.w-1,round((x-xx)*w.w/max(1,ww)))),max(0,min(w.rect[3]-1,round((y-yy)*w.rect[3]/max(1,hh)))))
                            break
                if candidates:
                    w,origin=candidates[0]
                    self.overview_selection=w.name
                    self.overview_drag=(w.name,origin)
                    self.overview_grab=(*(grab if grab else (px-w.x,py-w.y)),w.x,w.y)
                elif y<self.mini_bounds(0)[1]+self.mini_bounds(0)[3]:self.switch(desktop)
            return
        if self.pager and not any(self.shown(w) and w.x<=x<w.x+w.w and w.y<=y<w.y+w.rect[3] for w in self.windows):
            desktop=self.pager.hit(x,y)
            if desktop is not None:
                if button&64 and not released and self.desktop_scroll:self.relative_desktop(1 if button&1 else -1)
                elif button==0 and not released:self.switch(desktop)
                return
        if button & 64:
            if self.desktop_scroll and not released and not any(self.shown(w) and w.x<=x<w.x+w.w and w.y<=y<w.y+w.rect[3] for w in self.windows):
                self.relative_desktop(1 if button&1 else -1);return
            if not released and button & 3 in (0, 1):
                for w in reversed(self.windows):
                    if self.shown(w) and self.bounds(w)[0] <= x < self.bounds(w)[0]+self.bounds(w)[2] and self.bounds(w)[1] <= y < self.bounds(w)[1]+self.bounds(w)[3]:
                        if y == w.y:
                            rolled = (button & 3) == 0
                            if w.rolled != rolled: self.roll(w.name)
                        break
            return
        if released:
            if self.pointer_origin and self.drag:
                ox, oy = self.pointer_origin
                self.motion(x-ox, y-oy)
                self.finish(True)
            self.pointer_origin = None
            return
        if button & 32:
            if self.pointer_origin and self.drag:
                ox, oy = self.pointer_origin
                self.motion(x-ox, y-oy)
                self.edge_motion(x,y)
            return
        if button & 3 or button & 64:
            return
        self.finish(False)
        self.edge_armed = True
        self.pointer_origin = None
        for w in reversed(self.windows):
            if self.shown(w) and self.bounds(w)[0] <= x < self.bounds(w)[0]+self.bounds(w)[2] and self.bounds(w)[1] <= y < self.bounds(w)[1]+self.bounds(w)[3]:
                wx,wy,ww,wh=self.bounds(w)
                action=next((action for action,start,end in self.titlebar(w,ww)[1] if start<=x-wx<end),None) if y==wy else None
                if action=='close':self.close(w.name);break
                self.select(w.name)
                if action=='minimize':self.visibility(w.name)
                elif action=='pin':self.pin(w.name)
                elif action=='roll':self.roll(w.name)
                elif action=='maximize':self.maximize(w.name)
                elif y==wy or (x==wx+ww-1 and y==wy+wh-1) or (self.resize_edges and (x in (wx,wx+ww-1) or y==wy+wh-1)):
                    self.begin(y!=wy)
                    if y!=wy and self.resize_edges:self.resize_anchor=(x==wx,x==wx+ww-1,y==wy+wh-1)
                    self.pointer_origin=(x,y)
                break

    def opaque_plane(self,w,width,height):
        """Compile body runs once per changed row; focus only restyles interested rows."""
        signature=(width,height,self.focus==w.name,self.style,self.ascii,self.glyphs.key,self.palette,self.tinted,w.name,w.rolled,w.pinned,w.name in self.maximized,self.control_side(),tuple(w.lines),tuple((row,tuple(spans)) for row,spans in sorted(w.styles.items())))
        retained=w._opaque_plane_cache
        if retained is not None and retained[0]==signature:return retained[1]
        cache=w._opaque_cache
        if cache is None:cache={};w._opaque_cache=cache
        focus=w.name==self.focus;color=chrome_ink(1 if focus else 2,self._ansi_colors(),self.tinted)
        tl,tr,bl,br,horizontal,vertical=('+','+','+','+','-','|') if self.ascii else STYLES[self.style]
        title=self.titlebar(w,width)[0]
        rows=[tuple(Cell(c,color) for c in self.glyphs.text(title,self.ascii))]
        vertical=self.glyphs.cell(vertical,self.ascii)
        bl,br,horizontal=(self.glyphs.cell(c,self.ascii) for c in (bl,br,horizontal))
        border=Cell(vertical,color);blank=Cell(' ',0)
        for row in range(max(0,height-2)):
            text=w.lines[row] if row<len(w.lines) else ''
            styles=tuple(w.styles.get(row,()))
            interest=focus if any(role in ('selected','input') for _,_,role in styles) else False
            key=(width,text,styles,self.palette,interest,self.ascii,self.glyphs.key)
            prior=cache.get(row)
            if prior is None or prior[0]!=key:
                body=[blank]*(width-2)
                for x,char in enumerate(self.glyphs.text(text[:width-2],self.ascii)):body[x]=Cell(char,0)
                for start,end,role in styles:
                    ink_color=control_ink(role,self.palette,focus)
                    for x in range(max(0,start),min(width-2,end)):body[x]=Cell(body[x].char,ink_color)
                prior=(key,tuple(body));cache[row]=prior;self.opaque_rows_built+=1
            rows.append((border,)+prior[1]+(border,))
        if height>1:rows.append((Cell(bl,color),)+(Cell(horizontal,color),)*(width-2)+(Cell(br,color),))
        for row in tuple(cache):
            if row>=height-2:cache.pop(row)
        plane=tuple(rows);w._opaque_plane_cache=(signature,plane)
        return plane

    def _loader_cell(self,x,y):
        if self._loading_frame is not None and len(self._loading_frame)==self.width*self.height:
            index=y*self.width+x
            if index in self._loading_patch:
                self._loading_frame[index]=Cell(*self._loading_draw(x,y))
                self._loading_patch.discard(index)
            return self._loading_frame[index]
        from loading import cell
        return Cell(*cell(self.width,self.height,x,y,self.loading_step,self.ascii,self.build_snapshot,STYLES[self.style],self.build_wire,self.build_wire_progress))

    def scene_cell(self, x, y, include_outline=True, geometry=None):
        if include_outline:
            outline=self.outline_cell(x,y)
            if outline is not None:return outline
        if self.terrain_loading:result=self._loader_cell(x,y)
        else:result=self.backdrop.get((x,y),DESKTOP_BLANK)
        if self.pager:result=self.pager.cell(result,x,y)
        surface=result
        if geometry is None:
            geometry=((w,*self.bounds(w)) for w in (self.windows if self._frame_windows is None else self._frame_windows) if self.shown(w))
        dx,dy={'SE':(1,1),'S':(0,1),'SW':(-1,1),'W':(-1,0),'NW':(-1,-1),'N':(0,-1),'NE':(1,-1),'E':(1,0)}[self.shadow_direction]
        for w,wx,wy,ww,wh in geometry:
            sx,sy=wx+dx*self.shadow_size,wy+dy*self.shadow_size
            if self.shadow_enabled and sx<=x<sx+ww and sy<=y<sy+wh:
                if not (wx<=x<wx+ww and wy<=y<wy+wh):
                    result=Cell(result.char,shade_ink(result.color,self.shadow_opacity));surface=Cell(surface.char,shade_ink(surface.color,self.shadow_opacity))
            if not (wx <= x < wx+ww and wy <= y < wy+wh):
                continue
            behind=result;under=surface
            xx, yy = x-wx, y-wy
            color = 1 if w.name == self.focus else 2
            tl, tr, bl, br, horizontal, vertical = ('+', '+', '+', '+', '-', '|') if self.ascii else STYLES[self.style]
            if yy == 0:
                title=self.titlebar(w,ww)[0]
                char=title[xx]
                result=Cell(char,chrome_ink(color,self._ansi_colors(),self.tinted))
                surface=surface_cell(under.char,window_pane_ink(under.color,self.window_opacity)) if self.window_fill and self.window_opacity<1 else BLANK if self.window_fill else under
            elif yy == wh-1:
                char=bl if xx == 0 else br if xx == ww-1 else horizontal
                result=Cell(char,chrome_ink(color,self._ansi_colors(),self.tinted))
                surface=surface_cell(under.char,window_pane_ink(under.color,self.window_opacity)) if self.window_fill and self.window_opacity<1 else BLANK if self.window_fill else under
            elif xx in (0, ww-1):
                result=Cell(vertical,chrome_ink(color,self._ansi_colors(),self.tinted))
                surface=surface_cell(under.char,window_pane_ink(under.color,self.window_opacity)) if self.window_fill and self.window_opacity<1 else BLANK if self.window_fill else under
            else:
                line = w.lines[yy-1] if yy-1 < len(w.lines) else ''
                # Unsupported widths retain one visible placeholder per scalar.
                char = line[xx-1] if xx-1 < len(line) else ' '
                char=self.glyphs.cell(char,self.ascii)
                role=next((role for start,end,role in reversed(w.styles.get(yy-1,())) if start<=xx-1<end),None)
                if role:
                    color=control_ink(role,self.palette,w.name==self.focus)
                    if self.window_fill and self.window_opacity<1:
                        surface=surface_cell(*terminal_background(' ',color,under.char,under.color,self.window_opacity))
                        base=behind if self.show_underlying_text and char==' ' else under
                        result=surface if char==' ' and base is under else Cell(*terminal_background(char,color,base.char,base.color,self.window_opacity))
                    else:result=Cell(char,color);surface=surface_cell(' ',color) if self.window_fill else under
                elif not self.window_fill or self.window_opacity>=1:
                    result=Cell(char,0);surface=BLANK if self.window_fill else under
                else:
                    shaded=window_pane_ink(under.color,self.window_opacity)
                    surface=surface_cell(under.char,shaded)
                    if char==' ':
                        result=Cell(behind.char,window_pane_ink(behind.color,self.window_opacity)) if self.show_underlying_text else surface
                    else:result=Cell(char,window_text_ink(shaded))
                if w.layer:
                    lx,ly,lw,lh,cells=w.layer
                    if lx<=xx-1<lx+lw and ly<=yy-1<ly+lh:
                        result=Cell(*cells[(yy-1-ly)*lw+xx-1-lx]);layer_cell=result
                        if self.terminal_opacity<1 and w.name in self.terminal_layers:
                            base=behind if self.show_underlying_text and result.char==' ' else under
                            result=Cell(*terminal_background(result.char,result.color,base.char,base.color,self.terminal_opacity))
                        if layer_cell.char in ('▄','▀','█'):surface=result
                        elif self.terminal_opacity<1 and w.name in self.terminal_layers:
                            surface=surface_cell(*terminal_background(' ',layer_cell.color,under.char,under.color,self.terminal_opacity))
                        else:surface=surface_cell(' ',layer_cell.color)
                        if self.ascii and ord(result.char)>127:result=Cell(':',result.color)
                if not self.window_fill:
                    if result.char in (' ','▄','▀'):
                        result=behind
                    else:
                        source=result.color
                        if source>=1<<48:
                            fore=tuple((source>>shift)&255 for shift in (40,32,24))
                            back=tuple((behind.color>>shift)&255 for shift in (16,8,0)) if behind.color>=1<<48 else (12,12,12)
                            result=Cell(result.char,ink(*fore,background=back))
                        else:result=Cell(result.char,inherit_background(source,behind.color))
        return result

    def outline_cell(self,x,y):
        if self.drag and (self.resize_mode if self.drag[3] else self.move_mode) == 'outline':
            xx, yy, ww, hh = self.drag[2]
            if xx <= x < xx+ww and yy <= y < yy+hh and (x in (xx,xx+ww-1) or y in (yy,yy+hh-1)):
                corner = x in (xx,xx+ww-1) and y in (yy,yy+hh-1)
                glyph = '+' if self.ascii else ('┌' if x == xx and y == yy else '┐' if y == yy else '└' if x == xx else '┘')
                return Cell(glyph if corner else ('-' if self.ascii else '─') if y in (yy,yy+hh-1) else ('|' if self.ascii else '│'), 3)
        return None

    def overview_window_cell(self,w,rect,x,y,mini=False):
        """Use normal frame styles; contrast belongs to windows, not the scene."""
        wx,wy,width,height=rect
        xx,yy=x-wx,y-wy
        under=self.backdrop.get((x,y),DESKTOP_BLANK)
        body=Cell(under.char,shade_ink(under.color,.78 if w.name==self.focus else .65))
        color=3 if self.overview_drag and self.overview_drag[0]==w.name or self.overview_selection==w.name else 1 if w.name==self.focus else 2 if w.visible else 5
        tl,tr,bl,br,horizontal,vertical=('+','+','+','+','-','|') if self.ascii else STYLES[self.style]
        if yy==0:
            label=' '+('[min] ' if not w.visible else '')+w.name+' '
            title=(tl+label)[:max(0,width-1)].ljust(max(0,width-1),horizontal)+tr
            return Cell(title[xx],color)
        if yy==height-1:
            return Cell(bl if xx==0 else br if xx==width-1 else horizontal,color)
        if xx in (0,width-1):return Cell(vertical,color)
        if not mini:
            row,column=yy-2,xx-2
            text=w.lines[row] if 0<=row<len(w.lines) else ''
            if 0<=column<len(text) and xx<width-2:
                char=text[column]
                if char!=' ':return Cell(char if ' '<=char<='~' else '?',16)
        return body

    def cell(self, x, y):
        base=self._cell(x,y)
        if self.pointer_trail and (x,y) in self.pointer_trail.overlay:
            from pointer_fx import glint
            return Cell(*glint(base.char,base.color,*self.pointer_trail.overlay[x,y]))
        return base

    _pointer_cell=cell

    def overlay_cell(self, x, y):
        if self.launcher_lines:
            left,top,width,height=self.launcher_bounds()
            if top<=y<top+height and left<=x<left+width:
                line=self.launcher_lines[y-top].ljust(width)
                return Cell(line[x-left],1 if line.startswith('>') or y==top else 0)
        if self.screensaver:return self.backdrop.get((x,y),DESKTOP_BLANK)
        if self.settings_lines:
            left=max(0,(self.width-58)//2)
            if 1<=y<=len(self.settings_lines) and left<=x<min(self.width,left+58):
                line=self.settings_lines[y-1].ljust(58)
                return Cell(line[x-left],1 if line.startswith('>') or y==1 else 0)
        if self.drag and self.pointer_origin is None and y==0 and not self.help_lines:
            label=('RESIZE ' if self.drag[3] else 'MOVE ')+self.drag[0]+' | Arrows/hjkl adjust | Enter save | Esc cancel'
            return Cell(label[x] if x<len(label) else ' ',3)
        if self.help_lines:
            left = max(0,(self.width-58)//2)
            if 1 <= y <= len(self.help_lines) and left <= x < min(self.width,left+58):
                line = self.help_lines[y-1].ljust(58)
                return Cell(line[x-left],1 if y == 1 else 0)
        return None

    def _cell(self, x, y):
        overlay=self.overlay_cell(x,y)
        if overlay is not None:return overlay
        if self.overview:
            background=self.backdrop.get((x,y),DESKTOP_BLANK)
            pane=Cell(background.char,pane_ink(background.color,self.overview_opacity*.35)) if self.overview_opacity else background
            desktop = min(2,x//max(1,self.width//3))
            xx,yy,ww,hh = self.mini_bounds(desktop)
            if yy <= y < yy+hh:
                color = 3 if self.overview_drag and desktop == self.overview_target else 1 if desktop == self.desktop else 2
                tl,tr,bl,br,horizontal,vertical=('+','+','+','+','-','|') if self.ascii else STYLES['thin' if self.style=='bare' else self.style]
                if x>=xx+ww:return background
                if y == yy:
                    marker=' DROP' if self.overview_drag and desktop==self.overview_target else (' *' if self.ascii else ' ●') if desktop==self.desktop else ''
                    title=' Desktop '+str(desktop+1)+marker+' '
                    line=(tl+title)[:ww-1].ljust(ww-1,horizontal)+tr
                    return Cell(line[x-xx],color if x-xx in (0,ww-1) or desktop==self.desktop or color==3 else 0)
                if y == yy+hh-1:return Cell(bl if x==xx else br if x==xx+ww-1 else horizontal,color)
                if x in (xx,xx+ww-1):return Cell(vertical,color)
                # One continuous landscape underneath all transparent regions.
                # Desktop bounds contain windows; they do not repeat a wallpaper.
                result = pane
                for w in self.overview_windows(desktop):
                    wx,wy,width,height = self.mini_window(w,desktop)
                    if wx <= x < min(wx+width,xx+ww-1) and wy <= y < min(wy+height,yy+hh-1):
                        rect=(wx,wy,min(width,xx+ww-1-wx),min(height,yy+hh-1-wy))
                        result=self.overview_window_cell(w,rect,x,y)
                if self.overview_preview and self.overview_preview[0]==desktop:
                    _,nx,ny=self.overview_preview
                    w=self.window(self.overview_drag[0])
                    gx=xx+1+nx*(ww-2)//self.width
                    gy=yy+1+ny*(hh-2)//self.height
                    gw=max(2,w.w*(ww-2)//self.width)
                    gh=max(1,w.rect[3]*(hh-2)//self.height)
                    if gx<=x<gx+gw and gy<=y<gy+gh and (x in (gx,gx+gw-1) or y in (gy,gy+gh-1)):
                        result=Cell('#' if self.ascii else '·',3)
                return result
            for w in self.exposed_windows():
                rect=self.expose_window(w)
                wx,wy,ww,hh=rect
                if wx<=x<wx+ww and wy<=y<wy+hh:
                    return self.overview_window_cell(w,rect,x,y)
            if y==0:
                label='Desktops above / spatial expose below — click to focus; drag to move'
                return Cell(label[x] if x<len(label) else ' ',2)
            return background
        if self.slide:
            old,began,direction = self.slide
            t=min(1,max(0,(self.clock()-began)/.18))
            offset = round(self.width*t*t*(3-2*t))
            source = x+direction*offset
            if 0 <= source < self.width: return old[y*self.width+source]
            return self.scene_cell(source-direction*self.width,y)
        return self.scene_cell(x,y)

    def launcher_damage(self,budget=None,inside=True):
        if inside and not self.launcher_lines or not inside and not self._launcher_dirty:return ()
        bounds=self.launcher_bounds() if inside else None;result=[]
        # Materialize each bounded native dirty map once, rather than crossing
        # the Python/C boundary twice for every menu cell on every batch.
        damage=set(self.damage)
        eligible=set(self.ui_damage).intersection(damage)
        self._launcher_dirty.intersection_update(damage)
        if bounds:
            x,y,width,height=bounds
            candidates=(i for i in sorted(eligible) if x<=i%self.width<x+width and y<=i//self.width<y+height)
        else:candidates=sorted(self._launcher_dirty.intersection(eligible))
        result=list(candidates) if bounds else candidates
        return result if budget is None else result[:max(1,budget)]

    def _phase_start(self):
        return (time.monotonic(),time.thread_time()) if self.observe_composition else None

    def _phase_end(self,name,start):
        if start is None:return
        wall=time.monotonic()-start[0];cpu=time.thread_time()-start[1]
        row=self.compose_phases.setdefault(name,dict(calls=0,wall_seconds=0.,cpu_seconds=0.,max_wall_seconds=0.))
        row['calls']+=1;row['wall_seconds']+=wall;row['cpu_seconds']+=cpu
        row['last_wall_seconds']=wall;row['max_wall_seconds']=max(row['max_wall_seconds'],wall)

    def flush(self, budget=2048, max_seconds=None):
        if not self.background_enabled or self.effect!='flux' or self._flux_external_budget:return self._flush(budget,max_seconds)
        started=time.thread_time()
        try:return self._flush(budget,max_seconds)
        finally:self._flux_painted(time.thread_time()-started)

    def _flush(self, budget=2048, max_seconds=None):
        self.composed_indices=() # Reuse existing batch indices; no copied cell buffer.
        self.ui_painted=False
        bounds=self.launcher_bounds() if self.launcher_lines else None
        if bounds!=self._launcher_presented_bounds:
            self._invalidate_launcher(self._launcher_presented_bounds)
            self._invalidate_launcher(bounds)
            self._launcher_presented_bounds=bounds
        menu_indices=self.launcher_damage(budget) if budget>0 else ()
        overlay_indices=self.launcher_damage(budget,inside=False) if budget>0 else ()
        if self.launcher_lines and not menu_indices and not self.launcher_damage(1,inside=False):return '',0,0
        if menu_indices and len(menu_indices)==len(overlay_indices) and self._native is not None:
            try:
                output,changed,computed=self._native.menu_flush(self,menu_indices)
                self.ui_damage.difference_update(menu_indices);self.damage.difference_update(menu_indices)
                self._launcher_dirty.difference_update(menu_indices)
                self.composed+=computed;self.ui_painted=True
                self.composed_indices=menu_indices if self.observe_composition else ()
                self.render_backend='native';self.render_reason='menu_overlay'
                return output,changed,computed
            except (ValueError,MemoryError,OSError) as error:
                self.native_error=str(error);self.front=list(self.front);self._native=None
        deadline=time.monotonic()+max_seconds if max_seconds is not None else None
        ui_pending=bool(self.ui_damage);menu_open=bool(self.launcher_lines)
        menu_busy=menu_open or bool(self._launcher_dirty)
        self._background_invalidating=True
        phase=self._phase_start()
        try:self.tick(advance_background=not menu_busy and not (self.effect=='flux' and self.drag) and (not self.ui_damage or self.effect!='terrain') and (self.effect not in ('flurry','flux','terrain') or not self.damage or self.background_step<0))
        finally:
            self._background_invalidating=False
            self._phase_end('tick',phase)
        self.advance()
        loading_points=None
        if self.terrain_loading and not menu_busy and (not self.damage or self.loading_step<0):
            snapshot=self.terrain_renderer.trace.snapshot() if self.terrain_renderer else ()
            wire=self.terrain_renderer.trace.wire() if self.terrain_renderer else None
            changed=snapshot!=self.build_snapshot or wire is not self.build_wire
            if wire is not self.build_wire:self.build_wire_started=self.clock()
            self.build_wire_progress=min(1,max(0,(self.clock()-self.build_wire_started)/.65))
            self.build_snapshot=snapshot;self.build_wire=wire
            step=round(self.clock()*6)*8/6 if self.animate else 0
            if step!=self.loading_step or changed:
                self.loading_step=step
                if self._loading_frame is None:self.invalidate((0,0,self.width,self.height),priority=False)
                else:
                    from loading import changed_points
                    loading_points=tuple(changed_points(self.width,self.height,self.build_wire,self._loading_wire,step if self.build_wire_progress>=1 and self._loading_frame_key[-1]>=1 else None,self._loading_frame_key[2]))
                    self._invalidate_loading_points(loading_points)
        if self.terrain_arrival is not None and not menu_busy and (not self.animate or not self.damage or self.arrival_progress<0):
            if not self.animate:
                self.terrain_arrival=None;self.invalidate((0,0,self.width,self.height),priority=False)
            else:
                from loading import Arrival
                if self.arrival_plan is None or self.arrival_progress<0:
                    self.arrival_plan=Arrival(self.width,self.height,[self.bounds(w) for w in self.windows if self.shown(w)],
                                              [(w.name,w.desktop,self.bounds(w)) for w in self.windows if w.opened and w.visible and not w.pinned and w.desktop!=self.desktop] if not any(self.shown(w) for w in self.windows) else ())
                elapsed=max(0,(self.clock()-self.terrain_arrival)/self.arrival_duration)
                # Finish each coherent paint, then sample the reveal's real clock.
                # Keep its opening frame without queuing obsolete animation times.
                progress=0 if self.arrival_progress<0 else min(1,elapsed)
                if progress>=1:
                    self.terrain_arrival=None;self.arrival_plan=None;self.arrival_progress=1;self.invalidate((0,0,self.width,self.height),priority=False)
                elif progress!=self.arrival_progress or self.arrival_progress<0:
                    wire=getattr(self.terrain_renderer.completed[1],'wireframe',None) if self.terrain_renderer and self.terrain_renderer.completed else None
                    if self.arrival_progress>=0 and getattr(wire,'bands',None) is not None:
                        from loading import ripple_damage
                        self.damage.update(ripple_damage(wire,self.width,self.arrival_progress,progress,self.arrival_plan))
                        for rect in self.arrival_plan.dirty(self.arrival_progress,progress):
                            if rect!=self.arrival_plan.landscape[0]:self.invalidate(rect,priority=False)
                    else:
                        for rect in self.arrival_plan.dirty(self.arrival_progress,progress):self.invalidate(rect,priority=False)
                    self.arrival_progress=progress
        phase=self._phase_start()
        self.ui_damage.intersection_update(self.damage)
        priority=self.ui_damage if hasattr(self.damage,'take') and self.terrain_arrival is None else sorted(self.ui_damage)
        if self._launcher_dirty:indices=overlay_indices
        elif menu_indices:indices=menu_indices
        elif hasattr(self.damage,'take') and self.terrain_arrival is None:
            indices=self.damage.take(budget,self.ui_damage)
        elif priority:
            background=sorted(self.damage-self.ui_damage);indices=[];u=b=0
            # Normal bounded batches retain the established UI/background share.
            while len(indices)<budget and (u<len(priority) or b<len(background)):
                take=min(48 if b<len(background) else 64,budget-len(indices))
                indices.extend(priority[u:u+take]);u+=min(take,len(priority)-u)
                take=min(64 if u>=len(priority) else 16,budget-len(indices))
                indices.extend(background[b:b+take]);b+=min(take,len(background)-b)
        else:indices=self.arrival_plan.take(self.damage,budget) if self.terrain_arrival is not None and self.arrival_plan else sorted(self.damage)[:budget]
        self._phase_end('damage_selection',phase)
        if not indices:return '',0,0
        if self.terrain_loading:
            key=(self.width,self.height,self.loading_step,self.ascii,self.build_snapshot,self.style,id(self.build_wire),self.build_wire_progress)
            if key!=self._loading_frame_key:
                from loading import frame,prepare,changed_points
                if self._loading_frame is None or len(self._loading_frame)!=self.width*self.height:
                    raw=frame(self.width,self.height,0,self.ascii)
                    shared={value:Cell(*value) for value in set(raw)}
                    self._loading_frame=[shared[value] for value in raw]
                    points=changed_points(self.width,self.height,self.build_wire,self._loading_wire)
                else:
                    points=loading_points if loading_points is not None else changed_points(self.width,self.height,self.build_wire,self._loading_wire,self.loading_step if self.build_wire_progress>=1 and self._loading_frame_key[-1]>=1 else None,self._loading_frame_key[2])
                self._loading_patch.update(y*self.width+x for x,y in points)
                self._loading_frame_key=key;self._loading_wire=self.build_wire
                self._loading_draw=prepare(self.width,self.height,self.loading_step,self.ascii,self.build_snapshot,STYLES[self.style],self.build_wire,self.build_wire_progress)
        else:
            self._loading_frame=None;self._loading_frame_key=None;self._loading_wire=None;self._loading_patch.clear();self._loading_draw=None
        self._frame_windows=tuple(w for w in self.windows if self.shown(w))
        if self.window_fill and self.window_opacity>=1 and not (self.shadow_enabled or self.overview or self.slide or self.animations):
            visible=[]
            for index,w in enumerate(self._frame_windows):
                x,y,width,height=self.bounds(w)
                covered=False
                for upper in self._frame_windows[index+1:]:
                    ux,uy,uw,uh=self.bounds(upper)
                    if upper.layer is None and ux+1<=x and uy+1<=y and ux+uw-1>=x+width and uy+uh-1>=y+height:
                        covered=True;break
                if not covered:visible.append(w)
            self._frame_windows=tuple(visible)
        changes = [];processed=[]
        if self.overview:
            self._overview_frame_groups=tuple(self.overview_windows(d) for d in range(self.desktop_count))
            self._overview_frame_windows=self.exposed_windows()
            self._overview_frame_minis={(w.name,d):self.mini_window(w,d) for d,group in enumerate(self._overview_frame_groups) for w in group}
            self._overview_frame_expose={w.name:self.expose_window(w) for w in self._overview_frame_windows}
            self._overview_rendering=True
        opaque=None
        opaque_base_enabled=not (self.pager or self.pointer_trail and self.pointer_trail.overlay or self.shadow_enabled and self._frame_windows or self.overview or self.slide or self.help_lines or self.settings_lines or self.terrain_loading or self.terrain_arrival or self.screensaver) and (not self._frame_windows or self.window_fill and self.window_opacity>=1) and not (self.drag and (self.resize_mode if self.drag[3] else self.move_mode)=='outline' and not (self._native and self._native.supports_outline(self)))
        layers_supported=self._native is not None and all(self._native.supports_layer(self,w) for w in self._frame_windows)
        opaque_enabled=opaque_base_enabled and all(w.layer is None for w in self._frame_windows) and not self.launcher_lines
        self.render_backend='python'
        self.render_reason='not_loaded' if self._native is None else 'cell_layer' if not layers_supported else 'decorations_or_transparency' if not opaque_base_enabled else None
        mixed_enabled=not (self.overview or self.slide or self.terrain_arrival or self.screensaver or self.pointer_trail and self.pointer_trail.overlay)
        full_native=opaque_base_enabled and layers_supported
        if self._native is not None and (full_native or mixed_enabled):
            try:
                output_parts=[];changed=computed=0
                phase=self._phase_start()
                native_blend=not full_native and self._native.supports_blend(self,self._frame_windows)
                regions=self._native.mixed_regions(self,self._frame_windows) if not (full_native or native_blend) else None
                prepared=self._native.prepare(self,self._frame_windows,STYLES) if full_native or native_blend else None
                self._phase_end('native_setup',phase)
                phase=self._phase_start()
                batch_size=64 if deadline is not None and not self._launcher_dirty else len(indices)
                if full_native and deadline is not None and (getattr(self.backdrop,'native_surface',None) is not None or not self.backdrop) and not any(w.layer for w in self._frame_windows) and hasattr(self._native.lib,'flush_budget'):
                    # A held text-window outline is a small, bounded UI update.
                    # Re-admitting the same plan for 64 cells can cost more than
                    # drawing its whole border; use the static UI's native batch.
                    outline=self._native.supports_outline(self) and not self.background_enabled
                    native_seconds=max(0.,deadline-time.monotonic())
                    # Scene admission can consume the whole outer time budget on
                    # ARM11. Give background-only native work a bounded 3 ms of
                    # progress rather than repeatedly rebuilding the plan for
                    # one 64-cell chunk. Explicit zero budgets and UI stay exact.
                    if self.effect=='flux' and self.background_enabled and not ui_pending and not self.ui_damage:
                        native_seconds=max(native_seconds,min(.003,max_seconds))
                    part,changed,computed=self._native.flush(self,self._frame_windows,indices,STYLES,prepared=prepared,
                        max_seconds=None if outline else native_seconds)
                    output_parts.append(part)
                else:
                    for start in range(0,len(indices),batch_size):
                        batch=indices[start:start+batch_size]
                        if full_native:part,c,n=self._native.flush(self,self._frame_windows,batch,STYLES,prepared=prepared)
                        elif native_blend:part,c,n=self._native.blend_flush(self,batch,prepared)
                        else:part,c,n=self._native.mixed_flush(self,batch,regions)
                        output_parts.append(part);changed+=c;computed+=n
                        if deadline is not None and time.monotonic()>=deadline:break
                self._phase_end('native_draw',phase)
                self.composed_indices=indices[:computed] if self.observe_composition else ()
                painted=indices[:computed]
                self.ui_painted=self.ui_damage.intersects(painted) if isinstance(painted,memoryview) and hasattr(self.ui_damage,'intersects') else any(i in self.ui_damage for i in painted)
                self.ui_damage.difference_update(painted)
                self._launcher_dirty.difference_update(painted)
                self.damage.difference_update(painted);self.composed+=computed
                self._frame_windows=None
                self.render_backend='native' if full_native else 'native_blend' if native_blend else 'native_mixed'
                self.render_reason=None if full_native or native_blend else 'python_loader_surface' if self.terrain_loading else 'python_blend_regions'
                return ''.join(output_parts),changed,computed
            except (ValueError,MemoryError,OSError) as error:
                self.native_error=str(error)
                self.render_reason='native_error'
                self.front=list(self.front);self._native=None
        # Portable transition batches update the retained front in place.
        # Keep native window plans for the return to ordinary composition.
        if opaque_enabled:
            opaque=tuple((self.bounds(w),self.opaque_plane(w,self.bounds(w)[2],self.bounds(w)[3])) for w in reversed(self._frame_windows))
        reveal=None;world_phase=None
        bare_world=not self.pager and not self._frame_windows and not (self.pointer_trail and self.pointer_trail.overlay or self.overview or self.launcher_lines or self.help_lines or self.settings_lines)
        if self.terrain_arrival is not None:
            from loading import land,WorldReveal
            plan=self.arrival_plan
            wire=getattr(self.terrain_renderer.completed[1],'wireframe',{}) if self.terrain_renderer and self.terrain_renderer.completed else None
            world_phase=plan.world(0,0,self.arrival_progress) if plan else self.arrival_progress
            if getattr(wire,'starts',None) is not None:
                reveal=WorldReveal(world_phase,self.arrival_progress,wire)
        for i in indices:
            if processed and len(processed)%64==0 and deadline is not None and time.monotonic()>=deadline:break
            processed.append(i)
            point=(i%self.width,i//self.width)
            background=self.backdrop.get(point,DESKTOP_BLANK)
            if opaque is not None:
                c=background;x,y=point
                for (wx,wy,ww,wh),plane in opaque:
                    if wx<=x<wx+ww and wy<=y<wy+wh:c=plane[y-wy][x-wx];break
                if c.color&FRAME_DEFERRED:c=self.scene_cell(x,y)
            else:c=background if bare_world and not self.terrain_loading else self.cell(*point)
            if self.terrain_arrival is not None:
                if reveal is not None and c==background and point not in wire:
                    c=Cell(*reveal.cell(c,i))
                else:
                    ui_phase=plan.local(*point,self.arrival_progress) if plan else None
                    c=Cell(*land(c,(i*2654435761)&0xffffffff,world_phase,point,
                                 (self.width,self.height),wire,background,ui_phase,self.arrival_progress))
                if plan and point in plan.ghosts:c=Cell(*plan.ghost_cell(c,point,self.arrival_progress,self.ascii))
            char=self.glyphs.cell(c.char,self.ascii)
            if char!=c.char:c=Cell(char,c.color)
            self.composed += 1
            if c != self.front[i]:
                self.front[i] = c
                changes.append((i, c))
        self._overview_rendering=False;self._frame_windows=None
        self.composed_indices=processed if self.observe_composition else ()
        self.damage.difference_update(processed)
        self.ui_painted=any(i in self.ui_damage for i in processed)
        self.ui_damage.difference_update(processed)
        self._launcher_dirty.difference_update(processed)
        changes.sort(key=lambda item:item[0])
        runs = []
        for i, c in changes:
            if runs and i == runs[-1][0]+len(runs[-1][2]) and i//self.width == runs[-1][0]//self.width and c.color == runs[-1][1]:
                runs[-1][2] += c.char
            else:
                runs.append([i, c.color, c.char])
        colors = self._ansi_colors()
        tint = '2;10;10;10'
        shade=round((10 if self.tinted else 18)*(1-self.overview_opacity)+24*self.overview_opacity)
        pane_background=f'2;{shade};{shade};{shade}'
        ox,oy=self.origin
        # Adjacent colored cells already advance the cursor. Avoid an absolute
        # cursor move for every color change in terrain and particle layers.
        pieces=[];cursor=None;last_color=None
        for i,color,text in runs:
            if i!=cursor or i%self.width==0:
                pieces.append(f'\x1b[{i//self.width+oy+1};{i%self.width+ox+1}H')
            if color!=last_color:
                bg=paint_background(color,pane_background if color in (15,16) else '5;232' if color==14 else tint if color>=4 and self.tinted else '5;233')
                pieces.append(f'\x1b[0;{foreground(color,colors)};48;{bg}m')
                last_color=color
            pieces.append(text);cursor=i+len(text)
        output=''.join(pieces)
        return output, len(changes), len(processed)
