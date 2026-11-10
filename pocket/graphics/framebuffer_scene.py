# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""RGB565 presentation of shared semantic scenes on an owned framebuffer."""
from collections import OrderedDict
from pathlib import Path
import ctypes as C
from scenes import MapScene,RasterScene

class Context:
    report_key='framebuffer_scene'
    def __init__(self,platform):
        self.platform=platform;self.renderer=platform.renderer;self.maps=OrderedDict()
        self.frame=None;self.compositor=None;self.image_rects=[];self.frames=0;self.map_builds=0
        self.backend='framebuffer';self.renderer_description=self.renderer.renderer_name+'; framebuffer presenter'
        self.lib=self.renderer.lib
        for name,args in (
            ('pocket_map_base',[C.c_void_p,C.c_size_t,C.c_void_p,C.c_uint,C.c_uint]),
            ('pocket_map_lines',[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_uint]),
            ('pocket_map_marks',[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_void_p])):
            getattr(self.lib,name).argtypes=args
    def direct(self):return False
    def raster(self,scene):
        prior=self.maps.get(id(scene))
        if prior and prior[0] is scene:return prior[1]
        width,height=scene.width,scene.height
        if (scene.sample_width,scene.sample_height)!=(width,height*2):raise ValueError('Framebuffer map requires two terrain samples per cell')
        if len(scene.terrain)!=width*height*2:raise ValueError('Semantic terrain sample dimensions differ')
        samples=(C.c_uint32*len(scene.terrain)).from_buffer(scene.terrain)
        pixels=(C.c_uint16*(width*8*height*16))();capacity=len(pixels)
        if self.lib.pocket_map_base(pixels,capacity,samples,width,height):raise ValueError('Framebuffer terrain rejected')
        for color,points in scene.lines:
            rgb=((color[0]>>3)<<11)|((color[1]>>2)<<5)|(color[2]>>3)
            data=(C.c_double*len(points)).from_buffer(points)
            if self.lib.pocket_map_lines(pixels,capacity,width*8,height*16,data,len(points)//4,rgb):raise ValueError('Framebuffer vectors rejected')
        masks=b''.join(self.renderer.font.glyph(chr(mark.ch)) for mark in scene.marks)
        if self.lib.pocket_map_marks(pixels,capacity,width,height,scene.marks,len(scene.marks),C.c_char_p(masks)):raise ValueError('Framebuffer labels rejected')
        self.maps[id(scene)]=(scene,pixels);self.maps.move_to_end(id(scene))
        while len(self.maps)>2:self.maps.popitem(last=False)
        self.map_builds+=1;return pixels
    def prepare_scene(self,scene):return RasterScene(scene,self.raster(scene))
    def cells(self,defer,dirty):
        if dirty:self.renderer.finish()
        self.frame=bytearray(self.renderer.pixels)
    def compose(self,apps,defer):
        context=self
        class View:
            def __init__(self,owner):object.__setattr__(self,'owner',owner)
            def __getattr__(self,name):return getattr(self.owner,name)
            def __setattr__(self,name,value):setattr(self.owner,name,value)
            def render_image(self):
                result=self.owner.render_image()
                if result is None:return None
                source,x,y,width,height=result
                if isinstance(source,RasterScene):source=source.pixels
                elif isinstance(source,MapScene):source=context.raster(source)
                return source,x,y,width,height
        self.image_rects=[]
        if not apps:return
        if self.compositor is None:
            from pixel_compositor import Compositor
            self.compositor=Compositor(self.platform.host,self.renderer,Path(self.platform.library).resolve().parent/'room-pixels.so')
        self.compositor.compose(self.frame,[View(app) for app in apps]);self.image_rects=self.compositor.image_rects
    def present(self,text):
        self.platform.display.present(self.frame);self.frames+=1
    def capture(self):return self.frame
    def status(self):return dict(backend=self.backend,frames=self.frames,map_builds=self.map_builds,pixel_composition='CPU reference')
    def close(self):
        if self.compositor:self.compositor.close();self.compositor=None
        self.maps.clear();self.frame=None
    def close_window(self):pass
