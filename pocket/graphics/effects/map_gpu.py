# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exact integer Metal sampling and vector shading for native station maps."""
from array import array
from concurrent.futures import CancelledError
import math,threading

class MapGPU:
    def __init__(self):
        import mlx.core as mx
        import numpy as np
        if not mx.metal.is_available():raise RuntimeError('Metal map compute unavailable')
        self.mx=mx;self.np=np;self.lock=threading.RLock();self.sources={}
        self.stats=dict(backend='Metal',sample_frames=0,halfcell_samples=0,vector_frames=0,vector_cells=0,cpu_projection_coordinates=0)
    def sample(self,view,layers,cancel=lambda:False):
        with self.lock:return self._sample(view,layers,cancel)
    def _sample(self,view,layers,cancel):
        mx,np=self.mx,self.np;width,height=view.width,view.height;used=[]
        with mx.stream(mx.gpu):
            pixels=mx.zeros((height*2,width),dtype=mx.uint32);covered=mx.zeros((height*2,width),dtype=mx.bool_)
            for name,source,values in layers:
                if cancel():raise CancelledError()
                xs=[];ys=[]
                for x in range(width):
                    lon=view.center[1]+(x-(width-1)/2)*view.span/max(1,width-1)/111.32/math.cos(math.radians(view.center[0]))
                    xs.append(round(source.project(lon,view.center[0])[0]))
                for y in range(height*2):
                    lat=view.center[0]-(y-(height*2-1)/2)*view.span/max(1,width-1)/111.32
                    ys.append(round((source.center[0]-lat)*111.32*(source.width-1)/source.span+(source.height*2-1)/2))
                self.stats['cpu_projection_coordinates']+=len(xs)+len(ys)
                key=id(values);entry=self.sources.get(key)
                if entry is None or entry[0] is not values:
                    data=mx.array(np.frombuffer(values,dtype=np.uint32).reshape(source.height,source.width,2).transpose(0,2,1).reshape(source.height*2,source.width))
                    self.sources[key]=(values,data)
                    if len(self.sources)>8:self.sources.pop(next(iter(self.sources)))
                else:data=entry[1]
                xx=mx.array(xs,dtype=mx.int32);yy=mx.array(ys,dtype=mx.int32)
                valid=(xx[None,:]>=0)&(xx[None,:]<source.width)&(yy[:,None]>=0)&(yy[:,None]<source.height*2)
                sampled=data[mx.clip(yy,0,source.height*2-1)[:,None],mx.clip(xx,0,source.width-1)[None,:]]
                pixels=mx.where(valid,sampled,pixels);covered=covered|valid
                if bool(mx.any(valid).item()):used.append(name)
            if not bool(mx.all(covered).item()):raise ValueError('No prepared terrain covers this view')
            mx.eval(pixels);data=np.array(pixels).reshape(height,2,width).transpose(0,2,1).reshape(-1,2)
        if cancel():raise CancelledError()
        self.stats['sample_frames']+=1;self.stats['halfcell_samples']+=width*height*2
        return [(' ' if a==b else '▀',(1<<48)|(int(a)<<24)|int(b)) for a,b in data],used
    def vectors(self,engine,view,result,roads=True):
        with self.lock:return self._vectors(engine,view,result,roads)
    def _vectors(self,engine,view,result,roads):
        mx,np=self.mx,self.np
        lines,_=engine._lines(view) if roads else ({},0);streams,_=engine._lines(view,True)
        m=view.ground_m_per_halfcell;opacity={0:round(256*max(0,min(1,(150-m)/120))),1:256,2:round(256*max(0,min(1,(250-m)/200)))}
        total=0
        for marks,water in ((lines,False),(streams,True)):
            ids=[];chars=[];background=[];alpha=[];targets=[]
            for (x,y),(char,role) in marks.items():
                if not opacity[role]:continue
                i=y*view.width+x;ids.append(i);chars.append(char);background.append(result[i][1]&0xffffff);alpha.append(opacity[role]);targets.append(engine.rgb.CREEK if water else (173,181,159) if role==0 else (218,222,207))
            if not ids:continue
            with mx.stream(mx.gpu):
                bg=mx.array(background,dtype=mx.uint32);a=mx.array(alpha,dtype=mx.uint32)[:,None];target=mx.array(targets,dtype=mx.uint32)
                rgb=mx.stack(((bg>>16)&255,(bg>>8)&255,bg&255),axis=1)
                fg=(rgb*(256-a)+target*a+128)//256
                levels=mx.array((31,63,31),dtype=mx.uint32)
                def quant(c):
                    n=c*levels;q=n//255;tail=n%255;q=q+(tail*2>255).astype(mx.uint32)
                    n=q*255;q=n//levels;tail=n%levels
                    return q+((tail*2>levels)|((tail*2==levels)&((q&1)>0))).astype(mx.uint32)
                fg=quant(fg);rgb=quant(rgb)
                packed=(fg[:,0]<<16)|(fg[:,1]<<8)|fg[:,2];back=(rgb[:,0]<<16)|(rgb[:,1]<<8)|rgb[:,2]
                mx.eval(packed,back);f,b=np.array(packed),np.array(back)
            for i,char,front,back in zip(ids,chars,f,b):result[i]=(char,(1<<48)|(int(front)<<24)|int(back))
            total+=len(ids)
        self.stats['vector_frames']+=1;self.stats['vector_cells']+=total
        return len(lines),len(streams)
    def dem_shade(self,heights,metres):
        mx,np=self.mx,self.np;filled=np.where(np.isfinite(heights),heights,0);m=max(.1,metres)
        with self.lock,mx.stream(mx.gpu):
            z=mx.array(filled.astype(np.float32))
            gx=mx.concatenate(((z[:,1:2]-z[:,:1])/m,(z[:,2:]-z[:,:-2])/(2*m),(z[:,-1:]-z[:,-2:-1])/m),axis=1)
            gy=mx.concatenate(((z[1:2]-z[:1])/m,(z[2:]-z[:-2])/(2*m),(z[-1:]-z[-2:-1])/m),axis=0)
            shade=mx.clip((1-gx*.8+gy*.8)/mx.sqrt(1+gx*gx+gy*gy),.4,1.3)
            stops=(-100,0,100,300,700,1500,3000,5000);colors=((23,68,60),(35,88,51),(65,106,55),(106,121,66),(142,132,96),(163,151,130),(210,206,197),(245,245,245))
            rgb=mx.broadcast_to(mx.array(colors[0],dtype=mx.float32),(*z.shape,3))
            for i in range(7):
                t=mx.clip((z-stops[i])/(stops[i+1]-stops[i]),0,1)[...,None]
                color=mx.array(colors[i],dtype=mx.float32)+(mx.array(colors[i+1],dtype=mx.float32)-mx.array(colors[i],dtype=mx.float32))*t
                rgb=mx.where((z>=stops[i])[...,None],color,rgb)
            raw=mx.clip(rgb*shade[...,None],0,255);mx.eval(raw);values=np.array(raw)
        output=values.astype(np.uint8)
        # Float32 channels close to RGB8 boundaries use canonical float64 arithmetic.
        uncertain=np.any(np.abs(values-np.rint(values))<.01,axis=-1)
        yy,xx=np.nonzero(uncertain)
        if len(xx):
            left=np.maximum(xx-1,0);right=np.minimum(xx+1,filled.shape[1]-1)
            top=np.maximum(yy-1,0);bottom=np.minimum(yy+1,filled.shape[0]-1)
            gx=(filled[yy,right]-filled[yy,left])/((right-left)*m);gy=(filled[bottom,xx]-filled[top,xx])/((bottom-top)*m)
            shade=np.clip((1-gx*.8+gy*.8)/np.sqrt(1+gx*gx+gy*gy),.4,1.3)
            precise=np.stack([np.interp(filled[yy,xx],stops,[c[i] for c in colors]) for i in range(3)],axis=-1)
            output[yy,xx]=np.clip(precise*shade[:,None],0,255).astype(np.uint8)
        self.stats['dem_frames']=self.stats.get('dem_frames',0)+1;self.stats['dem_samples']=self.stats.get('dem_samples',0)+filled.size
        self.stats['dem_precision_samples']=self.stats.get('dem_precision_samples',0)+len(xx)
        return output
    def render_dem(self,engine,view,terrain):
        import desktop_elevation as dem
        from desktop_shoreline import mask
        np=self.np
        frame,legend=engine._original_rgb_terrain(view,terrain)
        if view.width<2:return frame,legend
        water=mask(view);heights,spacing=dem.sample(view,land_mask=water!=0 if water is not None else None);known=np.isfinite(heights)
        rgb=self.dem_shade(heights,view.ground_m_per_halfcell)
        rows,_,_=engine.atlas.raster(view.center,view.span,view.width,view.height)
        for y in range(view.height):
            for x in range(view.width):
                _,a,b=frame[y*view.width+x];pair=[a,b]
                for j in (0,1):
                    yy=2*y+j;land=(water[yy,x]>0) if water is not None and water[yy,x]>=0 else rows[yy][x]!=0
                    if not land:pair[j]=engine.palette.WATER
                    elif terrain and known[yy,x]:pair[j]=tuple(map(int,rgb[yy,x]))
                    elif rows[yy][x]==0:pair[j]=engine.palette.LAND
                frame[y*view.width+x]=(' ' if pair[0]==pair[1] else '▀',*pair)
        if not terrain or not known.any():return frame,legend
        return frame,f'Local DEM · {np.nanmin(spacing[known]):.0f}–{np.nanmax(spacing[known]):.0f} m source spacing · cached desktop relief'
