# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise semantic map handoff through the native desktop event dispatcher."""
from pathlib import Path
import json,sys,tempfile,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from reference_fixtures import activate
activate()
import run
from scenes import MapScene


def main():
    from map_pixels import View
    original=View.render_image
    counts={'active':0,'missing':0}
    scenes=set()
    def render(view):
        plan=view.plan();result=original(view)
        if plan is not None:
            counts['active']+=1
            if result is None:counts['missing']+=1
            else:
                if not isinstance(result[0],MapScene):raise AssertionError('Map bypassed semantic scene')
                scenes.add(id(result[0]))
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
                      (5.5,{'key':'u'}),(6.,{'key':'z'}),
                      (6.5,{'key':'t'}),(7.,{'launch':'window:Connections'}))
            if self.stage<len(schedule) and time.monotonic()-self.started>=schedule[self.stage][0]:
                self.actions.insert(0,schedule[self.stage][1]);self.stage+=1
            return super().events()
    run.shared.Platform=Platform;View.render_image=render
    try:
        with tempfile.TemporaryDirectory(prefix='pocket-map-check-') as folder:
            report=Path(folder)/'report.json'
            options=sys.argv[1:]
            sys.argv=[__file__,'--headless','--seconds','8','--state',folder,
                      '--report',str(report),'--effect-backend','cpu','--no-save',*options]
            run.main();data=json.loads(report.read_text());gpu=data['gpu_scene']
            if counts['active']<3 or counts['missing']:raise AssertionError(counts)
            if len(scenes)<3 or gpu['map_builds']<3:raise AssertionError('Map did not rebuild')
            if gpu['diagnostic_readbacks']:raise AssertionError('Unexpected map readback')
            if data['errors'] or data['pixel_apps']['Station Map']['error']:raise AssertionError(data['pixel_apps'])
            print(json.dumps(dict(result='passed',semantic_scenes=len(scenes),**counts,**gpu)))
    finally:run.shared.Platform=base;View.render_image=original

if __name__=='__main__':main()
