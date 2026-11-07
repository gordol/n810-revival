#!/usr/bin/env python3
"""Framework-native room proof in the existing Host; no Doom port/filter."""
import argparse, hashlib, json, math, os, resource, select, sys, termios, time, tty
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT))
from core import Host,Window,Cell,Inbox
from held_motion import HeldMotion
from build_trace import Trace
from frame_job import Request,prepare
from input import Input
from terminal import measure,Presentation
from geometry import raster,render
from room import scene,portal_scene,walkthrough_pose,portal_materials
from surface_renderer import GlyphRenderer,ToneRenderer
from coverage_adapter import frame
from profiles import ROOM

NAME='Surface room'
HELP=(('Explore',('W/S or Up/Down: walk','A/D: strafe; Left/Right: turn','Q or Ctrl-C: exit this proof','Mouse: shared window controls',
    'Room/corridor and one moving prop; no combat.')),)


class SurfaceRoom:
    """Normal lifetime owner publishing cells through Host.layer_patch."""
    @property
    def layer_only(self):return not self.input_diagnostic
    def __init__(self,host,*,clock=time.monotonic,implementation=None,portal=False,walkthrough=False,dense=False,rift=False,asynchronous=True,outdoors=False,name=NAME,world_detail=True,approved_forest=False,frame_backend=None):
        self.frame_backend=frame_backend
        self.materials=portal_materials() if portal or rift else ROOM
        self.input_diagnostic=False;self.key_event_reports=0;self.input_status='No press/release reports received.'
        self._diagnostic_lines=None
        self.last_scene_requested_at=None
        self.approved_forest=approved_forest;self.world_detail=world_detail;self.outdoors=outdoors;self.pitch=-.04 if outdoors else 0.
        self.error='';self.asynchronous=asynchronous;self.worker=None;self.trace=Trace();self.ready=None
        self.rift=rift;self.last_motion=clock();self.teleports=0
        self.portal=portal;self.walkthrough=walkthrough;self.dense=dense
        self.host=host;self.clock=clock;self.name=name;self.view=self;self.help=HELP
        self.help+=(("Held movement",("With hardware key releases, combine walk, strafe and turn.","I/K look up/down. Other input sources keep keypress controls.","V: input diagnostic / room. The diagnostic skips new scene renders.")),)
        if outdoors:self.help+=(("Rainier walk",("I/K: look up/down. Ground follows actual terrain in metres.","Fictional ruins and metre-scale marmot/eagle; no combat.")),)
        if rift:self.help+=(("What is left?",("Stillness dissolves the room into intro wire and glow.","Move to restore it; cross the far golden aperture to teleport.","One reflected camera view, no recursive mirrors; no combat/audio.")),)
        self.implementation=implementation or GlyphRenderer(max_cells=12000 if dense else 6000,max_glyphs=3600 if dense else 1600)
        self.closed=False;self.started=clock();self.next_poll=0;self.paused_at=None;self.paused_total=0
        self.held_motion=HeldMotion(self.started)
        self.x=0.;self.z=0. if outdoors else -600.;self.yaw=0.;self.previous=();self.dimensions=None;self.render_dimensions=None;self.sequence=0;self.input_sequence=0
        self.last_frame=None;self.pending_inputs=[];self.latencies=[]
        self.stats=dict(updates=0,geometry_seconds=0.,surface_seconds=0.,damage_seconds=0.)
    def open(self):
        if self.closed:return False
        self.error='';self.host.activate(self.name);self.next_poll=0;return True
    def _active(self):
        w=self.host.window(self.name)
        return not self.closed and w.opened and self.host.shown(w) and not w.rolled and self.host.focus==self.name
    def _sync(self):
        now=self.clock();active=self._active()
        if not active:
            self.cancel_keys(now)
            if self.paused_at is None:self.paused_at=now
        elif active and self.paused_at is not None:self.paused_total+=now-self.paused_at;self.last_motion+=now-self.paused_at;self.paused_at=None
        return active
    def poll_interval(self):return (.01 if self.worker and self.worker.pending else 1/35) if self._sync() and (not self.error or self.input_diagnostic) else None
    def cancel_keys(self,now=None):
        if self.held_motion.held:self.input_status='Held keys cleared.'
        self.held_motion.clear(self.clock() if now is None else now)
    def _translate(self,forward,sideways,distance,heading=None):
        heading=self.yaw if heading is None else heading
        x=self.x+(math.sin(heading)*forward+math.cos(heading)*sideways)*distance
        z=self.z+(math.cos(heading)*forward-math.sin(heading)*sideways)*distance
        x=max(-1100,min(1100,x));z=max(-900,min(6600 if self.portal or self.rift else 5300,z))
        if not (self.portal or self.rift or self.outdoors) and 3370<z<3900 and abs(x)>300:z=min(self.z,3370)
        if not (self.portal or self.rift or self.outdoors) and z>=3900:x=max(-300,min(300,x))
        if self.rift:
            from room import teleport_step
            x,z,self.yaw,teleported=teleport_step(self.x,self.z,x,z,self.yaw)
            self.teleports+=int(teleported)
        self.x,self.z=x,z
    def _apply_motion(self,step,now):
        if not step.seconds or not any(step[1:]):return
        turn=step.turn*step.seconds
        heading=self.yaw+turn*.5;self.yaw+=turn
        self._translate(step.forward,step.strafe,step.seconds*(3.2 if self.outdoors else 380.),heading)
        self.pitch=max(-1,min(1,self.pitch+step.look*step.seconds*.8))
        self.last_motion=now;self.next_poll=0
    def _leave_walkthrough(self,now):
        if not self.walkthrough:return
        if self.rift:
            from experience import scripted_experience
            self.x,self.z,self.yaw,*_=scripted_experience((now-self.started-self.paused_total)%20)
        else:self.x,self.z,self.yaw=walkthrough_pose((now-self.started-self.paused_total)/24)
        self.walkthrough=False
    def key_event(self,key,kind,now):
        if not self._sync() or self.error and not self.input_diagnostic:return False
        was_held=key in self.held_motion.held
        if kind=='press' and key in self.held_motion.bindings:self._leave_walkthrough(now)
        step=self.held_motion.event(key,kind,now)
        if step is None:return False
        self.key_event_reports+=1;self.input_status=key+' '+kind
        self._apply_motion(step,now)
        edge=(kind=='press' and not was_held) or (kind=='release' and was_held)
        if edge:
            self.input_sequence+=1;self.pending_inputs.append((self.input_sequence,now));self.next_poll=0
        return True
    def key(self,key,now=None):
        if not self._sync():return False
        if key.lower()=='v':
            self.input_diagnostic=not self.input_diagnostic;self.next_poll=0;self._diagnostic_lines=None
            if self.input_diagnostic:self._publish_diagnostic()
            else:self.dimensions=None
            return True
        if self.error:
            if key.lower()=='r':self.error='';self.next_poll=0;return True
            return False
        now=self.clock() if now is None else now
        if self.walkthrough and key in ('left','right','w','up','s','down','a','d'):
            self._leave_walkthrough(now)
        if self.outdoors and key in ('i','k'):
            self.pitch=max(-1,min(1,self.pitch+(-.05 if key=='i' else .05)))
        elif key in ('left','right'):self.yaw+=(-.065 if key=='left' else .065)
        elif key in ('w','up','s','down','a','d'):
            forward=1 if key in ('w','up') else -1 if key in ('s','down') else 0
            sideways=-1 if key=='a' else 1 if key=='d' else 0
            self._translate(forward,sideways,.8 if self.outdoors else 95)
        else:return False
        self.input_status='Terminal keypress: '+key+' (no release report).'
        self.last_motion=now
        self.input_sequence+=1;self.pending_inputs.append((self.input_sequence,now));self.next_poll=0
        return True
    def _request(self,now):
        w=self.host.window(self.name);body_width=max(1,w.w-2);body_height=max(1,w.h-2)
        budget=12000 if self.dense else 6000
        scale=min(1,1024/body_width,512/body_height,math.sqrt(budget/(body_width*body_height)))
        width=max(1,int(body_width*scale));height=max(1,int(body_height*scale))
        age=now-self.started-self.paused_total
        x,z,yaw=walkthrough_pose(age/24) if self.walkthrough else (self.x,self.z,self.yaw)
        idle=now-self.last_motion
        if self.rift and self.walkthrough:
            from experience import scripted_experience
            x,z,yaw,idle,_=scripted_experience(age%20)
        return Request(body_width,body_height,width,height,age,x,z,yaw,idle,self.rift,self.portal,self.input_sequence,now,self.outdoors,self.pitch,self.world_detail,self.approved_forest)
    def _prepare(self,request):
        backend=self.frame_backend
        if backend is not None and backend.supports(request,self.implementation,self.materials):
            return backend.prepare(request,self.implementation,self.materials)
        return prepare(request,self.implementation,self.materials)
    def _publish(self,result):
        request,cells,stats=result
        width,height=request.body_width,request.body_height
        self.render_dimensions=(request.width,request.height)
        for key,value in stats.items():
            if key=='reality':self.reality=value
            elif key.startswith('last_'):self.stats[key]=value
            else:self.stats[key]=self.stats.get(key,0)+value
        t=time.perf_counter();changed=None if self.dimensions!=(width,height) else [i for i,v in enumerate(cells) if v!=self.previous[i]]
        self.host.layer_patch(self.name,(0,0,width,height,cells),changed)
        self.stats['damage_seconds']+=time.perf_counter()-t;self.stats['updates']+=1
        self.previous=cells;self.dimensions=(width,height);self.sequence+=1
        self.last_frame=(self.sequence,request.input_sequence)
        self.last_scene_requested_at=request.requested_at
        self.stats['last_frame_age_at_publish_ms']=(self.clock()-request.requested_at)*1000
        return self.last_frame
    def _failure(self,error):
        self.cancel_keys()
        self.error=type(error).__name__+': '+str(error)[:700]
        self.ready=None;self.stats['failed_jobs']=self.stats.get('failed_jobs',0)+1
        self.host.content(self.name,('render-error',self.error),self.lines(),layer=None)
    def poll(self,force=False):
        now=self.clock()
        if not self._sync() or self.error and not self.input_diagnostic:return None
        self._apply_motion(self.held_motion.advance(now),now)
        if self.worker:
            for ok,result in self.worker.drain():
                if self.input_diagnostic:continue
                if not ok:self._failure(result);return None
                self.ready=result
        if self.input_diagnostic:
            self.ready=None
            if force or now>=self.next_poll:return self._publish_diagnostic()
            return None
        if self.ready is not None:
            window=self.host.window(self.name)
            r=self.ready[0]
            if (r.body_width,r.body_height)!=(max(1,window.w-2),max(1,window.h-2)):
                self.stats['discarded_resize_frames']=self.stats.get('discarded_resize_frames',0)+1;self.ready=None
            elif not self.host.damage or self.dimensions is None:
                result=self.ready;self.ready=None;return self._publish(result)
        # Start the first detached scene while Host paints its initial damage.
        # A completed first plane may replace the empty body before that damage
        # drains; later frames retain the coherent presentation boundary.
        if self.ready is not None or self.host.damage and self.dimensions is not None and not force:return None
        if self.worker and self.worker.pending:return None
        if not force and now<self.next_poll:return None
        request=self._request(now);self.next_poll=now+1/35
        if not self.asynchronous or force:
            try:return self._publish(self._prepare(request))
            except Exception as error:self._failure(error);return None
        if self.worker is None:self.worker=Inbox(capacity=1)
        self.worker.submit(lambda:self.trace.run(self._prepare,request))
        return None
    def presented(self,now=None):
        now=self.clock() if now is None else now
        if not self.last_frame:return
        acknowledged=self.last_frame[1]
        for sequence,started in self.pending_inputs:
            if sequence<=acknowledged:self.latencies.append((now-started)*1000)
        self.pending_inputs=[p for p in self.pending_inputs if p[0]>acknowledged]
    def lines(self):
        if self.input_diagnostic:
            forward,strafe,turn,look=self.held_motion.axes()
            pending=self.worker.pending if self.worker is not None else 0
            captured=self.last_frame[1] if self.last_frame else 0
            age='none completed' if self.last_scene_requested_at is None else f'{max(0,self.clock()-self.last_scene_requested_at):.2f}s since request'
            status=getattr(self.host,'input_status',{})
            hardware=status.get('hardware') or {};terminal=status.get('terminal') or {}
            trouter=terminal.get('router') or {}
            motion=terminal.get('last_motion') or {}
            def recent(source):
                return ', '.join((str(e.get('key',''))+' '+str(e.get('kind',''))+' routed='+str(e.get('routed','-'))).strip() for e in source.get('events',())[-2:])[:100] or '(none)'
            routing=('Hardware: foreground='+str(hardware.get('foreground','not reported'))+' target='+str(hardware.get('target','none')),
                     'Hardware down: '+(' '.join(hardware.get('down',())[:10]) or '(none)'),
                     'Hardware events: '+recent(hardware),
                     'Terminal: confirmed='+str(terminal.get('confirmed','not reported'))+' focused='+str(terminal.get('focused','not reported')),
                     'Terminal returned flags: '+str(terminal.get('received_flags','not reported')),
                     'Terminal last motion: '+str(motion.get('key','none'))+' '+str(motion.get('kind',''))+' modifiers='+str(motion.get('modifiers','-')),
                     'Terminal motion bytes: '+str(motion.get('encoding') or '(not reported)')[:40],
                     'Terminal target: '+str(trouter.get('target','none'))+' enabled='+str(terminal.get('enabled','not reported')),
                     'Terminal events: '+recent(trouter),
                     'Input error: '+str(status.get('error') or '(none reported)')[:70])
            return ('Input diagnostic | V: return to room',
                    'Held keys: '+(' '.join(sorted(self.held_motion.held)) or '(none)'),
                    f'Forward {forward:+.3f}   Strafe {strafe:+.3f}',
                    f'Turn {turn:+.0f}   Look {look:+.0f}',
                    f'X {self.x:.2f}   Z {self.z:.2f}',
                    f'Yaw {self.yaw:.3f}   Pitch {self.pitch:.3f}',
                    'Last report: '+self.input_status,
                    f'Key-event reports: {self.key_event_reports}',
                    f'Input sequence {self.input_sequence}   Captured {captured}',
                    f'Render job pending: {pending}   Ready: {self.ready is not None}',
                    'Last scene snapshot: '+age,
                    *routing,
                    'No new scene jobs are submitted in this view.',
                    'Keypress-only input moves in steps; held keys need releases.')
        if self.error:return (self.name+' could not render.',self.error,'R: retry; close: return to desktop.')
        return (self.name, 'W/S walk, A/D strafe, arrows turn. Q exits standalone proof.')
    def spans(self):return ()
    def _publish_diagnostic(self):
        lines=self.lines();self.next_poll=self.clock()+.1
        if lines==self._diagnostic_lines:return None
        self.host.content(self.name,lines,lines,layer=None);self._diagnostic_lines=lines
        self.sequence+=1;self.last_frame=(self.sequence,self.input_sequence)
        return self.last_frame
    def on_close(self):self.cancel_keys();self._sync()
    def on_focus(self,*args):self._sync()
    def on_visibility(self,*args):self._sync()
    def close(self):
        if self.closed:return
        self.cancel_keys()
        self.closed=True;self.trace.cancel()
        if self.worker:self.worker.close();self.worker=None
        if self.frame_backend:self.frame_backend.close();self.frame_backend=None
        self.ready=None;self.previous=();self.pending_inputs=[]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seconds',type=float,default=0);parser.add_argument('--metrics',type=Path)
    parser.add_argument('--approved-forest',action='store_true',help='evaluate fixed approved forest profile (optional cost study)');parser.add_argument('--full-detail',action='store_true',help='retain close-up wildlife meshes for a matched LOD reference');parser.add_argument('--outdoors',action='store_true',help='ground-level Rainier terrain with fictional ruins and Lab wildlife');parser.add_argument('--float-mesh',action='store_true',help='exercise float-coordinate native normal stages; measured slower for this small room');parser.add_argument('--synchronous',action='store_true',help='reference preparation on UI loop for matched measurement');parser.add_argument('--compute-backend',choices=('auto','python','existing'),default='auto');parser.add_argument('--scene-backend',choices=('cpu','numpy','gpu'),default='numpy')
    parser.add_argument('--windowed',action='store_true',help='start in a small movable window instead of filling the terminal');parser.add_argument('--rift',action='store_true',help='mirrors, teleport and stillness dissolution');parser.add_argument('--portal',action='store_true');parser.add_argument('--walkthrough',action='store_true');parser.add_argument('--dense',action='store_true')
    parser.add_argument('--scripted-input',action='store_true');parser.add_argument('--reference-tones',action='store_true');a=parser.parse_args()
    if not sys.stdin.isatty():parser.error('run in a terminal')
    import compute_runtime,scene_acceleration
    from room import configure_numeric
    configure_numeric(a.float_mesh)
    compute_selection=compute_runtime.select(a.compute_backend);shader_selection=scene_acceleration.configure(a.scene_backend)
    window_name='Rainier walk' if a.outdoors else NAME
    cols,rows=measure(0);host=Host(cols,rows,[Window(window_name,2,2,min(162 if a.dense else 82,cols-3),min(56 if a.dense else 29,rows-4))],animate=False)
    host.background_enabled=False;host.shadow_enabled=False;host.window_opacity=1;host.show_clock=False;host.show_connectivity=False
    # Existing shared renderer, native if available; no engine configuration changes.
    library=ROOT/'native/build/_cellengine.abi3.so'
    if library.exists():host.enable_native(library)
    app=SurfaceRoom(host,implementation=ToneRenderer() if a.reference_tones else None,portal=a.portal,walkthrough=a.walkthrough,dense=a.dense,rift=a.rift,asynchronous=not a.synchronous,outdoors=a.outdoors,name=window_name,world_detail=not a.full_detail,approved_forest=a.approved_forest);app.open()
    if not a.windowed:host.maximize(window_name)
    decoder=Input();presentation=Presentation();old=termios.tcgetattr(0)
    started=time.monotonic();cpu=time.process_time();composition=write_seconds=0.;written=completed=bytes_out=0
    active=None;active_wrote=False;next_script=started+.4;script=0;scripted=0;running=True
    try:
        tty.setraw(0);os.write(1,b'\x1b[?1049h\x1b[?25l\x1b[?1000h\x1b[?1002h\x1b[?1006h')
        while running:
            now=time.monotonic()
            if a.seconds and now-started>=a.seconds:break
            dims=measure(0)
            if dims!=(host.width,host.height):host.resize(*dims)
            readers=[0]+([app.worker.readable] if app.worker else [])
            ready=select.select(readers,[],[],.005)[0]
            events=decoder.feed(os.read(0,4096)) if 0 in ready else decoder.feed(b'',expire=True)
            for event in events:
                if event[0]=='mouse':host.pointer(*event[1:]);continue
                key=event[1]
                if key in ('q','\x03'):running=False;break
                app.key(key,now)
            if a.scripted_input and now>=next_script:
                app.key(('right','w','a','left','s','d')[script%6],now);script+=1;scripted+=1;next_script=now+.35
            if active is None:
                active=app.poll();active_wrote=False
            t=time.perf_counter();out,_,_=host.flush(4096,max_seconds=.008);composition+=time.perf_counter()-t
            text=presentation.write(out,not host.damage,time.monotonic())
            if text:
                t=time.perf_counter();data=text.encode();offset=0
                while offset<len(data):offset+=os.write(1,data[offset:])
                write_seconds+=time.perf_counter()-t;bytes_out+=len(data);active_wrote|=active is not None
            if active and not host.damage:
                completed+=1;written+=int(active_wrote);app.presented();active=None
            if not host.window(window_name).opened:break
    finally:
        app.close();os.write(1,(presentation.close()+'\x1b[?1006l\x1b[?1002l\x1b[?1000l\x1b[?25h\x1b[?1049l').encode());termios.tcsetattr(0,termios.TCSANOW,old)
    elapsed=time.monotonic()-started
    def quantiles(values):
        values=sorted(values)
        return dict(n=len(values),p50=values[len(values)//2],p95=values[min(len(values)-1,int(len(values)*.95))]) if values else dict(n=0)
    result=dict(wall_seconds=elapsed,host_dimensions=[host.width,host.height],viewport_cells=app.dimensions,render_cells=app.render_dimensions,completed_updates=completed,frames_written=written,
        completed_update_hz=completed/elapsed,changed_frame_write_hz=written/elapsed,output_bytes=bytes_out,composition_encode_seconds=composition,output_write_seconds=write_seconds,
        cpu_seconds=time.process_time()-cpu,peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if sys.platform=='darwin' else 1024),
        input_to_written_frame_ms=quantiles(app.latencies),scripted_inputs=scripted,scene='outdoors' if a.outdoors else 'rift' if a.rift else 'portal' if a.portal else 'room',teleports=app.teleports,stats=app.stats,backend=host.render_backend,
        approved_forest=app.approved_forest,asynchronous=app.asynchronous,float_mesh=a.float_mesh,world_detail=not a.full_detail,worker_capacity=1,compute=compute_runtime.status(),scene_compute=scene_acceleration.status(),shader_selection=shader_selection,implementation='tone reference' if a.reference_tones else 'glyph surface renderer',sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [p for p in [HERE/'app.py',HERE/'room.py',HERE/'frame_job.py',HERE/'experience.py',HERE/'outdoors.py',HERE/'surface_renderer.py',HERE/'coverage_adapter.py',*([HERE.parent/'mixed-forest/mixed_forest.py',HERE.parent/'mixed-forest/frozen/seasonal_foreground.py',HERE.parent/'mixed-forest/frozen/static_foreground.py'] if app.approved_forest else []),HERE.parent/'landscape-lab/marmot_art.py',HERE.parent/'landscape-lab/eagle_art.py',ROOT/'core.py',ROOT/'geometry.py',ROOT/'geometry_compute.py',ROOT/'terminal.py',ROOT/'native/build/_cellengine.abi3.so',ROOT/'native/build-host/Darwin-arm64-geometry/libgeometry.dylib',ROOT/'data/tahoma-3dep.json',ROOT/'data/tahoma-3dep.i16.zlib'] if p.is_file()]},
        limits='Completed shared Host composition and PTY writes, not display scanout FPS. Scripted keys enter owner key handler; latency starts at handler, not physical keyboard. Preparation uses the existing capacity-one Inbox worker unless --synchronous. Python GIL still limits CPU parallelism; frame completion is not physical scanout. No combat, general collision engine, canonical hook or defaults changed.')
    if a.metrics:a.metrics.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))

if __name__=='__main__':main()
