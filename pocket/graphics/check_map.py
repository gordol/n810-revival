# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise semantic map handoff through the native desktop event dispatcher."""
from pathlib import Path
import json,sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from reference_fixtures import activate
activate()
import run
from scenes import MapScene,MapComposite


def main():
    from map_pixels import View
    original=View.render_image
    counts={'completed':False,'active':0,'missing':0,'composite':0,'surround':0,'drag_composite':0,'overview_inset':0,'inset_surface':0,'inset_error':'','side_overview':0,'locator_rect':0}
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
            if not hasattr(self,'stage'):
                self.stage=0;self.last_active=-1;self.drag_step=0
            schedule=({'launch':'window:Station Map'},
                      {'key':'+'},{'key':'\r'},
                      {'key':'-'},{'key':'\r'},
                      {'resize':[125,40]},{'key':'v'},
                      {'key':'+'},{'key':'-'},
                      {'key':'u'},{'key':'s'},{'key':'z'})
            map_view=next((view for view in self.pixel_apps if view.name=='Station Map'),None)
            ready=(map_view is not None and map_view.ready is not None and map_view.pending is None)
            # Advance only after the preceding action received a map frame.
            # Software CI rendering can take longer than a timed action script.
            advanced=counts['active']>self.last_active
            dispatched=False
            if self.stage<len(schedule) and (self.stage==0 or ready and advanced):
                self.actions.insert(0,schedule[self.stage]);self.stage+=1;dispatched=True
                self.last_active=counts['active']
            events=super().events()
            if not dispatched and self.stage==len(schedule) and ready and advanced and counts['overview_inset']:
                if map_view._surround_scene is not None and self.drag_step<3:
                    if self.drag_step==0:
                        wx,wy,ww,wh=self.host.bounds(self.host.window('Station Map'))
                        self.drag_origin=(wx+ww//2,wy+max(3,(wh-3)//2))
                    column,row=self.drag_origin
                    actions=((0,column,row,False),(32,column+6,row+4,False),(0,column+6,row+4,True))
                    # Hold the pointer until a shifted scene has actually drawn.
                    if self.drag_step!=2 or counts['drag_composite']:
                        events.append(('mouse',*actions[self.drag_step]));self.drag_step+=1
                        self.last_active=counts['active']
                elif self.drag_step==3 and counts['drag_composite']:
                    counts['completed']=True;self.closed=True
            return events
    run.shared.Platform=Platform;View.render_image=render
    try:
        with tempfile.TemporaryDirectory(prefix='pocket-map-check-') as folder:
            report=Path(folder)/'report.json'
            options=sys.argv[1:]
            sys.argv=[__file__,'--headless','--seconds','120','--state',folder,
                      '--report',str(report),'--effect-backend','cpu','--no-save',*options]
            run.main();data=json.loads(report.read_text());gpu=data['gpu_scene']
            if not counts['completed']:raise AssertionError('Map interaction sequence did not complete: '+repr(counts))
            if counts['active']<3 or counts['missing']:raise AssertionError(counts)
            if counts['drag_composite']<1:raise AssertionError('Native map drag did not draw its surrounding map: '+repr(counts))
            if counts['overview_inset']<1:raise AssertionError('Native map side overview omitted its inset scene: '+repr(counts))
            if len(scenes)<3 or gpu['map_builds']<3:raise AssertionError('Map did not rebuild')
            if gpu['diagnostic_readbacks']:raise AssertionError('Unexpected map readback')
            if data['errors'] or data['pixel_apps']['Station Map']['error']:raise AssertionError(data['pixel_apps'])
            print(json.dumps(dict(result='passed',semantic_scenes=len(scenes),**counts,**gpu)))
    finally:run.shared.Platform=base;View.render_image=original

if __name__=='__main__':main()
