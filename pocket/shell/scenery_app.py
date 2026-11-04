#!/usr/bin/env python3
"""Scenery: shared desktop/standalone scene controls and portable preparation."""
from pathlib import Path


class SceneryApp:
    navigation_tab_row=2
    actions=(("\x0f","Show / hide controls"),)
    appearance=('scene_seed','season','light_mode','moon_phase','terrain_grid','show_foliage','show_animals','show_flowers','terrain_shadows')
    def __init__(self,host,library,close=lambda:None):
        import time
        from core import Host
        from model_scene import Renderer
        from settings import SettingsManager
        from scenery import rows
        from controls import scene_controls
        # A scene owns its camera/time/preferences. The desktop's background and
        # its worker are independent; immutable terrain caches remain shared.
        self._source=host;self._initialized=False
        self.scene=Host(1,1,[],clock=host.clock,wall_clock=host.wall_clock)
        for key in ('ascii','scene_seed','season','light_mode','moon_phase','terrain_grid','show_foliage','show_animals','show_flowers','show_lookout','terrain_shadows','nature_epoch','nature_rate','static_world_age','style'):
            setattr(self.scene,key,getattr(host,key))
        self.scene.scenery=dict(host.scenery)
        self.renderer=Renderer();self.scene.terrain_renderer=self.renderer
        self.scene.set_effect('terrain');self.scene.parallax=0
        self._active=False;self._layer=None;self._display=None;self._clock=time.monotonic
        self.controls_visible=True;self.width=96;self.height=30
        shared=scene_controls(self.scene)
        self.manager=SettingsManager([('Scenery',(' /\\ ','/~~\\','    '),'Landscape, camera and library',[
            ('Scene',rows(self.scene,library)),('Nature',[c.row() for c in shared['sky']]),('Shadows',[shared['shadows'][-1].row()])])],close=close)
        self.manager.category='Scenery'
    def set_active(self,active):
        if self._active and not active:
            self.renderer.suspend()
            self._layer=None;self._display=None
        if active and not self._initialized:
            previous=(dict(self.scene.scenery),tuple(getattr(self.scene,key) for key in self.appearance))
            self.scene.scenery=dict(self._source.scenery)
            for key in self.appearance:setattr(self.scene,key,getattr(self._source,key))
            self._initialized=True
            if previous!=(self.scene.scenery,tuple(getattr(self.scene,key) for key in self.appearance)):
                callback=getattr(self,'_session_callback',None)
                if callback:callback()
        self._active=active
    def bind_session(self,callback):
        self._session_callback=callback
        self.scene.session_callback=self._scene_session_changed
    def _scene_session_changed(self,scope,key=None):
        if scope!='preference' or key not in (None,'scenery',*self.appearance):return
        callback=getattr(self,'_session_callback',None)
        if callback:callback()
    def _toggle_controls(self):
        self.controls_visible=not self.controls_visible
        callback=getattr(self,'_session_callback',None)
        if callback:callback()
    def session_state(self):
        return dict(scenery=dict(self.scene.scenery),appearance={k:getattr(self.scene,k) for k in self.appearance},controls_visible=self.controls_visible)
    def restore_session(self,state):
        from scenery import validate
        from scenery import PHASES
        import math
        try:
            config=validate(state['scenery']);a=state['appearance'];visible=state['controls_visible']
            if type(visible) is not bool or set(a)!=set(self.appearance):return
            if a['season'] not in ('auto','spring','summer','autumn','winter') or a['light_mode'] not in ('dynamic','day','night') or a['moon_phase'] not in PHASES:return
            if type(a['scene_seed']) is not int or not 0<=a['scene_seed']<2**32:return
            if type(a['terrain_grid']) not in (int,float) or not math.isfinite(a['terrain_grid']) or not 0<=a['terrain_grid']<=.35:return
            if any(type(a[k]) is not bool for k in ('show_foliage','show_animals','show_flowers','terrain_shadows')):return
        except (KeyError,ValueError,TypeError):return
        self.scene.scenery=config._asdict()
        for key in self.appearance:setattr(self.scene,key,a[key])
        self.controls_visible=visible;self._initialized=True
    def poll_interval(self):return .05 if self._active and self.renderer.pending else .2 if self._active else None
    def poll(self):pass
    def _bounds(self):
        controls=min(38,max(0,self.width-24)) if self.controls_visible else 0
        return controls+(1 if controls else 0),0,max(1,self.width-controls-(1 if controls else 0)),max(1,self.height-2)
    def key(self,key):
        if key=='\x1b':self.manager.close();return True
        if key=='\x0f':self._toggle_controls();return True
        return self.manager.key(key)
    def pointer(self,column,row,width,button=0,released=False):
        self.width=width
        if row==self.height-2 and button==0 and not released:
            self._toggle_controls();return True
        left,_,_,_=self._bounds()
        if column<left and self.controls_visible:
            return self.manager.pointer(column,row,max(1,left-1),button,released)
        return False
    def _render(self):
        from landscape_detail import Nature
        from scenery import Config
        from core import Cell
        from loading import frame
        left,top,width,height=self._bounds();state=self.scene
        state.width=width;state.height=height
        nature=Nature(state.season,state.show_foliage,state.show_animals,state.show_flowers,state.show_lookout,state.scene_seed,state.terrain_grid,tuple(state.scenery[k] for k in Config._fields))
        image=self.renderer.frame(width,height,state.ascii,state.nature_age(),1,False,state.light_mode,state.moon_phase,0,1,state.terrain_shadows,nature)
        if image.base:
            token=(left,top,width,height,id(image.base))
            if token==self._display:return
            cells=tuple(Cell(*image.get((x,y),(' ',1<<48))) for y in range(height) for x in range(width))
        else:
            # The same geometry scaffold/loader as the desktop, scoped to this
            # viewport. There is only one latest request and one owned worker.
            step=int(self._clock()*6)%32;token=(left,top,width,height,step,tuple(self.renderer.trace.snapshot()))
            if token==self._display:return
            cells=tuple(Cell(*c) for c in frame(width,height,step,state.ascii,self.renderer.trace.snapshot(),wire=self.renderer.trace.wire(),centered=True))
        self._layer=(left,top,width,height,cells);self._display=token
    def lines(self):
        self._render()
        left,_,_,_=self._bounds()
        self.manager.width=max(1,left-1);self.manager.height=max(1,self.height-2)
        if self.manager.category is None:self.manager.category='Scenery'
        controls=self.manager.lines() if left else ()
        lines=[((controls[y] if y<len(controls) else '')[:left-1].ljust(left-1)+'│') if left else '' for y in range(max(0,self.height-2))]
        lines.append('[ '+('Hide controls' if left else 'Show controls')+' ] Ctrl-O | Esc close');lines.append('')
        self._spans=tuple(s for s in self.manager.spans() if left and s[0]<self.height-1 and s[1]+s[2]<=left-1)
        return tuple(lines)
    def spans(self):return getattr(self,'_spans',())
    def layer(self):return self._layer
    def help_pages(self):
        return (('Scenery viewport',('The scene renders inside this window; the desktop background stays unchanged.',
            'Click the bottom Show / Hide controls button or press Ctrl-O.',
            'Tab selects a control; Left / Right adjusts it. [ / ] changes section.',
            'Save scenery stores a recipe; Capture view saves the completed image and camera.',
            'Escape closes the window. Reopening keeps this scene for the session.')),)
    def close(self):self.renderer.close()


def main():
    import argparse,sys
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',type=Path,help='prepare a scene pack on this machine, then exit')
    parser.add_argument('--prepared',type=Path,help='display a prepared pack without building terrain')
    parser.add_argument('--preset',choices=('original','wide','elevated','valley'),default='original')
    parser.add_argument('--quality',choices=('compact','detailed'),default='compact')
    parser.add_argument('--size',default='98x25',help='prepared scene columns x rows')
    parser.add_argument('--recipe',type=Path,help='saved scene-*.json library recipe to prepare')
    args,extra=parser.parse_known_args()
    if args.prepare and args.prepared:parser.error('choose prepare or prepared')
    if args.prepare:
        from scene_package import prepare
        try:w,h=map(int,args.size.lower().split('x'));print(prepare(args.prepare,w,h,args.preset,args.quality,args.recipe))
        except (ValueError,OSError) as error:parser.error(str(error))
    elif args.prepared:
        from scene_package import play
        play(args.prepared)
    else:
        # Same application form, window manager, controls and renderer as the
        # desktop. A separate library entry is saved explicitly by its button.
        sys.argv=[sys.argv[0],'--minimal','--no-save','--scenery-app','--scene-preset',args.preset,'--scene-quality',args.quality,*extra]
        from demo import main as desktop
        desktop()


if __name__=='__main__':main()
