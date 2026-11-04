"""Illustrative celestial sky; no live data."""
import math
from functools import lru_cache
from geometry import Vec,dot,unit,add,mul
from lighting import mix,smooth

MODES=('dynamic','day','night')


def scene_age(age,mode):
    if mode not in MODES:raise ValueError('invalid light mode')
    return 0 if mode=='day' else 35000 if mode=='night' else max(0,age)


@lru_cache(maxsize=1)
def stars():
    # Fixed sky directions, no screen-space random flickering or per-star objects.
    result=[]
    for i in range(1800):
        azimuth=i*2.39996322973
        altitude=.015+.985*((i*.75487766625)%1)
        horizontal=math.sqrt(1-altitude*altitude)
        result.append((Vec(math.sin(azimuth)*horizontal,altitude,math.cos(azimuth)*horizontal),.35+.65*((i*.61803398875)%1)))
    return tuple(result)


def sky_details(pixels,samples,model,pw,ph,env,phase=0,points=None):
    night=1-smooth(0,.20,env.sunlight)
    if night<=0:return
    camera=model.camera
    right,down,forward=camera.axes()
    def project(direction):
        depth=dot(direction,forward)
        if depth<=0:return None
        scale=camera.focal/depth if camera.focal else camera.span_x*.7/depth
        return (.5+dot(direction,right)*scale/camera.span_x)*pw,(.5+dot(direction,down)*scale/camera.span_y)*ph
    for direction,brightness in stars():
        point=project(direction)
        if point is None:continue
        x,y=map(int,point)
        if 0<=x<pw and 0<=y<ph and samples[y*pw+x] is None:
            # Distant haze extinguishes low stars; stable and restrained.
            strength=night*brightness*smooth(.01,.12,direction.y)
            color=mix(pixels[y*pw+x],(151,164,181),strength*.8)
            if points is None:pixels[y*pw+x]=color
            else:points.append((x,y,color,pixels[y*pw+x]))
    if env.moon.y>0:
        from moon import Moon,draw
        draw(pixels,samples,camera,pw,ph,Moon(env.moon,phase))
