"""Optional bounded phase counters. No screen contents, event log or worker."""
from runtime_codec import pack
import os
import time
from pathlib import Path


def scene_state(host):
    """Actual runtime selection, separately from an obsolete worker request."""
    renderer=host.terrain_renderer
    request=renderer.requested if renderer else None
    nature=request[10] if request and len(request)>10 else None
    return dict(active_effect=host.effect,animate=host.animate,background_enabled=host.background_enabled,
                background_async=getattr(host,'background_async',False),
                worker_kind=getattr(renderer,'requested_mode',None),target_kind=getattr(renderer,'mode',None),
                background_step=host.background_step,effect_generation=host.effect_generation,
                terrain_job_wanted=host.background_enabled and host.effect=='terrain',
                terrain_cancel_requested=renderer.trace.stopped.is_set() if renderer else False,
                terrain_request_nature=nature._asdict() if hasattr(nature,'_asdict') else None,
                preferences={key:getattr(host,key) for key in ('season','show_animals','show_flowers','show_foliage','scene_seed','nature_epoch','nature_rate','light_mode')},
                scenery=dict(host.scenery),menu_active=bool(host.launcher_lines),
                menu_pending_cells=len(getattr(host,'_launcher_dirty',())),ui_damage_cells=len(host.ui_damage))


def scenery_state(host):
    """Read the app's existing state; never request, poll, or build a scene."""
    form=getattr(host,'app_forms',{}).get('Scenery')
    form=getattr(form,'owner',form)
    if form is None:return None
    renderer=form.renderer;state=form.scene;window=host.window('Scenery')
    def request(key):
        if key is None:return None
        nature=key[10] if len(key)>10 else None
        return dict(view=list(key[:10]),nature=nature._asdict() if hasattr(nature,'_asdict') else None)
    layer=form.layer()
    return dict(opened=window.opened,visible=host.shown(window),rolled=window.rolled,
                bounds=list(host.bounds(window)),form_viewport=[form.width,form.height],
                layer_geometry=list(layer[:4]) if layer is not None else None,
                layer_cell_count=len(layer[4]) if layer is not None else 0,
                controls_visible=form.controls_visible,scenery=dict(state.scenery),
                preferences={key:getattr(state,key) for key in (*form.appearance,'nature_epoch','nature_rate','static_world_age')},
                worker=renderer.trace.progress(),pending=renderer.pending is not None,
                future_done=renderer.pending.done() if renderer.pending is not None else None,
                requested=request(renderer.requested),
                completed=request(renderer.completed[0]) if renderer.completed is not None else None)


REGISTERED_STATS=('updates','geometry_seconds','surface_seconds','damage_seconds',
                  'cell_pack_seconds','resize_seconds','preparation_seconds',
                  'failed_jobs','discarded_resize_frames','last_frame_age_at_publish_ms',
                  'last_scene_triangles','last_world_marmot','forest_overlay_cells',
                  'experience_seconds','secondary_view_seconds')


def registered_state(host):
    """Bounded snapshots of already-created owners; no factory or polling."""
    rows=[]
    for form in getattr(host,'app_forms',{}).values():
        owner=getattr(form,'owner',None);entry=getattr(form,'entry',None)
        if owner is None or entry is None:continue
        window=host.window(entry.title);stats=getattr(owner,'stats',{})
        trace=getattr(owner,'trace',None);worker=getattr(owner,'worker',None)
        layer=window.layer
        rows.append(dict(id=entry.id,title=entry.title,opened=window.opened,
                         visible=host.shown(window),rolled=window.rolled,
                         focused=host.focus==entry.title,bounds=list(host.bounds(window)),
                         layer_geometry=list(layer[:4]) if layer is not None else None,
                         layer_cell_count=len(layer[4]) if layer is not None else 0,
                         render_dimensions=getattr(owner,'render_dimensions',None),
                         sequence=getattr(owner,'sequence',None),input_sequence=getattr(owner,'input_sequence',None),
                         pending_input_count=len(getattr(owner,'pending_inputs',())),
                         held_keys=sorted(getattr(getattr(owner,'held_motion',None),'held',())),
                         pose={name:getattr(owner,name,None) for name in ('x','z','yaw','pitch')},
                         latency_sample_count=len(getattr(owner,'latencies',())),
                         worker_pending=getattr(worker,'pending',0) if worker is not None else 0,
                         ready=getattr(owner,'ready',None) is not None,
                         worker=trace.progress() if trace is not None else None,
                         stats={key:stats[key] for key in REGISTERED_STATS
                                if isinstance(stats,dict) and isinstance(stats.get(key),(int,float,bool))}))
        if len(rows)>=16:break
    return rows


def composition_state(host):
    """Expose actual fast-path inputs rather than guessing from saved settings."""
    return dict(window_fill=host.window_fill,window_opacity=host.window_opacity,
                terminal_opacity=host.terminal_opacity,window_shadows=host.shadow_enabled,
                pager=host.pager is not None,overview=host.overview,slide=bool(host.slide),
                help_overlay=bool(host.help_lines),settings_overlay=bool(host.settings_lines),
                terrain_loading=host.terrain_loading,terrain_arrival=host.terrain_arrival is not None,
                screensaver=host.screensaver,pointer_overlay=bool(host.pointer_trail and host.pointer_trail.overlay),
                camera_motion=host.camera_motion is not None,
                visible_layers=[dict(name=w.name,geometry=list(w.layer[:4]),terminal=w.name in host.terminal_layers)
                                for w in host.windows if host.shown(w) and w.layer is not None][:16])


def enable_renderer_timing(host):
    """Opt in only for already-created renderer instances; never create owners."""
    from itertools import islice
    for renderer in islice(getattr(host,'app_renderers',()),64):
        if 'timing_enabled' in getattr(renderer,'__dict__',{}):renderer.timing_enabled=True


def renderer_timings(host):
    """Bounded detached worker counters, without requests or private view keys."""
    from itertools import islice
    rows=[]
    for index,renderer in enumerate(islice(getattr(host,'app_renderers',()),64)):
        snapshot=getattr(type(renderer),'timing_snapshot',None)
        if snapshot is not None and getattr(renderer,'timing_enabled',False):
            rows.append(dict(index=index,type=type(renderer).__name__,timing=snapshot(renderer)))
    return rows


def map_cache_state(host):
    """Read existing worker cache selection; never poll, create, or prepare."""
    from itertools import islice
    rows=[]
    for index,renderer in enumerate(islice(getattr(host,'app_renderers',()),64)):
        engine=getattr(renderer,'__dict__',{}).get('engine')
        stats=getattr(engine,'__dict__',{}).get('stats')
        if not isinstance(stats,dict):continue
        cache=stats.get('cache')
        if cache not in ('prepared','ram','cold'):continue
        rows.append(dict(index=index,cache=cache))
    return rows


def pending_model_renderers(host):
    """Inspect bounded existing owner references, never invoke app methods."""
    from itertools import islice
    from concurrent.futures import Future
    owners={}
    for name,form in islice(getattr(host,'app_forms',{}).items(),64):
        fields=getattr(form,'__dict__',{})
        owner=fields.get('owner')
        for value in (form,owner):
            if value is None:continue
            renderer=getattr(value,'__dict__',{}).get('renderer')
            if renderer is not None:owners.setdefault(id(renderer),[]).append(name)
    result=[]
    for index,renderer in enumerate(islice(getattr(host,'app_renderers',()),64)):
        pending=getattr(renderer,'__dict__',{}).get('pending')
        active=bool(pending) if isinstance(pending,(bool,int)) else pending is not None
        if not active:continue
        names=list(dict.fromkeys(owners.get(id(renderer),())))
        visible=[]
        for name in names:
            try:visible.append(host.shown(host.window(name)))
            except (KeyError,ValueError):visible.append(None)
        future=pending if isinstance(pending,Future) else pending[1] if type(pending) is tuple and len(pending)==2 and isinstance(pending[1],Future) else None
        result.append(dict(index=index,type=type(renderer).__name__,owners=names,visible=visible,
                           done=future.done() if future is not None else None))
    return result


class Metrics:
    def __init__(self):
        self.started=time.monotonic();self.phases={};self.counts={}
        self.input_started=None
        self.metadata={}
        self.render=RenderStats()
        self.next_live=0.
        self.input_context=[]
        self.model_work={};self.model_schedule={}

    def add(self,name,value=1):
        self.counts[name]=self.counts.get(name,0)+value

    def begin(self):
        return time.monotonic(),time.thread_time()

    def end(self,name,start):
        if start is None:return
        wall=time.monotonic()-start[0];cpu=time.thread_time()-start[1]
        phase=self.phases.setdefault(name,dict(calls=0,wall_seconds=0.,cpu_seconds=0.,max_wall_seconds=0.))
        phase['calls']+=1;phase['wall_seconds']+=wall;phase['cpu_seconds']+=cpu
        phase['max_wall_seconds']=max(phase['max_wall_seconds'],wall)
        phase['last_wall_seconds']=wall

    def model_call(self,owner,stage,fn,*args):
        """Opt-in bounded model timing; no output, factories or extra polls."""
        allowed={'poll','interval','lines','spans','layer','content','update','bind','capture','observe','save','present','set_active'}
        stage=stage if stage in allowed else 'other'
        key=str(owner)[:80]+':'+stage
        if key not in self.model_work and len(self.model_work)>=128:key='overflow:'+stage
        started=self.begin()
        try:return fn(*args)
        finally:
            wall=time.monotonic()-started[0];cpu=time.thread_time()-started[1]
            row=self.model_work.setdefault(key,dict(calls=0,wall_seconds=0.,cpu_seconds=0.,max_wall_seconds=0.))
            row['calls']+=1;row['wall_seconds']+=wall;row['cpu_seconds']+=cpu
            row['max_wall_seconds']=max(row['max_wall_seconds'],wall);row['last_wall_seconds']=wall

    def save_live(self,path,host,engine=None,now=None,presentation=None):
        """Small opt-in progress receipt while a first scene is still building."""
        now=time.monotonic() if now is None else now
        if now<self.next_live:return False
        self.next_live=now+2
        started=self.begin()
        try:return self._save_live(path,host,engine,now,presentation)
        finally:self.end('metrics_live_report',started)

    def _save_live(self,path,host,engine,now,presentation):
        renderer=host.terrain_renderer;trace=renderer.trace if renderer else None
        result=dict(version=1,elapsed_seconds=now-self.started,main_thread_cpu_seconds=time.thread_time(),engine=engine,
                    viewport=[host.width,host.height],background_enabled=host.background_enabled,
                    terrain_loading=host.terrain_loading,damage_cells=len(host.damage),last_backend=host.render_backend,
                    scene_request=list(renderer.requested[:10]) if renderer and renderer.requested else None,
                    future_done=renderer.pending.done() if renderer and renderer.pending else None,
                    worker=trace.progress() if trace else None,
                    stages=[dict(kind=e.kind,count=e.count) for e in trace.snapshot()] if trace else [],
                    geometry_compute=__import__('sys').modules['geometry_compute'].status() if 'geometry_compute' in __import__('sys').modules else None,
                    last_compose_seconds=self.phases.get('host_compose',{}).get('last_wall_seconds'),
                    completed_scene_output=self.render.summary())
        result['main_phase']=self.phases.get('main_phase',{})
        result['compose_phases']=getattr(host,'compose_phases',{})
        result['paint_batch']=getattr(host,'paint_batch',None)
        result['effective_scene']=scene_state(host)
        result['scenery_window']=scenery_state(host)
        result['composition_controls']=composition_state(host)
        result['registered_windows']=registered_state(host)
        result['app_control_path']=getattr(host,'control_path',None)
        result['model_work']=self.model_work
        result['model_schedule']=self.model_schedule
        result['map_caches']=map_cache_state(host)
        result['renderer_timings']=renderer_timings(host)
        result['input_source']=getattr(host,'input_status',None)
        result['session_work']=dict(getattr(host,'session_stats',{}))
        result['session_error']=getattr(host,'session_error',None)
        result['main_phases']={key:self.phases.get(key,{}) for key in ('input_handlers','model_layout','model_header','model_sources','model_apps','model_panel','metrics_live_report','host_compose','terminal_write')}
        result['timing_scope']='host_compose excludes periodic live snapshot/write; metrics_live_report records completed snapshot/write calls. Main phases are cumulative counters, not matched-pass sums.'
        result['presentation']=presentation.stats() if presentation is not None else None
        path=Path(path);temporary=path.with_name(path.name+'.tmp')
        try:
            with temporary.open('wb') as output:output.write(pack(result))
            os.replace(temporary,path)
        finally:
            try:temporary.unlink()
            except FileNotFoundError:pass
        return True

    def call(self,name,fn,*args,**kwargs):
        start=self.begin()
        try:return fn(*args,**kwargs)
        finally:self.end(name,start)

    def input(self,terrain_pending=None):
        self.add('input_batches')
        if len(self.input_context)<128:
            self.input_context.append(dict(elapsed_seconds=time.monotonic()-self.started,terrain_pending=terrain_pending))
        if self.input_started is None:self.input_started=self.begin()
        else:self.add('input_batches_coalesced')

    def wrote(self):
        # First nonempty host presentation after input, not child acknowledgement
        # or proof of physical display completion. Several inputs may coalesce.
        if self.input_started is not None:
            if self.input_context:self.input_context[-1]['next_output_seconds']=time.monotonic()-self.input_started[0]
            self.end('input_dispatch_to_next_output',self.input_started)
            self.input_started=None

    def save(self,path,terminals=()):
        result=dict(version=1,elapsed_seconds=time.monotonic()-self.started,
                    renderer=self.metadata,completed_scene_output=self.render.summary(),
                    phases=self.phases,counts=self.counts,model_work=self.model_work,model_schedule=self.model_schedule,
                    input_context=self.input_context,
                    input_waiting_for_output=self.input_started is not None,
                    terminals=[dict(name=t.name,exit_status=getattr(t,'exit_status',None),received_bytes=t.received,patched_cells=t.patched,
                                    ready_calls=t.ready_calls,max_ready_ms=t.max_ready_ms,
                                    size=t.size) for t in terminals])
        path=Path(path);temporary=path.with_name(path.name+'.tmp')
        try:
            with temporary.open('wb') as output:output.write(pack(result))
            os.replace(temporary,path)
        finally:
            try:temporary.unlink()
            except FileNotFoundError:pass


class RenderStats:
    """Constant-space completed scene output counters; debug-only work excluded."""
    def __init__(self,clock=time.monotonic):
        self.clock=clock;self.started=self.sampled=clock();self.frames=0
        self.compose=self.write=0.;self.batches=self.bytes=0;self.pending=False
        self.previous=(0,0.,0.,0,0);self.backend='unmeasured';self.reason=None
        self.generated=self.effect_completed=self.superseded=0
        self.seen_effect=self.pending_effect=self.last_effect=None
        self.previous_effects=0
        self.current=dict(effect_fps=0.,fps=0.,compose_ms=0.,write_ms=0.,bytes_per_second=0.,frames=0,sample_seconds=0.)

    def batch(self,scene,complete,emitted,compose,write,backend,reason,effect_id=None):
        if effect_id is not None and effect_id!=self.seen_effect:
            self.generated+=1
            if self.pending_effect is not None:self.superseded+=1
            self.seen_effect=self.pending_effect=effect_id
        self.pending=self.pending or scene
        if self.pending:
            self.compose+=compose;self.write+=write;self.batches+=1;self.bytes+=emitted
            self.backend=backend;self.reason=reason
        if self.pending and complete and emitted:
            self.frames+=1;self.pending=False
            if effect_id is not None and effect_id!=self.last_effect:
                self.effect_completed+=1;self.last_effect=effect_id;self.pending_effect=None
        elif complete and not emitted:self.pending=False

    def read(self):
        now=self.clock();elapsed=now-self.sampled
        if elapsed>=1:
            values=(self.frames,self.compose,self.write,self.batches,self.bytes)
            frames,compose,write,batches,size=(a-b for a,b in zip(values,self.previous))
            self.current=dict(effect_fps=(self.effect_completed-self.previous_effects)/elapsed,fps=frames/elapsed,compose_ms=1000*compose/max(1,batches),write_ms=1000*write/max(1,batches),bytes_per_second=size/elapsed,frames=self.frames,sample_seconds=elapsed)
            self.previous=values;self.sampled=now;self.previous_effects=self.effect_completed
        return self.current

    def summary(self):
        elapsed=max(0.,self.clock()-self.started)
        return dict(self.read(),elapsed_seconds=elapsed,total_frames=self.frames,effect_generated=self.generated,effect_completed=self.effect_completed,
                    effect_superseded=self.superseded,last_effect_id=self.last_effect,
                    fps_overall=self.frames/elapsed if elapsed else 0.,
                    total_output_bytes=self.bytes,total_compose_seconds=self.compose,
                    total_write_seconds=self.write,total_batches=self.batches)


class RenderDebug:
    """Native window; one visible refresh per second, no worker or disk I/O."""
    def __init__(self,stats,visible,details,clock=time.monotonic,host=None):
        self.stats=stats;self.visible=visible;self.details=details;self.clock=clock;self.due=0;self.cached=();self.host=host
    def _change(self,values):
        if self.host is None:return
        original=getattr(self.host,'render_debug_preferences',None)
        if original is None:self.host.render_debug_preferences=original={}
        for key,value in values.items():
            original.setdefault(key,getattr(self.host,key));setattr(self.host,key,value)
        self.host.invalidate((0,0,self.host.width,self.host.height));self.cached=();self.due=0
    def close(self):
        if self.host is None:return
        original=getattr(self.host,'render_debug_preferences',{})
        for key,value in original.items():setattr(self.host,key,value)
        if original:self.host.invalidate((0,0,self.host.width,self.host.height))
        self.host.render_debug_preferences={};self.cached=();self.due=0
    def set_active(self,active):
        if not active and self.host is not None and getattr(self.host,'render_debug_preferences',{}):self.close()
    def key(self,key):
        if self.host is None:return False
        if key=='s':self._change({'shadow_enabled':not self.host.shadow_enabled})
        elif key=='o':
            original=getattr(self.host,'render_debug_preferences',{})
            saved=original.get('window_opacity',self.host.window_opacity)
            self._change({'window_opacity':(saved if saved<1 else .88) if self.host.window_opacity>=1 else 1.})
        elif key=='n':self._change({'shadow_enabled':False,'window_opacity':1.})
        elif key=='r':self.close()
        else:return False
        return True
    def pointer(self,x,y,width,button,released=False):
        if button==0 and not released and 0<=y<4:return self.key(('s','o','n','r')[y])
        return False
    def poll_interval(self):return max(.01,self.due-self.clock()) if self.visible() else None
    def lines(self):
        if self.cached and self.clock()<self.due:return self.cached
        self.due=self.clock()+1
        stats=self.stats()
        if stats is None:return ('Open this window from Menu to start measuring.',)
        report=stats.read();details=self.details();width,height,schedule,native,error=details[:5]
        numeric=details[5] if len(details)>5 else {}
        self.cached=(
            f"Completed scene renders: {report['fps']:.2f}/s"+('  idle' if not report['fps'] else ''),
            f"Unique effect frames: {report['effect_fps']:.2f}/s | display FPS unknown",
            f"Compose {report['compose_ms']:.2f} ms/draw pass | write {report['write_ms']:.2f} ms/pass",
            f"Output {report['bytes_per_second']/1024:.1f} KiB/s | total {report['frames']} frames",
            f'Viewport {width}x{height} | background schedule {schedule}',
            f'Compositor {stats.backend} | native loaded {native}',
            'Numeric: '+str(numeric.get('backend','not measured'))+' / '+str(numeric.get('reason') or 'accepted'),
            'Fallback: '+str(stats.reason or 'none'),
            'Native error: '+str(error or 'none'),
            'Debug window area/refresh excluded from scene FPS.',
            f"Sample {report['sample_seconds']:.1f}s; averages include partial batches.")
        if self.host is not None:
            self.cached=(f"[s] Window shadows: {'on' if self.host.shadow_enabled else 'off'}",
                         f"[o] Window opacity: {self.host.window_opacity:.0%} (toggle opaque)",
                         '[n] Test shadows off + opaque windows',
                         '[r] Restore | temporary; closing restores')+self.cached
        return self.cached
