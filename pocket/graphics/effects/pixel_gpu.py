# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exact integer RGB565 source-over and shadows on Metal."""
import ctypes as C
import threading

class PixelGPU:
    def __init__(self):
        import mlx.core as mx
        import numpy as np
        self.mx=mx;self.np=np;self.lock=threading.RLock();self.stats=dict(backend='Metal integer RGB565 source-over',layers=0,pixels=0)
    def over(self,dst,source,alpha):
        mx=self.mx;inv=255-alpha
        r=(((source>>11)&31)*alpha+(dst>>11)*inv+127)//255
        g=(((source>>5)&63)*alpha+((dst>>5)&63)*inv+127)//255
        b=((source&31)*alpha+(dst&31)*inv+127)//255
        return (r<<11)|(g<<5)|b
    def layer(self,compositor,canvas,coverage,handle,x,y,sx,sy,shadow):
        mx,np=self.mx,self.np;w,h=C.c_uint(),C.c_uint();pointer=C.POINTER(C.c_uint32)()
        view=compositor.lib.pocket_mac_layer_view
        view.argtypes=[C.c_void_p,C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.POINTER(C.POINTER(C.c_uint32))]
        if view(handle,C.byref(w),C.byref(h),C.byref(pointer)):raise ValueError('Native layer view rejected')
        cw,ch=compositor.renderer.size;cw*=8;ch*=16
        if not(-cw<=x<=cw and -ch<=y<=ch and -cw<=sx<=cw and -ch<=sy<=ch and 0<=shadow<=255):raise ValueError('Invalid Metal layer bounds')
        left=max(0,min(x,x+sx));right=min(cw,max(x+w.value,x+sx+w.value));top=max(0,min(y,y+sy));bottom=min(ch,max(y+h.value,y+sy+h.value))
        if left>=right or top>=bottom:return 0
        target=np.ctypeslib.as_array(C.cast(canvas,C.POINTER(C.c_uint16)),shape=(cw*ch,)).reshape(ch,cw)
        mask=np.ctypeslib.as_array(C.cast(coverage,C.POINTER(C.c_ubyte)),shape=(cw*ch,)).reshape(ch,cw)
        pixels=np.ctypeslib.as_array(pointer,shape=(w.value*h.value,)).reshape(h.value,w.value)
        with self.lock,mx.stream(mx.gpu):
            dst=mx.array(target[top:bottom,left:right].astype(np.uint32));covered=mx.array(mask[top:bottom,left:right]>0)
            xx=mx.arange(left,right)[None,:];yy=mx.arange(top,bottom)[:,None]
            inside=(xx>=x)&(xx<x+w.value)&(yy>=y)&(yy<y+h.value)
            shadowed=(xx>=x+sx)&(xx<x+sx+w.value)&(yy>=y+sy)&(yy<y+sy+h.value)&~inside&covered
            if shadow:dst=mx.where(shadowed,self.over(dst,mx.zeros_like(dst),mx.array(shadow,dtype=mx.uint32)),dst)
            src=mx.array(pixels)[mx.clip(yy-y,0,h.value-1),mx.clip(xx-x,0,w.value-1)]
            out=mx.where(inside&covered,self.over(dst,src&65535,(src>>16)&255),dst)
            mx.eval(out);target[top:bottom,left:right]=np.array(out).astype(np.uint16)
        self.stats['layers']+=1;self.stats['pixels']+=(right-left)*(bottom-top)
        return 0
    def install(self,platform):
        import pixel_compositor
        original=pixel_compositor.Compositor;backend=self
        class Compositor(original):
            def __init__(self,*args,**kwargs):
                super().__init__(*args,**kwargs)
                self.lib.pocket_pixel_layer_over=lambda *a:backend.layer(self,*a)
            def layer(self,w):
                if w.name not in self.host._native.planes:
                    from core import STYLES
                    self.host._native.prepare(self.host,[view for view in self.host.windows if self.host.shown(view)],STYLES)
                return super().layer(w)
            def gpu_compose(self,canvas,apps):return False
        pixel_compositor.Compositor=Compositor
        return lambda:setattr(pixel_compositor,'Compositor',original)
