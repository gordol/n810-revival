"""Colored analytic vortex ribbons over a retained nebula; no particle history."""
import math
from functools import lru_cache
from paint import ink,Scene


@lru_cache(maxsize=8)
def plan(seed):
    from effects import sample
    return tuple((sample(i,seed,31)*math.tau,.35+sample(i,seed,32)*.65,
                  .20+sample(i,seed,33)*.55,i%4) for i in range(1024))


@lru_cache(maxsize=4)
def backdrop(width,height):
    sw,sh=min(96,width),min(48,height)
    small={}
    for y in range(sh):
        for x in range(sw):
            u,v=x/max(1,sw-1),y/max(1,sh-1)
            a=(.5+.5*math.sin(u*6+v*3))**2
            b=(.5+.5*math.cos(u*4-v*7))**2
            glow=math.exp(-((u-.52)**2+(v-.5)**2)*5)
            upper=(7+17*b*glow,8+24*a*glow,15+25*b*glow)
            lower=tuple(c+1.5*glow for c in upper)
            small[x,y]=('▄',ink(*lower,background=upper))
    return {(x,y):small[min(sw-1,x*sw//width),min(sh-1,y*sh//height)] for y in range(height) for x in range(width)}


def frame(width,height,step,ascii=False,seed=0,strands=48,sway=.6,speed_scale=1.0):
    time=step/24*speed_scale;count=max(8,min(192,int(strands)));pixels={}
    colors=((45,170,125),(113,105,200),(195,117,68),(80,175,193))
    for phase,radius,speed,group in plan(seed)[:count]:
        previous=None
        for trail in range(20):
            t=time-trail*.035
            angle=phase+t*speed*(1 if group%2 else -1)
            twist=math.sin(t*.21+phase*2)*.28*(sway/.6)
            cx=.5+.11*math.sin(t*.07+group*1.7)
            cy=.5+.10*math.cos(t*.08+group)
            depth=.55+.45*math.sin(phase+t*.11)**2
            point=((cx+math.cos(angle+twist)*radius*.47*depth)*width,
                   (cy+math.sin(angle*1.01)*radius*.46*depth)*height)
            strength=(1-trail/21)*(.35+.65*depth)
            points=(point,) if previous is None else (point,((point[0]+previous[0])/2,(point[1]+previous[1])/2))
            for px,py in points:
                for offset,glow in ((0,1),(-1,.22),(1,.22)):
                    x,y=int(px)+offset,int(py)
                    if not 0<=x<width or not 0<=y<height:continue
                    if (x,y) not in pixels and len(pixels)>=16384:continue
                    old=pixels.get((x,y),(0,0,0))
                    pixels[x,y]=tuple(min(215,a+b*strength*glow*.32) for a,b in zip(old,colors[group]))
            previous=point
    base=backdrop(width,height);overlay={}
    for xy,rgb in pixels.items():
        under=base[xy][1];bg=((under>>16)&255,(under>>8)&255,under&255)
        upper=tuple(min(220,a+b*.45) for a,b in zip(bg,rgb))
        lower=tuple(min(230,a+b) for a,b in zip(bg,rgb))
        overlay[xy]=(':' if ascii else '▄',ink(*lower,background=upper))
    if ascii:
        base=ascii_backdrop(width,height)
    return Scene(base,overlay)


@lru_cache(maxsize=4)
def ascii_backdrop(width,height):return {xy:(' ',color) for xy,(_,color) in backdrop(width,height).items()}
