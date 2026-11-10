# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared native scene rasterization/composition over a platform backend."""
from collections import OrderedDict
from pathlib import Path
import ctypes as C
import time
from scenes import MapScene,RoomScene


def overlay_records(lib,pointer,cols,rows,outline=False):
    """Export a dense batch, preserving hollow outline interiors as blanks."""
    from array import array
    return lib.export_cells(pointer,array('I',range(cols*rows)),True) if outline else lib.export_cells(pointer,array('I',range(cols*rows)))


def subtract(rect,cut):
    x,y,w,h=rect;a,b,c,d=cut
    left,top,right,bottom=max(x,a),max(y,b),min(x+w,a+c),min(y+h,b+d)
    if left>=right or top>=bottom:return [rect]
    return [r for r in ((x,y,w,top-y),(x,bottom,w,y+h-bottom),(x,top,left-x,bottom-top),(right,top,x+w-right,bottom-top)) if r[2]>0 and r[3]>0]


class Context:
    def __init__(self,platform):
        self.platform=platform;self.display=platform.display;self.hidden=None
        self.lib=self.display.lib if self.display is not None and hasattr(self.display.lib,'pocket_scene_open') else C.CDLL(str(Path(platform.library).resolve().parent/'window.so'))
        self.native_room=all(hasattr(self.lib,n) for n in ('pocket_scene_room','pocket_scene_room_create','pocket_scene_room_source'))
        self.room_binding=None
        declarations={
            'pocket_scene_open':([C.c_void_p,C.c_int],C.c_void_p),
            'pocket_scene_backend':([C.c_void_p],C.c_char_p),
            'pocket_scene_font':([C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint,C.c_void_p,C.c_void_p,C.c_uint],C.c_int),
            'pocket_scene_size':([C.c_void_p,C.c_uint,C.c_uint],C.c_int),
            'pocket_scene_cells':([C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_int],C.c_int),
            'pocket_scene_begin':([C.c_void_p],C.c_int),
            'pocket_scene_map':([C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_uint],C.c_void_p),
            'pocket_scene_lines':([C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint,C.c_uint],C.c_int),
            'pocket_scene_marks':([C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint,C.c_int],C.c_int),
            'pocket_scene_image':([C.c_void_p,C.c_void_p,C.c_int,C.c_int],C.c_int),
            'pocket_scene_window':([C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_uint,C.c_int,C.c_uint],C.c_void_p),
            'pocket_scene_window_patch':([C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_int,C.c_int,C.c_void_p,C.c_uint,C.c_uint],C.c_int),
            'pocket_scene_upload':([C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_int],C.c_void_p),
            'pocket_scene_layer':([C.c_void_p,C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint,C.c_int,C.c_int,C.c_uint,C.c_uint],C.c_int),
            'pocket_scene_present':([C.c_void_p,C.c_int],C.c_int),
            'pocket_scene_capture':([C.c_void_p,C.c_void_p,C.c_size_t],C.c_int),
            'pocket_scene_stats':([C.c_void_p,C.c_void_p],C.c_int),
            'pocket_scene_texture_free':([C.c_void_p],None),
            'pocket_scene_close':([C.c_void_p],None),
        }
        for name,(args,result) in declarations.items():
            fn=getattr(self.lib,name);fn.argtypes=args;fn.restype=result
        if self.display is None:
            self.lib.pocket_window_open_hidden.argtypes=[C.c_int];self.lib.pocket_window_open_hidden.restype=C.c_void_p
            self.hidden=self.lib.pocket_window_open_hidden(-1);window=self.hidden
        else:window=self.display.handle
        self.handle=self.lib.pocket_scene_open(window,int(platform.require_gpu))
        if not self.handle:raise RuntimeError('Native GPU scene context unavailable')
        self.maps=OrderedDict();self.layers={};self.images={};self.image_rects=[];self.last_size=None
        r=platform.renderer
        self.check(self.lib.pocket_scene_font(self.handle,r.font_codes,r.font_bits,len(r.font_codes),r.coverage_codes,r.coverage_bits,len(r.coverage_codes)))
        r.lib.pocket_mbx_cell_colors.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t]
        r.lib.pocket_mac_layer_view.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p]
        self.backend=self.lib.pocket_scene_backend(self.handle).decode()
    def check(self,result):
        if result:
            self.lib.pocket_window_error.restype=C.c_char_p
            raise RuntimeError(self.lib.pocket_window_error().decode())
    def release(self,handle):
        if handle:self.lib.pocket_scene_texture_free(handle)
    def texture(self,source,defer):
        if len(source.terrain)!=source.sample_width*source.sample_height:raise ValueError('Semantic terrain sample dimensions differ')
        key=(id(source),bool(defer));cached=self.maps.get(key)
        if cached and cached[0] is source:self.maps.move_to_end(key);return cached[1]
        terrain=(C.c_uint32*len(source.terrain)).from_buffer(source.terrain)
        target=self.lib.pocket_scene_map(self.handle,terrain,source.width,source.height,source.sample_width,source.sample_height)
        if not target:raise RuntimeError('Native GPU terrain texture rejected')
        try:
            for color,points in source.lines:
                data=(C.c_double*len(points)).from_buffer(points)
                rgb=(color[0]<<16)|(color[1]<<8)|color[2]
                self.check(self.lib.pocket_scene_lines(self.handle,target,data,len(points)//4,rgb))
            self.check(self.lib.pocket_scene_marks(self.handle,target,source.marks,len(source.marks),int(defer)))
        except BaseException:self.release(target);raise
        self.maps[key]=(source,target)
        while len(self.maps)>2:self.release(self.maps.popitem(last=False)[1][1])
        return target
    def upload(self,source,w,h,key,alpha=False):
        cache=self.layers if alpha else self.images;prior=cache.get(key)
        if prior and isinstance(source,bytes) and prior[0] is source:return prior[1]
        pointer=source if isinstance(source,C.Array) else C.c_char_p(source) if isinstance(source,bytes) else (C.c_ubyte*len(source)).from_buffer(source)
        target=self.lib.pocket_scene_upload(self.handle,pointer,w,h,int(alpha))
        if not target:raise RuntimeError('Native GPU source texture rejected')
        if prior:self.release(prior[1])
        cache[key]=(source,target);return target
    def layer(self,window):
        from array import array
        h=self.platform.host;r=self.platform.renderer;native=h._native
        signature,plane=native.planes[window.name][:2];cols,rows=signature[:2]
        key=(signature,r.layer_key,r.layer_fallback,h.window_fill,h.window_opacity)
        app=native.cell_view(h,window,h.bounds(window))
        if app is not None:
            _,cw,ch,cx,cy=app;wx,wy,_,_=h.bounds(window)
            key+=(window.layer_generation,id(window.layer),cw,ch,cx-wx,cy-wy,h.ascii,h.glyphs.key)
        prior=self.layers.get(window.name)
        if prior and prior[0]==key:return prior[1]
        records=native.lib.export_cells(plane.pointer,array('I',range(cols*rows)))
        target=self.lib.pocket_scene_window(self.handle,C.c_char_p(records),cols,rows,r.layer_palette,len(r.layer_palette),r.layer_fallback,int(h.window_fill),round(h.window_opacity*255))
        if not target:raise RuntimeError('Native GPU window commands rejected')
        try:
            if app is not None:
                records,cw,ch,x,y=app;wx,wy,_,_=h.bounds(window)
                self.check(self.lib.pocket_scene_window_patch(self.handle,target,C.c_char_p(records),cw,ch,(x-wx)*8,(y-wy)*16,r.layer_palette,len(r.layer_palette),r.layer_fallback))
        except BaseException:self.release(target);raise
        if prior:self.release(prior[1])
        self.layers[window.name]=(key,target);return target
    def cells(self,defer,dirty):
        r=self.platform.renderer;cols,rows=r.size
        size=(cols*8,rows*16)
        self.check(self.lib.pocket_scene_size(self.handle,*size))
        if dirty or size!=self.last_size:
            data=(C.c_uint32*(cols*rows*2))()
            self.check(r.lib.pocket_mbx_cell_colors(r.handle,data,len(data)))
            self.check(self.lib.pocket_scene_cells(self.handle,data,cols,rows,int(defer)))
            self.last_size=size
        self.check(self.lib.pocket_scene_begin(self.handle))
    def native_scene(self,app):
        """Only admit commands when the backend explicitly supplies the sink.

        A missing sink keeps the established image path. A failed admitted
        command propagates; it must never silently rasterize through the CPU.
        """
        draw=self.lib.pocket_scene_room if self.native_room else None
        producer=getattr(app,'render_scene',None)
        if draw is None or producer is None:return None
        result=producer()
        if result is None:return ()
        source,x,y=result
        if not isinstance(source,RoomScene):raise TypeError('Unsupported native scene')
        bind=self.lib.pocket_scene_room_source
        bind.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p];bind.restype=C.c_int
        binding=(C.cast(app.lib.pocket_room_draw_tile,C.c_void_p).value,C.cast(app.lib.pocket_room_set_eye_height,C.c_void_p).value)
        if self.room_binding is None:
            self.check(bind(self.handle,*binding));self.room_binding=binding
            region=getattr(self.lib,'pocket_scene_room_region_source',None)
            producer=getattr(app.lib,'pocket_room_draw_region',None)
            if region is not None and producer is not None:
                region.argtypes=[C.c_void_p,C.c_void_p];region.restype=C.c_int
                self.check(region(self.handle,C.cast(producer,C.c_void_p).value))
        elif self.room_binding!=binding:raise RuntimeError('Room producer changed within the rendering session')
        draw.argtypes=[C.c_void_p,C.c_void_p]+[C.c_float]*6;draw.restype=C.c_int
        prior=self.images.get(app.name)
        if prior and prior[0] is source:
            target=prior[1]
        else:
            create=self.lib.pocket_scene_room_create
            create.argtypes=[C.c_void_p,C.c_uint,C.c_uint];create.restype=C.c_void_p
            reuse=prior and isinstance(prior[0],RoomScene) and (prior[0].width,prior[0].height)==(source.width,source.height)
            target=prior[1] if reuse else create(self.handle,source.width,source.height)
            if not target:raise RuntimeError('Native GPU Room target rejected')
            wall=time.monotonic_ns();cpu=time.process_time_ns()
            jobs=draw(self.handle,target,source.age,source.x,source.z,source.yaw,source.pitch,source.eye_height)
            if jobs<0:
                if not reuse:self.release(target)
                raise RuntimeError('Native GPU Room scene rejected')
            if prior and not reuse:self.release(prior[1])
            self.images[app.name]=(source,target)
            app.stats.update(last_pixel_wall_ns=time.monotonic_ns()-wall,last_pixel_cpu_ns=time.process_time_ns()-cpu)
            # This submits retained scene state; GPU execution can be deferred until
            # composition. Only the driver can count completed hardware jobs.
            app.stats['native_scene_updates']=app.stats.get('native_scene_updates',0)+1
            app.size=(source.width,source.height);app.pixel_frames+=1;app.pixel_dirty=False
        self.check(self.lib.pocket_scene_image(self.handle,target,x,y))
        return x,y,source.width,source.height
    def compose(self,apps,defer):
        h=self.platform.host;r=self.platform.renderer
        from core import STYLES
        windows=[w for w in h.windows if h.shown(w)]
        h._native.prepare(h,windows,STYLES)
        by_name={app.name:app for app in apps};covered=[];self.image_rects=[];active_layers=set();active_images=set();active_maps=set()
        dx,dy={'SE':(1,1),'S':(0,1),'SW':(-1,1),'W':(-1,0),'NW':(-1,-1),'N':(0,-1),'NE':(1,-1),'E':(1,0)}[h.shadow_direction]
        ox,oy=h.origin
        for window in windows:
            x,y,_,_=h.bounds(window);x=(x+ox)*8;y=(y+oy)*16
            if getattr(self,'native_pixels',False):
                self.draw_window(window,x,y,round(dx*h.shadow_size*8),round(dy*h.shadow_size*16))
            elif covered:
                active_layers.add(window.name);layer=self.layer(window)
                for clip in covered:self.check(self.lib.pocket_scene_layer(self.handle,layer,x,y,round(dx*h.shadow_size*8),round(dy*h.shadow_size*16),round(h.shadow_opacity*255) if h.shadow_enabled else 0,*clip))
            app=by_name.get(window.name)
            if app is None:continue
            native=self.native_scene(app)
            if native==():continue
            if native is not None:
                active_images.add(app.name);rect=native
            else:
                result=app.render_image()
                if result is None:continue
                source,px,py,w,height=result
                if isinstance(source,MapScene):
                    active_maps.add((id(source),bool(defer)));texture=self.texture(source,defer)
                else:
                    active_images.add(app.name);texture=self.upload(source,w,height,app.name)
                self.check(self.lib.pocket_scene_image(self.handle,texture,px,py))
                rect=(px,py,w,height)
            self.image_rects.append(rect);pieces=[rect]
            for prior in covered:pieces=[part for piece in pieces for part in subtract(piece,prior)]
            covered.extend(pieces)
        for cache,active in ((self.layers,active_layers),(self.images,active_images),(self.maps,active_maps)):
            for key in set(cache)-active:self.release(cache.pop(key)[1])
        overlays=[]
        if (covered or getattr(self,'native_pixels',False)) and h.launcher_lines and 'launcher' in h._native.overlays:
            cols,rows,plane,_=h._native.overlays['launcher'];x,y,_,_=h.launcher_bounds()
            overlays.append((plane.pointer,cols,rows,(x+ox)*8,(y+oy)*16,1,False))
        if (covered or getattr(self,'native_pixels',False)) and h._native.outline_layer is not None:
            pointer,x,y=h._native.outline_layer;cols,rows,_=h._native.outline_plane[0]
            overlays.append((pointer,cols,rows,(x+ox)*8,(y+oy)*16,0,True))
        for pointer,cols,rows,x,y,fill,outline in overlays:
            records=overlay_records(h._native.lib,pointer,cols,rows,outline)
            if getattr(self,'native_pixels',False):
                self.draw_records(records,cols,rows,x,y,fill,255);continue
            target=self.lib.pocket_scene_window(self.handle,C.c_char_p(records),cols,rows,r.layer_palette,len(r.layer_palette),r.layer_fallback,fill,255)
            if not target:raise RuntimeError('Native GPU overlay commands rejected')
            try:
                for clip in covered:self.check(self.lib.pocket_scene_layer(self.handle,target,x,y,0,0,0,*clip))
            finally:self.release(target)
    def present(self,text):self.check(self.lib.pocket_scene_present(self.handle,int(text)))
    def capture(self):
        w,h=self.platform.renderer.size;data=bytearray(w*8*h*16*2);out=(C.c_ubyte*len(data)).from_buffer(data)
        self.check(self.lib.pocket_scene_capture(self.handle,out,len(data)));return data
    def status(self):
        out=(C.c_uint64*5)();self.check(self.lib.pocket_scene_stats(self.handle,out))
        result=dict(backend=self.backend,**dict(zip(('frames','map_builds','line_segments','diagnostic_readbacks','source_upload_bytes'),out)))
        extra=getattr(self.lib,'pocket_scene_transfer_stats',None)
        if extra is not None:
            extra.argtypes=[C.c_void_p,C.c_void_p];extra.restype=C.c_int;values=(C.c_uint64*7)()
            self.check(extra(self.handle,values))
            result['frontend_transfers']=dict(zip(('owner_checks','owner_rejects','make_current_calls','target_switches','readback_calls','readback_bytes','presentation_bytes'),values))
            result['driver_materialization']='requires separate Mesa/kernel counters'
        return result
    def close(self):
        for _,handle in self.maps.values():self.release(handle)
        for cache in (self.layers,self.images):
            for _,handle in cache.values():self.release(handle)
            cache.clear()
        self.maps.clear()
        if self.handle:self.lib.pocket_scene_close(self.handle);self.handle=None
    def close_window(self):
        if self.hidden:
            self.lib.pocket_window_close.argtypes=[C.c_void_p];self.lib.pocket_window_close(self.hidden);self.hidden=None
