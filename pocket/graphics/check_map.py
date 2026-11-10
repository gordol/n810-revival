# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise semantic map handoff through the native desktop event dispatcher."""
from pathlib import Path
import json,os,sys,tempfile,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
from reference_fixtures import activate
activate()
import run
from scenes import MapScene


def main():
    from map_pixels import View
    original=View.render_image
    counts={'active':0,'missing':0,'insets':0,'dense_insets':0,'drag_frames':0,'backdrop_frames':0,'surround_pending':0,'surround_error':'','smooth_text_frames':0,'sources':{}}
    scenes=set()
    def render(view):
        plan=view.plan();result=original(view)
        if plan is not None:
            counts['active']+=1
            if result is None:counts['missing']+=1
            else:
                if not isinstance(result[0],MapScene):raise AssertionError('Map bypassed semantic scene')
                scenes.add(id(result[0]))
                counts['drag_frames']+=len(result)>5
                counts['backdrop_frames']+=len(result)>5 and result[0].surround is not None
                counts['surround_pending']+=view._surround_future is not None
                counts['surround_error']=view.surround_error or counts['surround_error']
                source=getattr(getattr(view.ready_surface,'image',None),'source','unknown')
                counts['sources'][source]=counts['sources'].get(source,0)+1
                counts['insets']+=len(result[0].insets)
                counts['dense_insets']+=sum(inset.sample_width>inset.width for inset,_,_ in result[0].insets)
        return result
    base=run.shared.Platform
    class Platform(base):
        def present(self,complete):
            shown=super().present(complete)
            if shown and self.report.get('native_text',{}).get('enabled'):
                counts['smooth_text_frames']+=1
            before=os.environ.get('POCKET_MAP_DRAG_CAPTURE_BEFORE')
            if (shown and before and not getattr(self,'before_captured',False) and
                    getattr(self,'started',None) is not None and time.monotonic()-self.started>=7.7):
                view=next((app for app in self.pixel_apps if app.name=='Station Map'),None)
                if view and view.pan_offset() is None and view.ready and view.ready.surround is not None:
                    Path(before).write_bytes(self.gpu_context.capture());self.before_captured=True
            after=os.environ.get('POCKET_MAP_DRAG_CAPTURE_AFTER')
            if (shown and after and getattr(self,'drag_captured',False) and
                    not getattr(self,'after_captured',False)):
                view=next((app for app in self.pixel_apps if app.name=='Station Map'),None)
                base=getattr(getattr(view,'owner',None),'base',None)
                projection=getattr(getattr(getattr(view,'ready_surface',None),'image',None),'projection',None)
                if (view and view.pan_offset() is None and projection is not None and base is not None and
                        tuple(projection.center)==tuple(base.center)):
                    Path(after).write_bytes(self.gpu_context.capture());self.after_captured=True
            target=os.environ.get('POCKET_MAP_DRAG_CAPTURE')
            if shown and target and not getattr(self,'drag_captured',False):
                view=next((app for app in self.pixel_apps if app.name=='Station Map'),None)
                if view and view.pan_offset() is not None and view.ready and view.ready.surround is not None:
                    if self.gpu_context.drag_terrain_planes!=1:
                        raise AssertionError('Drag composed more than one terrain plane')
                    Path(target).write_bytes(self.gpu_context.capture())
                    self.drag_captured=True
            return shown
        def attach(self,*args):
            super().attach(*args)
            def reject(*args):raise AssertionError('Desktop attempted pixel readback rasterization')
            self.renderer.finish=reject
        def events(self):
            if not hasattr(self,'started'):self.started=time.monotonic();self.stage=0
            schedule=((.2,{'launch':'window:Station Map'}),(.5,{'map_sidebar':True}),
                      (1.2,{'key':'+'}),(1.6,{'key':'\r'}),
                      (2.2,{'key':'-'}),(2.6,{'key':'\r'}),
                      (3.2,{'resize':[125,40]}),(4.,{'key':'v'}),
                      (4.5,{'key':'+'}),(5.,{'key':'-'}),
                      (5.5,{'key':'u'}),(8.4,{'drag':'down'}),(8.5,{'drag':'move'}),
                      (8.65,{'drag':'up'}),(9.,{'key':'z'}),(9.3,{'key':'z'}),
                      (9.6,{'key':'t'}),(10.,{'launch':'window:Connections'}))
            if os.environ.get('POCKET_MAP_DRAG_PREVIEW'):
                schedule=tuple((at,action) for at,action in schedule if action!={'key':'v'})
            if os.environ.get('POCKET_MAP_DRAG_CAPTURE_AFTER'):
                schedule=tuple((at,action) for at,action in schedule if at<9.0)
            if self.stage<len(schedule) and time.monotonic()-self.started>=schedule[self.stage][0]:
                action=schedule[self.stage][1]
                drag=action.get('drag')
                if drag:
                    from pointer_events import PointerEvent
                    w=self.host.window('Station Map');wx,wy,_,_=self.host.bounds(w);ox,oy=self.host.origin
                    x,y=wx+ox+1+40,wy+oy+1+20
                    self._drag_event=PointerEvent(('mouse',32 if drag=='move' else 0,x,y,drag=='up'),
                        pixel=(x*8+4+(80 if drag!='down' else 0),y*16+8+(40 if drag!='down' else 0)))
                elif action.get('map_sidebar'):
                    form=self.registry.forms['Station Map']._ensure()
                    if form is not None and not form.base.side_overview:form.key('s')
                else:self.actions.insert(0,action)
                self.stage+=1
            drag_events=[self._drag_event] if hasattr(self,'_drag_event') else []
            if drag_events:del self._drag_event
            return drag_events+super().events()
    run.shared.Platform=Platform;View.render_image=render
    desktop_window=run.DesktopWindow
    hidden_text=bool(os.environ.get('POCKET_MAP_HIDDEN_TEXT'))
    if hidden_text:
        import ctypes as C
        class HiddenWindow(desktop_window):
            def __init__(self,path,fd=-1):
                self.width=800;self.height=480;self.canvas_size=(800,480)
                self.lib=C.CDLL(str(path))
                self.lib.pocket_window_open_hidden.argtypes=[C.c_int]
                self.lib.pocket_window_open_hidden.restype=C.c_void_p
                self.lib.pocket_window_error.restype=C.c_char_p
                self.lib.pocket_window_present.argtypes=[C.c_void_p,C.c_void_p]
                self.lib.pocket_window_close.argtypes=[C.c_void_p]
                self.lib.pocket_window_event.argtypes=[C.POINTER(C.c_int)]
                self.handle=self.lib.pocket_window_open_hidden(fd)
                if not self.handle:raise RuntimeError(self.lib.pocket_window_error().decode())
        run.DesktopWindow=HiddenWindow
    try:
        with tempfile.TemporaryDirectory(prefix='pocket-map-check-') as folder:
            report=Path(folder)/'report.json'
            options=sys.argv[1:]
            sys.argv=[__file__,*([] if hidden_text else ['--headless']),'--seconds','12','--state',folder,
                      '--report',str(report),'--effect-backend','cpu','--no-save',*options]
            run.main();data=json.loads(report.read_text());gpu=data['gpu_scene']
            if counts['active']<3 or counts['missing'] or not counts['drag_frames']:raise AssertionError(counts)
            if hidden_text and not counts['smooth_text_frames']:raise AssertionError('Smooth Mac map text was never active')
            if len(scenes)<3 or gpu['map_builds']<3:raise AssertionError('Map did not rebuild')
            if not counts['insets'] or not counts['dense_insets']:raise AssertionError('Detailed pixel locator scene did not render')
            expected_readbacks=sum(bool(os.environ.get(name)) for name in
                ('POCKET_MAP_DRAG_CAPTURE','POCKET_MAP_DRAG_CAPTURE_BEFORE','POCKET_MAP_DRAG_CAPTURE_AFTER'))
            if gpu['diagnostic_readbacks']!=expected_readbacks:raise AssertionError('Unexpected map readback')
            if data['errors'] or data['pixel_apps']['Station Map']['error']:raise AssertionError(data['pixel_apps'])
            print(json.dumps(dict(result='passed',semantic_scenes=len(scenes),**counts,**gpu)))
    finally:run.shared.Platform=base;View.render_image=original;run.DesktopWindow=desktop_window

if __name__=='__main__':main()
