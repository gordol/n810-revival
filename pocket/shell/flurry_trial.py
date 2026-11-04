"""Bounded private comparison controller; no transport or process ownership."""
import json
import time
from pathlib import Path


class Trial:
    width=80; height=24; warm_frames=2; windows=3; window_seconds=20.
    startup_limit=60.; outer_limit=150.
    def __init__(self,root,clock=time.monotonic):
        self.root=Path(root);self.root.mkdir(mode=0o700,parents=True,exist_ok=False)
        self.clock=clock;self.started=clock();self.began=None;self.initial=None
        self.records=[];self.seen_online=False;self.state='preparing';self.error=None
        self.actual_geometry=None;self.save()

    def save(self):
        result=dict(version=1,state=self.state,error=self.error,
                    elapsed_seconds=self.clock()-self.started,
                    logical_effect_geometry=[self.width,self.height],terminal_geometry=self.actual_geometry,
                    settings=dict(strands=24,seed=17,sway=.6,speed=1.,ascii=False,schedule_hz=6),
                    warm_frames=self.warm_frames,window_seconds=self.window_seconds,windows=self.records,
                    startup_limit_seconds=self.startup_limit,outer_limit_seconds=self.outer_limit,
                    receive_observed_online=self.seen_online,
                    physical_display_fps='unknown')
        path=self.root/'trial.json';temporary=self.root/'trial.json.tmp'
        temporary.write_text(json.dumps(result,indent=2)+'\n');temporary.replace(path)

    def fail(self,message):
        self.state='failed';self.error=message;self.save();raise RuntimeError(message)

    def viewport(self,columns,rows):
        self.actual_geometry=[columns,rows]
        if columns<self.width or rows<self.height+1:self.fail('Terminal cannot fit fixed 80x24 effect plus top bar; font/terminal unchanged')
        return self.width,self.height+1

    def configure(self,args):
        if any((args.smoke,args.terminal,args.mirror,args.reader,args.library,args.library_root,args.workbench,args.audio_socket,args.audio_provider,args.app_preview,args.kitchen_sink,args.legacy_aprs,args.legacy_workspace,args.screensaver,args.ascii)):
            self.fail('Flurry trial excludes startup apps, showcase, smoke and ASCII modes')
        args.minimal=True;args.no_save=True;args.no_animation=True;args.effect='flurry'
        args.panel='top';args.panel_mode='bar'
        if args.session.exists():self.fail('Trial requires an unused private --session path')
        if args.metrics is not None and args.metrics.exists():self.fail('Trial refuses to overwrite existing --metrics output')
        if args.app_state is None:args.app_state=self.root/'apps'
        if args.metrics is None:args.metrics=self.root/'render-metrics.json'

    def apply(self,host):
        host.set_effect('flurry');host.background_enabled=True;host.scene_seed=17
        host.flurry_strands=24;host.flurry_sway=.6;host.flurry_speed=1.

    def update(self,stats,host,source=None):
        now=self.clock()
        if now-self.started>self.outer_limit:self.fail('Flurry trial outer deadline exceeded')
        if (host.width,host.height,host.effect,host.background_enabled,host.scene_seed,host.flurry_strands,host.flurry_sway,host.flurry_speed,host.ascii)!=(80,24,'flurry',True,17,24,.6,1.,False):self.fail('Flurry trial configuration changed')
        if host.launcher_lines or host.help_lines or host.overview or any(host.shown(w) for w in host.windows):self.fail('Trial viewport changed by window/menu interaction')
        ready=True
        if source is not None:
            state=getattr(source,'state',None)
            if not isinstance(state,dict) or 'online' not in state:self.fail('Trial source has no receive connection evidence')
            ready=bool(state['online'])
            if self.seen_online and not ready:self.fail('Receive source degraded during trial')
            self.seen_online=self.seen_online or ready
        if host.flurry_provider and host.flurry_provider.status()['python_frames']:self.fail('Requested Flurry provider fell back to Python')
        if self.began is None:
            if now-self.started>self.startup_limit:self.fail('Flurry trial startup deadline exceeded')
            if ready and stats.effect_completed>=self.warm_frames:
                self.began=now;self.initial=stats.summary();self.state='measuring';self.save()
            return False
        if now-self.began>=self.window_seconds:
            final=stats.summary();elapsed=now-self.began
            delta={key:final[key]-self.initial[key] for key in ('total_frames','effect_generated','effect_completed','effect_superseded','total_output_bytes','total_compose_seconds','total_write_seconds','total_batches')}
            self.records.append(dict(elapsed_seconds=elapsed,effect_fps=delta['effect_completed']/elapsed,counts=delta,last_effect_id=final['last_effect_id'],numeric=host.flurry_provider.status() if host.flurry_provider else {'backend':'python'},compositor=host.render_backend))
            self.began=now;self.initial=final
            self.state='complete' if len(self.records)==self.windows else 'measuring';self.save()
        return self.state=='complete'

    def finish(self,error=None,stats=None):
        if self.state not in ('failed','complete'):
            self.state='failed' if error else 'cancelled';self.error=str(error) if error else 'Desktop exited before all trial windows completed'
        if stats is not None and self.began is not None and self.state!='complete':
            self.records.append(dict(partial=True,elapsed_seconds=self.clock()-self.began,final=stats.summary(),initial=self.initial))
        self.save()
