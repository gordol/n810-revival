"""Wildlife study form for the existing desktop lifecycle and cell compositor."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import math,time
from geometry import Vec,HeightField,Model,Camera,merge,unit,render,raster
from lighting import environment
from core import Cell
from marmot_art import marmot,ellipsoid,fur_overlay
from eagle_art import eagle,feather_overlay

NAME='Wildlife'
HELP=(('Wildlife',('Tab: marmot / eagle','Space: pause motion','Left / Right: turn camera','Up / Down: view scale','O: foreground obstacle; R: reset','Close-up art study; not a wildlife simulation.')),)


def scene(age,species,yaw=0.,zoom=1.,obstacle=False):
    """Small immutable frame input; geometry and visibility remain canonical."""
    field=HeightField(17,17,Vec(-2.4,0,-2.4),.3,.3,(0.,)*289,'meters')
    env=environment(0)._replace(sun=unit(Vec(-.55,.85,-.65)),ambient=(.58,.55,.48),sky=(86,140,185))
    if species=='marmot':
        phase=age%12
        pose='forage' if phase<4 else 'walk' if phase<8 else 'look'
        progress=(phase-4)/4 if 4<=phase<8 else 0 if phase<4 else 1
        position=Vec(-.11+.22*progress,0,0)
        animal=marmot(position,pose)
        parts=[field.mesh(),animal]
        if obstacle:
            parts.append(ellipsoid(Vec(.13,.055,-.19),(.10,.065,.07),'metal','study:rock'))
        camera=Camera(origin=Vec(-.0576,.384,-1.44),yaw=yaw,elevation=.1,span_x=1.08*zoom,span_y=.864*zoom,focal=0)
        model=Model(field,merge(parts),camera,env.sun,haze_strength=0)
        return model,env,position,pose
    phase=age%9
    pose='glide' if phase<3 else 'bank' if phase<6 else 'upstroke'
    position=Vec(math.sin(age*.4)*.10,0,math.cos(age*.4)*.06)
    animal=eagle(position,pose)
    camera=Camera(origin=Vec(1.2,-1.8,-2),yaw=-.54+yaw,elevation=-.65,span_x=2.6*zoom,span_y=2.1*zoom,focal=0)
    parts=[animal]
    if obstacle:
        # Foreground slab is a deliberate visibility fixture, not terrain art.
        from landscape_detail import box
        parts.append(box(Vec(-.45,-.95,-1.1),.22,.55,.12,'metal','study:occluder'))
    model=Model(field,merge(parts),camera,env.sun,haze_strength=0)
    return model,env,position,pose


def frame(age,species,width,height,yaw=0.,zoom=1.,obstacle=False):
    started=time.perf_counter()
    model,env,position,pose=scene(age,species,yaw,zoom,obstacle)
    model=replace(model,camera=replace(model.camera,span_x=model.camera.span_y*width/(2*height)))
    cells,_=render(model,width,height,environment=env,cast_shadows=False,grid_strength=0)
    # Match render()'s exact cache key; omitting False creates a second entry.
    coverage=raster(model,width,height,False)
    overlay=(fur_overlay if species=='marmot' else feather_overlay)(model,coverage,cells,width,height,origin=position)
    cells.update(overlay)
    return tuple(Cell(*cells[x,y]) for y in range(height) for x in range(width)),dict(species=species,pose=pose,age=age,seconds=time.perf_counter()-started,viewport=(width,height),position=position)


class Wildlife:
    """One render worker; stale controls/size results cannot replace newer views."""
    layer_only=True
    def __init__(self,host,*,clock=time.monotonic,render_frame=frame):
        self.host=host;self.clock=clock;self.render_frame=render_frame
        self.name=NAME;self.help=HELP;self.view=self;self.width=96;self.height=32
        self.species='marmot';self.yaw=0.;self.zoom=1.;self.obstacle=False;self.playing=True
        self.age=0.;self.last_clock=clock();self.next_poll=0.;self.revision=0
        self.pool=None;self.pending=None;self.pending_key=None;self._layer=None
        self.closed=False;self.opened=False;self.was_active=False;self.dirty=True;self.error=''
        self.last_result=None;self.last_size=None;self.stats=dict(submitted=0,accepted=0,discarded=0)
    def _sync(self):
        now=self.clock()
        try:
            w=self.host.window(self.name)
            active=self.opened and not self.closed and w.opened and self.host.shown(w) and not w.rolled and self.host.focus==self.name
        except (KeyError,StopIteration):active=False
        if active and self.was_active and self.playing:self.age+=max(0,now-self.last_clock)
        self.last_clock=now;self.was_active=active
        return active
    def open(self):
        if self.closed:return False
        self.opened=True;self.last_clock=self.clock();self.dirty=True
        return True
    def set_active(self,active):
        self._sync()
        if not active:self.was_active=False
    def on_focus(self,*args):self._sync()
    def on_visibility(self,*args):self._sync()
    def on_close(self):
        self._sync();self.opened=False;self.was_active=False
    def poll_interval(self):
        return .05 if self._sync() and (self.pending or self.dirty or self.playing) else None
    def key(self,key):
        if not self._sync():return False
        if key in ('\t','tab'):self.species='eagle' if self.species=='marmot' else 'marmot';self.age=0
        elif key in (' ','space'):self.playing=not self.playing
        elif key=='left':self.yaw-=.08
        elif key=='right':self.yaw+=.08
        elif key=='up':self.zoom=max(.6,self.zoom*.9)
        elif key=='down':self.zoom=min(5.,self.zoom/ .9)
        elif key in ('o','O'):self.obstacle=not self.obstacle
        elif key in ('r','R'):self.yaw=0;self.zoom=1;self.age=0;self.obstacle=False
        else:return False
        self.revision+=1;self.dirty=True;self.next_poll=0;self.error=''
        return True
    def _size(self):return max(1,min(120,self.width)),max(1,min(48,self.height-2))
    def poll(self):
        if not self._sync():return None
        width,height=self._size()
        if self.last_size!=(self.width,self.height):
            self.last_size=(self.width,self.height);self.dirty=True;self._layer=None
        key=(self.revision,width,height)
        if self.pending and self.pending.done():
            job=self.pending;job_key=self.pending_key;self.pending=None
            try:
                cells,details=job.result()
                if job_key==key:
                    self._layer=((self.width-width)//2,1,width,height,cells)
                    self.last_result=details;self.stats['accepted']+=1
                    self.dirty=False;self.next_poll=self.clock()+.12
                else:self.stats['discarded']+=1
            except Exception as error:
                self.error=str(error);self.dirty=False;self.next_poll=float('inf')
        if self.pending is None and not self.error and (self.dirty or self.playing and self.clock()>=self.next_poll):
            if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='wildlife')
            age=round(self.age*8)/8
            self.pending_key=key
            self.pending=self.pool.submit(self.render_frame,age,self.species,width,height,self.yaw,self.zoom,self.obstacle)
            self.stats['submitted']+=1
        return self.last_result
    def lines(self):
        self.poll()
        top=f'{self.species.capitalize()} | '+('playing' if self.playing else 'paused')+f' | view {self.zoom:.1f}x'
        if self.error:top='Render error: '+self.error
        footer='Tab animal  Space pause  arrows view  O obstacle  R reset'
        return tuple([top[:self.width]]+['']*max(0,self.height-2)+[footer[:self.width]])
    def spans(self):return ()
    def layer(self):return self._layer
    def help_pages(self):return HELP
    def close(self):
        self.closed=True;self.opened=False;self._layer=None
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
        self.pool=None;self.pending=None
