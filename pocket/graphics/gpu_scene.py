# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Accelerated native scene rasterization and composition on one SDL renderer."""
from collections import OrderedDict
from pathlib import Path
import ctypes as C
from scenes import MapScene


def subtract(rect,cut):
    x,y,w,h=rect;a,b,c,d=cut
    left,top,right,bottom=max(x,a),max(y,b),min(x+w,a+c),min(y+h,b+d)
    if left>=right or top>=bottom:return [rect]
    return [r for r in ((x,y,w,top-y),(x,bottom,w,y+h-bottom),(x,top,left-x,bottom-top),(right,top,x+w-right,bottom-top)) if r[2]>0 and r[3]>0]

def backdrop_rect(x,y,width,height,shift):
    """The coarse and detailed map share the same drag translation."""
    return x-width//2+shift[0],y-height//2+shift[1],width*2,height*2


class Context:
    def __init__(self,platform):
        self.platform=platform;self.display=platform.display;self.hidden=None
        self.lib=C.CDLL(str(Path(platform.library).resolve().parent/'window.so'))
        declarations={
            'pocket_scene_open':([C.c_void_p,C.c_int],C.c_void_p),
            'pocket_scene_backend':([C.c_void_p],C.c_char_p),
            'pocket_scene_font':([C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint,C.c_void_p,C.c_void_p,C.c_uint],C.c_int),
            'pocket_scene_size':([C.c_void_p,C.c_uint,C.c_uint],C.c_int),
            'pocket_scene_cells':([C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_int],C.c_int),
            'pocket_scene_begin':([C.c_void_p],C.c_int),
            'pocket_scene_map':([C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_uint,C.c_int],C.c_void_p),
            'pocket_scene_blank':([C.c_void_p,C.c_uint,C.c_uint],C.c_void_p),
            'pocket_scene_lines':([C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint,C.c_uint],C.c_int),
            'pocket_scene_marks':([C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint,C.c_int],C.c_int),
            'pocket_scene_image':([C.c_void_p,C.c_void_p,C.c_int,C.c_int],C.c_int),
            'pocket_scene_image_region':([C.c_void_p,C.c_void_p,*([C.c_int]*12)],C.c_int),
            'pocket_scene_fill':([C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_int,C.c_uint],C.c_int),
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
        self.maps=OrderedDict();self.overlays=OrderedDict();self.layers={};self.images={};self.image_rects=[];self.last_size=None
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
        target=self.lib.pocket_scene_map(self.handle,terrain,source.width,source.height,source.sample_width,source.sample_height,int(source.smooth))
        if not target:raise RuntimeError('Native GPU terrain texture rejected')
        try:
            for color,points in source.lines:
                data=(C.c_double*len(points)).from_buffer(points)
                rgb=(color[0]<<16)|(color[1]<<8)|color[2]
                self.check(self.lib.pocket_scene_lines(self.handle,target,data,len(points)//4,rgb))
            self.check(self.lib.pocket_scene_marks(self.handle,target,source.marks,len(source.marks),int(defer)))
        except BaseException:self.release(target);raise
        self.maps[key]=(source,target)
        while len(self.maps)>4:self.release(self.maps.popitem(last=False)[1][1])
        return target
    def overlay(self,source,defer):
        key=(id(source),bool(defer));cached=self.overlays.get(key)
        if cached and cached[0] is source:self.overlays.move_to_end(key);return cached[1]
        target=self.lib.pocket_scene_blank(self.handle,source.width,source.height)
        if not target:raise RuntimeError('Native GPU map overlay rejected')
        try:
            for color,points in source.overlay_lines:
                data=(C.c_double*len(points)).from_buffer(points)
                rgb=(color[0]<<16)|(color[1]<<8)|color[2]
                self.check(self.lib.pocket_scene_lines(self.handle,target,data,len(points)//4,rgb))
            marks=source.overlay_marks
            self.check(self.lib.pocket_scene_marks(self.handle,target,marks,len(marks),int(defer)))
        except BaseException:self.release(target);raise
        self.overlays[key]=(source,target)
        while len(self.overlays)>6:self.release(self.overlays.popitem(last=False)[1][1])
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
        app=native.cell_planes.get(window.name)
        if app is not None:key+=(app[0],id(window.layer),window.version)
        prior=self.layers.get(window.name)
        if prior and prior[0]==key:return prior[1]
        records=native.lib.export_cells(plane.pointer,array('I',range(cols*rows)))
        target=self.lib.pocket_scene_window(self.handle,C.c_char_p(records),cols,rows,r.layer_palette,len(r.layer_palette),r.layer_fallback,int(h.window_fill),round(h.window_opacity*255))
        if not target:raise RuntimeError('Native GPU window commands rejected')
        try:
            if app is not None and not window.rolled:
                cell=native.cell_plane(h,window,h.bounds(window),range(h.width*h.height),set(),{})
                if cell is not None:
                    pointer,x,y=cell;cw,ch=native.cell_planes[window.name][0][:2];wx,wy,_,_=h.bounds(window)
                    records=native.lib.export_cells(pointer,array('I',range(cw*ch)))
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
    def compose(self,apps,defer):
        h=self.platform.host;r=self.platform.renderer
        self.drag_terrain_planes=0
        from core import STYLES
        h._native.prepare(h,[w for w in h.windows if h.shown(w)],STYLES)
        by_name={app.name:app for app in apps};covered=[];self.image_rects=[];active_layers=set();active_images=set();active_maps=set();active_overlays=set()
        dx,dy={'SE':(1,1),'S':(0,1),'SW':(-1,1),'W':(-1,0),'NW':(-1,-1),'N':(0,-1),'NE':(1,-1),'E':(1,0)}[h.shadow_direction]
        ox,oy=h.origin
        for window in h.windows:
            if not h.shown(window):continue
            x,y,_,_=h.bounds(window);x=(x+ox)*8;y=(y+oy)*16
            if covered:
                active_layers.add(window.name);layer=self.layer(window)
                for clip in covered:self.check(self.lib.pocket_scene_layer(self.handle,layer,x,y,round(dx*h.shadow_size*8),round(dy*h.shadow_size*16),round(h.shadow_opacity*255) if h.shadow_enabled else 0,*clip))
            app=by_name.get(window.name)
            if app is None:continue
            result=app.render_image()
            if result is None:continue
            source,px,py,w,height,*pan=result
            def draw_map(scene,x,y,shift=(),clip=None,native_labels=False):
                content=min(scene.width*8,scene.content_width or scene.width*8)
                region=(x,y,content,scene.height*16) if clip is None else clip
                label_defer=bool(native_labels and clip is None)
                def draw(texture):
                    if clip is None and content==scene.width*8:
                        self.check(self.lib.pocket_scene_image(self.handle,texture,x,y))
                    else:
                        self.check(self.lib.pocket_scene_image_region(self.handle,texture,
                            0,0,content,scene.height*16,x+(shift[0] if shift else 0),
                            y+(shift[1] if shift else 0),content,scene.height*16,*region))
                continuous=clip is not None and scene.surround is not None
                if clip is not None:
                    self.check(self.lib.pocket_scene_fill(self.handle,*region,0x101818))
                    if continuous:
                        backdrop=scene.surround;active_maps.add((id(backdrop),False))
                        self.drag_terrain_planes+=1
                        self.check(self.lib.pocket_scene_image_region(self.handle,self.texture(backdrop,False),
                            0,0,backdrop.width*8,backdrop.height*16,
                            *backdrop_rect(x,y,content,scene.height*16,shift),*region))
                if not continuous:
                    base=scene.base or scene
                    base_defer=label_defer if scene.base is None else False
                    active_maps.add((id(base),base_defer))
                    if clip is not None:self.drag_terrain_planes+=1
                    draw(self.texture(base,base_defer))
                    forest=scene.forest_overlay
                    if forest is not None:
                        active_overlays.add((id(forest),False))
                        if scene.forest_visible:
                            draw(self.overlay(forest,False))
                    if scene.base is not None and (len(scene.overlay_marks) or scene.overlay_lines):
                        active_overlays.add((id(scene),label_defer))
                        draw(self.overlay(scene,label_defer))
                if continuous and scene.drag_labels is not None:
                    active_overlays.add((id(scene.drag_labels),False))
                    draw(self.overlay(scene.drag_labels,False))
            if isinstance(source,MapScene):
                native_labels=bool(defer and not pan and getattr(app,'presentation_marks',lambda:None)())
                draw_map(source,px,py,pan,(px,py,min(w,source.content_width or w),height) if pan else None,native_labels)
            else:
                active_images.add(app.name)
                texture=self.upload(source,w,height,app.name)
                self.check(self.lib.pocket_scene_image(self.handle,texture,px,py))
            if isinstance(source,MapScene):
                for inset,offset_x,offset_y in source.insets:
                    draw_map(inset,px+offset_x,py+offset_y)
                    self.image_rects.append((px+offset_x,py+offset_y,inset.width*8,inset.height*16))
            rect=(px,py,w,height);self.image_rects.append(rect);pieces=[rect]
            for prior in covered:pieces=[part for piece in pieces for part in subtract(piece,prior)]
            covered.extend(pieces)
        for cache,active in ((self.layers,active_layers),(self.images,active_images),(self.maps,active_maps),(self.overlays,active_overlays)):
            for key in set(cache)-active:self.release(cache.pop(key)[1])
        overlays=[]
        if covered and h.launcher_lines and 'launcher' in h._native.overlays:
            cols,rows,plane,_=h._native.overlays['launcher'];x,y,_,_=h.launcher_bounds()
            overlays.append((plane.pointer,cols,rows,(x+ox)*8,(y+oy)*16,1))
        if covered and h._native.outline_layer is not None:
            pointer,x,y=h._native.outline_layer;cols,rows,_=h._native.outline_plane[0]
            overlays.append((pointer,cols,rows,(x+ox)*8,(y+oy)*16,0))
        from array import array
        for pointer,cols,rows,x,y,fill in overlays:
            records=h._native.lib.export_cells(pointer,array('I',range(cols*rows)))
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
        return dict(backend=self.backend,**dict(zip(('frames','map_builds','line_segments','diagnostic_readbacks','source_upload_bytes'),out)))
    def close(self):
        for _,handle in self.maps.values():self.release(handle)
        for _,handle in self.overlays.values():self.release(handle)
        for cache in (self.layers,self.images):
            for _,handle in cache.values():self.release(handle)
            cache.clear()
        self.maps.clear();self.overlays.clear()
        if self.handle:self.lib.pocket_scene_close(self.handle);self.handle=None
    def close_window(self):
        if self.hidden:
            self.lib.pocket_window_close.argtypes=[C.c_void_p];self.lib.pocket_window_close(self.hidden);self.hidden=None
