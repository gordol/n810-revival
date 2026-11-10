# SPDX-License-Identifier: GPL-2.0-or-later
"""Pixel-native GUI candidate. Terminal applications retain a text-view adapter.

No Host.flush, full desktop cell export, or cell-to-pixel compositor is used.
The display/session owner and the existing shared scene backend remain owners
of presentation and GPU resources. This path is opt-in until device acceptance.
"""
from array import array
import ctypes as C
import time
import struct
import os
from gpu_scene import Context as SharedContext


def rgb565(value):
    return (((value>>11)&31)*255//31<<16)|(((value>>5)&63)*255//63<<8)|(value&31)*255//31


def landscape_marks(layer,width):
    """Sparse artwork transport; static landscape is packed once per change."""
    return b''.join(struct.pack('=IIQ',y*width+x,ord(char),ink)
                    for (x,y),(char,ink) in layer.items())


class Context(SharedContext):
    native_pixels=True
    def __init__(self,platform):
        super().__init__(platform)
        self.background=None;self.panels={};self.text_views={};self.started_cpu=0
        self.batches={};self.batch_builds=0;self.batch_replays=0
        self.lib.pocket_scene_batch_supported.restype=C.c_int
        self.retain_commands=bool(self.lib.pocket_scene_batch_supported()) and os.environ.get("POCKET_SCENE_BATCHES")!="0"
        self.lib.pocket_scene_batch_end.argtypes=[C.c_void_p];self.lib.pocket_scene_batch_end.restype=C.c_void_p
        self.model_frames=0;self.text_view_builds=0;self.pending_damage=None;self.full_damage=True;self.landscape=None;self.landscape_base=None;self.background_key=None
        for name,args in {
            'pocket_scene_batch_begin':[C.c_void_p],
            'pocket_scene_batch_abort':[C.c_void_p],
            'pocket_scene_batch_replay':[C.c_void_p,C.c_void_p],
            'pocket_scene_batch_replay_offset':[C.c_void_p,C.c_void_p,C.c_int,C.c_int],
            'pocket_scene_pixel_stats':[C.c_void_p,C.c_void_p],
            'pocket_scene_sink_stats':[C.c_void_p,C.c_void_p],
            'pocket_scene_dma_stats':[C.c_void_p,C.c_void_p],
            'pocket_scene_begin_pixels':[C.c_void_p,C.c_uint],
            'pocket_scene_landscape':[C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_int,C.c_int,C.c_void_p,C.c_uint,C.c_uint],
            'pocket_scene_damage':[C.c_void_p,C.c_int,C.c_int,C.c_uint,C.c_uint],
            'pocket_scene_index_bounds':[C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_void_p],
            'pocket_scene_rect':[C.c_void_p,*([C.c_float]*4),C.c_uint],
            'pocket_scene_text':[C.c_void_p,C.c_float,C.c_float,C.c_void_p,C.c_uint,C.c_uint],
            'pocket_scene_flux_pixels':[C.c_void_p,C.c_double,C.c_double,C.c_double,C.c_uint],
            'pocket_scene_window_draw':[C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_int,C.c_int,C.c_void_p,C.c_uint,C.c_uint,C.c_int,C.c_uint],
        }.items():
            fn=getattr(self.lib,name);fn.argtypes=args;fn.restype=C.c_int
    def batch(self,name,key,draw,position=None):
        if not self.retain_commands:draw();return
        if os.environ.get("POCKET_SCENE_MOVE_REUSE")=="0":key=(key,position);position=None
        key=(self.last_size,key)
        previous=self.batches.get(name)
        if previous is None or previous[0]!=key:
            self.check(self.lib.pocket_scene_batch_begin(self.handle))
            try:
                draw()
                target=self.lib.pocket_scene_batch_end(self.handle)
                if not target:raise RuntimeError('Native scene command retention failed')
            except BaseException:
                self.lib.pocket_scene_batch_abort(self.handle)
                raise
            self.batches[name]=(key,target,position);self.batch_builds+=1
            if previous:self.release(previous[1])
        else:target=previous[1]
        origin=self.batches[name][2]
        if position is not None and origin is not None:
            self.check(self.lib.pocket_scene_batch_replay_offset(self.handle,target,position[0]-origin[0],position[1]-origin[1]))
        else:self.check(self.lib.pocket_scene_batch_replay(self.handle,target))
        self.batch_replays+=1
    def close(self):
        for batch in self.batches.values():self.release(batch[1])
        self.batches.clear()
        super().close()
    def update_background(self,host,step):
        if host.effect=='flux':
            self.background=(step,host.flux_density,host.flux_glow,host.flux_arms)
        elif host.effect=='pnw':
            from effects import pnw
            # Reuse the original scene decisions and artwork. No Python pixel
            # raster, Host.flush, desktop plane, or ANSI bridge is involved.
            scene=pnw(host.width,host.height,step,host.ascii,host.weather,
                      seed=host.scene_seed,nature_age=host.nature_age())
            key=(scene.base,host.width,host.height)
            if self.landscape_base is None or self.landscape_base[0][0] is not scene.base or self.landscape_base[0][1:]!=key[1:]:
                self.landscape_base=(key,landscape_marks(scene.base,host.width))
            self.landscape=(self.landscape_base[1],landscape_marks(scene.overlay,host.width))
        else:raise RuntimeError('Pixel-native background producer not connected: '+host.effect)
        self.platform.dirty=True;self.full_damage=True
        self.background_key=(host.background_enabled,host.effect,host.width,host.height)
        return True
    def prepare_model(self):
        h=self.platform.host
        if h.background_enabled and h.effect not in ('flux','pnw'):
            raise RuntimeError('Pixel-native background producer not connected: '+h.effect)
        if h.terrain_loading or h.terrain_arrival is not None or h.camera_motion:
            raise RuntimeError('Pixel-native terrain transition is not connected')
        unsupported=any((h.pager,h.overview,h.screensaver,h.help_lines,h.settings_lines,
                         bool(h.pointer_trail and h.pointer_trail.overlay)))
        if unsupported:raise RuntimeError('Pixel-native overlay producer not connected')
        # TUI flush also advances the model. The pixel route must retain that
        # scheduling step without invoking its cell composition afterward.
        menu_busy=bool(h.launcher_lines or h._launcher_dirty)
        h.tick(advance_background=not menu_busy and not h.drag)
        h.advance()
        key=(h.background_enabled,h.effect,h.width,h.height)
        if self.background_key!=key:
            self.full_damage=True;self.platform.dirty=True
            if h.background_enabled:self.update_background(h,h.background_step)
            self.background_key=key
        changed=bool(h.damage)
        if changed:
            # Keep model damage before the terminal scheduler releases it.
            # Bounds are in desktop coordinates; panel origin is added here.
            ox,oy=h.origin
            if hasattr(h.damage,'bounds') and hasattr(getattr(h.damage,'lib',None),'damage_bounds'):
                left,top,width,height=h.damage.bounds(h.width)
            elif getattr(self,'lib',None) is not None and hasattr(h.damage,'take') and os.environ.get('POCKET_SCENE_MOVE_REUSE')!='0':
                ids=h.damage.take(h.width*h.height)
                raw=ids.obj if isinstance(ids.obj,bytes) else bytes(ids)
                bounds=(C.c_uint32*4)()
                self.check(self.lib.pocket_scene_index_bounds(C.c_char_p(raw),len(ids),h.width,h.height,bounds))
                left,top,width,height=bounds
            else:
                left=h.width;top=h.height;right=bottom=0
                for index in h.damage:
                    x=index%h.width;y=index//h.width
                    left=min(left,x);top=min(top,y);right=max(right,x+1);bottom=max(bottom,y+1)
                width=right-left;height=bottom-top
            self.damage_rect((left+ox)*8,(top+oy)*16,width*8,height*16)
        if changed or not hasattr(self.platform.renderer,'layer_palette'):
            self.platform.renderer.prepare_palette()
        self.platform.dirty|=changed
        h.ui_painted=bool(h.ui_damage)
        h.damage.clear();h.ui_damage.clear();h._launcher_dirty.clear()
        h._launcher_presented_bounds=h.launcher_bounds() if h.launcher_lines else None
        h.composed_indices=();h.render_backend='native_pixels';h.render_reason=None
        return '',0,0
    def damage_rect(self,x,y,w,h):
        if self.pending_damage is not None:
            a,b,c,d=self.pending_damage
            right=max(x+w,a+c);bottom=max(y+h,b+d);x=min(x,a);y=min(y,b)
            w=right-x;h=bottom-y
        self.pending_damage=(x,y,w,h)
    def begin_frame(self):
        self.started_cpu=time.process_time_ns()
        r=self.platform.renderer;size=(r.size[0]*8,r.size[1]*16)
        self.check(self.lib.pocket_scene_size(self.handle,*size))
        resized=self.last_size!=size
        self.last_size=size
        self.check(self.lib.pocket_scene_begin_pixels(self.handle,0x101018))
        h=self.platform.host
        active={('window',w.name) for w in h.windows if h.shown(w)}|{('panel',xy) for xy in self.panels}
        if h.background_enabled:active|={('background',h.effect,i) for i in range(2 if h.effect=='pnw' else 1)}
        for name in tuple(self.batches):
            if name not in active:self.release(self.batches.pop(name)[1])
        if h.background_enabled:
            if h.effect=='pnw':
                if self.landscape is None:self.update_background(h,h.background_step)
                ox,oy=h.origin
                for i,marks in enumerate(self.landscape):
                    def draw(marks=marks):
                        self.check(self.lib.pocket_scene_landscape(self.handle,C.c_char_p(marks),len(marks)//16,h.width,h.height,ox*8,oy*16,r.layer_palette,len(r.layer_palette),r.layer_fallback))
                    self.batch(('background','pnw',i),(marks,h.width,h.height,ox,oy,bytes(r.layer_palette),r.layer_fallback),draw)
            else:
                state=self.background or (h.background_step,h.flux_density,h.flux_glow,h.flux_arms)
                self.batch(('background','flux',0),state,lambda:self.check(self.lib.pocket_scene_flux_pixels(self.handle,*state)))
        if not self.full_damage and self.pending_damage is not None and not resized:
            x,y,w,h=self.pending_damage
            right=min(size[0],x+w);bottom=min(size[1],y+h);x=max(0,x);y=max(0,y)
            self.check(self.lib.pocket_scene_damage(self.handle,x,y,max(0,right-x),max(0,bottom-y)))
        self.last_size=size
    def cells(self,*args):
        raise RuntimeError('Full desktop cells are not part of the native pixel path')
    def draw_records(self,records,cols,rows,x,y,fill,opacity):
        r=self.platform.renderer
        self.check(self.lib.pocket_scene_window_draw(self.handle,C.c_char_p(records),cols,rows,x,y,r.layer_palette,len(r.layer_palette),r.layer_fallback,int(fill),opacity))
    def draw_window(self,window,x,y,dx,dy):
        h=self.platform.host;n=h._native
        signature,plane=n.planes[window.name][:2];cols,rows=signature[:2]
        key=(signature,window.version,id(window.layer))
        old=self.text_views.get(window.name)
        if old is None or old[0]!=key:
            records=n.lib.export_cells(plane.pointer,array('I',range(cols*rows)))
            self.text_views[window.name]=(key,records);self.text_view_builds+=1
        else:records=old[1]
        view=n.cell_view(h,window,h.bounds(window))
        state=(key,dx,dy,h.shadow_enabled,h.shadow_opacity,h.window_fill,h.window_opacity,
               bytes(self.platform.renderer.layer_palette),self.platform.renderer.layer_fallback,view)
        def draw():
            if h.shadow_enabled:
                self.check(self.lib.pocket_scene_rect(self.handle,x+dx,y+dy,cols*8,rows*16,round(h.shadow_opacity*255)))
            self.draw_records(records,cols,rows,x,y,h.window_fill,round(h.window_opacity*255))
            if view is not None:
                data,cw,ch,cx,cy=view;ox,oy=h.origin
                self.draw_records(data,cw,ch,(cx+ox)*8,(cy+oy)*16,h.window_fill,round(h.window_opacity*255))
        self.batch(('window',window.name),(state,x,y) if view is not None else state,draw,position=None if view is not None else (x,y))
    def panel_text(self,x,y,text,fg,bg):
        previous=self.panels.get((x,y));current=(text,fg,bg)
        if previous==current:return False
        self.panels[x,y]=current
        self.damage_rect(x*8,y*16,max(len(text),len(previous[0]) if previous else 0)*8,16)
        return True
    def present(self,text):
        for (x,y),(label,fg,bg) in self.panels.items():
            def draw():
                self.check(self.lib.pocket_scene_rect(self.handle,x*8,y*16,len(label)*8,16,(rgb565(bg)<<8)|255))
                encoded=label.encode('utf-32-le')
                self.check(self.lib.pocket_scene_text(self.handle,x*8,y*16,C.c_char_p(encoded),len(label),rgb565(fg)))
            self.batch(('panel',(x,y)),(label,fg,bg),draw)
        super().present(False);self.model_frames+=1
        self.pending_damage=None;self.full_damage=False
        self.platform.host._flux_painted((time.process_time_ns()-self.started_cpu)/1e9)
    def status(self):
        result=super().status()
        if self.display is not None and hasattr(self.lib,'pocket_window_present_stats'):
            fn=self.lib.pocket_window_present_stats;fn.argtypes=[C.c_void_p,C.c_void_p];fn.restype=C.c_int
            counts=(C.c_uint64*4)();self.check(fn(self.display.handle,counts))
            result.update(dict(zip(('rfbi_submissions','rfbi_requested_pixels','rfbi_partial_submissions','rfbi_partial_rejections'),counts)))
        if self.display is not None and hasattr(self.lib,'pocket_window_timing_stats'):
            fn=self.lib.pocket_window_timing_stats;fn.argtypes=[C.c_void_p,C.c_void_p];fn.restype=C.c_int
            counts=(C.c_uint64*6)();self.check(fn(self.display.handle,counts))
            result['presentation_timing']=dict(zip(('wait_calls','wait_cpu_ns','wait_wall_ns','submit_calls','submit_cpu_ns','submit_wall_ns'),counts))
        n=self.platform.host._native
        result.update(app_view_builds=n.cell_view_builds,app_view_export_bytes=n.cell_view_export_bytes,app_view_index_allocations=n.cell_view_index_allocations,app_cells_sampled=n.layer_cells_sampled)
        values=(C.c_uint64*3)();self.check(self.lib.pocket_scene_pixel_stats(self.handle,values))
        result.update(dict(zip(('flux_geometry_builds','flux_geometry_replays','cpu_control_points'),values)))
        sink=(C.c_uint64*2)();self.check(self.lib.pocket_scene_sink_stats(self.handle,sink))
        result.update(final_cpu_sink_calls=sink[0],final_cpu_sink_bytes=sink[1])
        self.check(self.lib.pocket_scene_dma_stats(self.handle,sink))
        result.update(final_dma_sink_calls=sink[0],final_dma_sink_bytes=sink[1])
        result.update(retained_command_builds=self.batch_builds,retained_command_replays=self.batch_replays,retained_command_batches=len(self.batches),native_pixel_frames=self.model_frames,desktop_cell_compositions=0,
                      text_view_builds=self.text_view_builds,background=(self.platform.host.effect+' native raster') if self.platform.host.background_enabled else 'off',
                      cpu_work='model and text layout; native geometry submission'+('; shared PNW scene decisions' if self.platform.host.background_enabled and self.platform.host.effect=='pnw' else '; bounded Clifford control points' if self.platform.host.background_enabled else ''))
        return result
