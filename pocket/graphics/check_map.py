# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise semantic map handoff through the native desktop event dispatcher."""
from pathlib import Path
import json,sys,tempfile,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from reference_fixtures import activate
activate()
import run
from scenes import MapScene,MapComposite


def main():
    from map_pixels import View
    original=View.render_image
    counts={'active':0,'missing':0,'composite':0,'surround':0,'drag_composite':0,'overview_inset':0,'inset_surface':0,'inset_error':'','side_overview':0,'locator_rect':0}
    scenes=set()
    def render(view):
        plan=view.plan();result=original(view)
        if plan is not None:
            counts['active']+=1
            if getattr(plan[2],'inset',None) is not None:counts['inset_surface']+=1
            if view.error:counts['inset_error']=view.error
            base=getattr(view.owner,'base',None)
            if getattr(base,'side_overview',False):counts['side_overview']+=1
            if getattr(base,'_locator_rect',None) is not None:counts['locator_rect']+=1
            if result is None:counts['missing']+=1
            else:
                if isinstance(result[0],MapScene):scenes.add(id(result[0]))
                elif isinstance(result[0],MapComposite):
                    counts['composite']+=1
                    shifted=any(item[1]<0 or item[2]<0 for item in result[0].layers[:2])
                    if shifted:
                        if len(result[0].layers)<2:raise AssertionError('Pan preview omitted the surrounding map')
                        counts['drag_composite']+=1;counts['surround']+=1
                    if len(result[0].layers)>2 or len(result[0].layers)==2 and not shifted:counts['overview_inset']+=1
                else:raise AssertionError('Map bypassed semantic scene')
        return result
    base=run.shared.Platform
    class Platform(base):
        def attach(self,*args):
            super().attach(*args)
            def reject(*args):raise AssertionError('Desktop attempted pixel readback rasterization')
            self.renderer.finish=reject
        def events(self):
            if not hasattr(self,'started'):self.started=time.monotonic();self.stage=0
            schedule=((.2,{'launch':'window:Station Map'}),
                      (1.2,{'key':'+'}),(1.6,{'key':'\r'}),
                      (2.2,{'key':'-'}),(2.6,{'key':'\r'}),
                      (3.2,{'resize':[125,40]}),(4.,{'key':'v'}),
                      (4.5,{'key':'+'}),(5.,{'key':'-'}),
                      (5.5,{'key':'u'}),(5.9,{'key':'s'}),(6.2,{'key':'z'}))
            if self.stage<len(schedule) and time.monotonic()-self.started>=schedule[self.stage][0]:
                self.actions.insert(0,schedule[self.stage][1]);self.stage+=1
            events=super().events()
            elapsed=time.monotonic()-self.started
            map_view=next((view for view in self.pixel_apps if view.name=='Station Map'),None)
            if elapsed>=6.5 and self.stage>=len(schedule) and getattr(self,'drag_step',0)<3:
                if map_view is not None and map_view._surround_scene is not None:
                    wx,wy,ww,wh=self.host.bounds(self.host.window('Station Map'))
                    column=wx+ww//2;row=wy+max(3,(wh-3)//2)
                    actions=((0,column,row,False),(32,column+6,row+4,False),(0,column+6,row+4,True))
                    self.drag_step=getattr(self,'drag_step',0)
                    if self.drag_step<len(actions):
                        events.append(('mouse',*actions[self.drag_step]));self.drag_step+=1
            return events
    run.shared.Platform=Platform;View.render_image=render
    try:
        with tempfile.TemporaryDirectory(prefix='pocket-map-check-') as folder:
            report=Path(folder)/'report.json'
            options=sys.argv[1:]
            sys.argv=[__file__,'--headless','--seconds','8','--state',folder,
                      '--report',str(report),'--effect-backend','cpu','--no-save',*options]
            run.main();data=json.loads(report.read_text());gpu=data['gpu_scene']
            if counts['active']<3 or counts['missing']:raise AssertionError(counts)
            if counts['drag_composite']<1:raise AssertionError('Native map drag did not draw its surrounding map: '+repr(counts))
            if counts['overview_inset']<1:raise AssertionError('Native map side overview omitted its inset scene: '+repr(counts))
            if len(scenes)<3 or gpu['map_builds']<3:raise AssertionError('Map did not rebuild')
            if gpu['diagnostic_readbacks']:raise AssertionError('Unexpected map readback')
            if data['errors'] or data['pixel_apps']['Station Map']['error']:raise AssertionError(data['pixel_apps'])
            print(json.dumps(dict(result='passed',semantic_scenes=len(scenes),**counts,**gpu)))
    finally:run.shared.Platform=base;View.render_image=original

if __name__=='__main__':main()
