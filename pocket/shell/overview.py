"""Bounded overview placement anchored to real window centers, never a grid."""
from functools import lru_cache


@lru_cache(maxsize=32)
def arrange(bounds,viewport,windows):
    left,top,width,height=bounds
    iw,ih=max(1,width-2),max(1,height-2)
    vw,vh=viewport
    # Try the natural fitted size first, then reduce only if all previews cannot fit.
    for factor in (1,.85,.70,.55,.40,.25,.12):
        placed={};failed=False
        for name,x,y,w,h,visible in windows:
            floor=10 if factor>=.4 else 4
            ww=min(iw,max(min(floor,iw),round(w*iw/vw*factor)))
            hh=min(ih,max(min(3 if factor>=.4 else 1,ih),round(h*ih/vh*factor)))
            if not visible:ww=min(ww,12);hh=min(hh,2)
            ax=max(0,min(iw-ww,round((x+w/2)*iw/vw-ww/2)))
            ay=max(0,min(ih-hh,round((y+h/2)*ih/vh-hh/2)))
            def free(px,py):
                return all(px+ww<=rx or rx+rw<=px or py+hh<=ry or ry+rh<=py for rx,ry,rw,rh in placed.values())
            if free(ax,ay):position=(ax,ay)
            else:
                best=None;position=None
                for py in range(ih-hh+1):
                    for px in range(iw-ww+1):
                        distance=(px-ax)**2+4*(py-ay)**2
                        if (best is None or distance<best) and free(px,py):best=distance;position=(px,py)
            if position is None:failed=True;break
            placed[name]=(*position,ww,hh)
        if not failed:return tuple((name,(left+1+x,top+1+y,w,h)) for name,(x,y,w,h) in placed.items())
    # More windows than physical cells: retain anchored headers, accepting overlap.
    return tuple((name,(left+1+min(iw-1,max(0,round(x*iw/vw))),top+1+min(ih-1,max(0,round(y*ih/vh))),1,1)) for name,x,y,w,h,_ in windows)
