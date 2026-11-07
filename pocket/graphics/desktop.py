# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Pocket's pixel frontend. Shares models/window actions, never terminal I/O."""
from pathlib import Path
import sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window
from cells import Font,LiveCells

class Desktop:
    def __init__(self,font,renderer_library,*,native_library=None,backend="native"):
        self.host=Host(100,30,[],animate=False)
        self.host.background_enabled=False
        self.host.show_clock=False;self.host.show_connectivity=False
        if native_library and not self.host.enable_native(native_library):
            raise RuntimeError(self.host.native_error)
        if backend=='mbx':
            from mbx import Renderer
            self.renderer=Renderer(self.host,font,renderer_library)
        elif backend=='native':self.renderer=LiveCells(self.host,Font(font),renderer_library,bulk=True)
        else:raise ValueError('Unknown renderer')
        self.backend=backend;self.renderer_library=Path(renderer_library)
        self.apps={};self.closed=False;self.repaint=True;self.frame_costs={};self.pixel_compositor=None
        self.host.add_window(Window('Pocket',4,3,48,12,lines=(
            'Pocket graphical frontend','',
            'Shared apps and window actions.','Open Surface Room (F2)')))
        self.host.focus='Pocket';self.host.invalidate((0,0,100,30))

    @classmethod
    def from_host(cls,host,font,renderer_library,*,backend="mbx"):
        """Attach an already initialized desktop model; preserve its catalog/state.

        The model owner retains app polling, dispatch and lifecycle. This adapter
        only composes/renders damage; it creates no welcome window or app registry.
        """
        if (host.width,host.height)!=(100,30):
            raise ValueError('Current pixel target requires a100x30 model')
        if host._native is None:
            raise ValueError('Direct desktop requires the native compositor')
        self=cls.__new__(cls);self.host=host
        if backend=='mbx':
            from mbx import Renderer
            self.renderer=Renderer(host,font,renderer_library)
        elif backend=='native':self.renderer=LiveCells(host,Font(font),renderer_library,bulk=True)
        else:raise ValueError('Unknown renderer')
        self.backend=backend;self.renderer_library=Path(renderer_library)
        self.apps={};self.closed=False;self.repaint=True;self.frame_costs={};self.pixel_compositor=None
        return self

    def dispatch(self,event):
        action=event.get('action')
        if action=='pointer':
            x,y=event['x'],event['y'];button=event['button']
            if type(x) is not int or type(y) is not int or type(button) is not int or not 0<=x<800 or not 0<=y<480:
                raise ValueError('Pointer outside pixel desktop')
            column,row=x//8,y//self.renderer.font.height
            welcome=self.host.window('Pocket')
            if button==0 and not event.get('released') and self.host.shown(welcome) and self.host.focus=='Pocket':
                wx,wy,ww,wh=self.host.bounds(welcome)
                if wx<column<wx+ww-1 and row==wy+4:
                    self.dispatch(dict(action='open',app='surface-room'));return
            self.host.pointer(button,column,row,bool(event.get('released',False)))
        elif action=='open':
            if event.get('app')!='surface-room':raise ValueError('App is not connected to the pixel frontend')
            if 'surface-room' not in self.apps:
                sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell/apps/surface-renderer'))
                from app import SurfaceRoom
                if not any(w.name=='Surface room' for w in self.host.windows):self.host.add_window(Window('Surface room',8,3,82,25))
                if self.backend=='mbx':
                    from room_pixels import PixelRoom
                    app=PixelRoom(self.host,self.renderer_library.resolve().parent/'room-pixels.so')
                else:app=SurfaceRoom(self.host,asynchronous=False)
                app.open();self.apps['surface-room']=app
            else:self.host.activate('Surface room')
        elif action=='key':
            for app in self.apps.values():
                if app.name==self.host.focus:
                    now=time.monotonic();kind='release' if event.get('released') else 'press'
                    handled=app.key_event(event['key'],kind,now)
                    if not handled and kind=='press':app.key(event['key'],now)
        elif action=='close':
            self.host.close(event['window'])
        elif action=='focus':
            self.host.activate(event['window'])
        elif action=='redraw':self.repaint=True
        elif action=='quit':self.closed=True
        else:raise ValueError('Unknown graphical desktop action')

    def render(self):
        self.frame_costs={}
        stamp=(time.monotonic_ns(),time.process_time_ns())
        def mark(name):
            nonlocal stamp
            now=(time.monotonic_ns(),time.process_time_ns())
            self.frame_costs[name]={'wall_ns':now[0]-stamp[0],'cpu_ns':now[1]-stamp[1]};stamp=now
        for app in self.apps.values():
            app.poll()
            if app.error:raise RuntimeError(app.error)
        mark("app_state")
        drawn=0
        # Drain this coherent damage set, not a second terminal frontend.
        for _ in range(48):
            if not self.host.damage:break
            _,computed,n=self.renderer.flush(2048);drawn+=n
            if not computed:break
        if self.host.damage:raise RuntimeError('Pixel composition made incomplete progress')
        mark("native_composition_and_batch")
        if drawn and self.backend=="mbx":self.renderer.finish()
        mark("desktop_gpu_and_readback")
        repaint=self.repaint;self.repaint=False
        pixel_apps=[app for app in self.apps.values() if hasattr(app,'render_image') and self.host.shown(self.host.window(app.name)) and not self.host.window(app.name).rolled]
        if not (drawn or repaint or any(app.pixel_dirty for app in pixel_apps)):return None
        canvas=bytearray(self.renderer.pixels)
        if pixel_apps:
            if self.pixel_compositor is None:
                from pixel_compositor import Compositor
                self.pixel_compositor=Compositor(self.host,self.renderer,self.renderer_library.resolve().parent/'room-pixels.so')
            self.pixel_compositor.compose(canvas,pixel_apps)
        mark("room_pixels_and_native_blit")
        return canvas

    def close(self):
        for app in self.apps.values():app.close()
        if self.pixel_compositor:self.pixel_compositor.close()
        self.renderer.close();self.closed=True
