"""Bounded cell-space pointer decoration; no cursor replacement or timer thread."""
from collections import deque
import colorsys
from functools import lru_cache
from paint import ink,SCENE_ROLES


@lru_cache(maxsize=1024)
def glint(char,color,glyph,rgb,strength):
    if color>=1<<48:
        foreground=tuple((color>>shift)&255 for shift in (40,32,24))
        background=tuple((color>>shift)&255 for shift in (16,8,0))
    else:foreground=SCENE_ROLES.get(color,(160,160,160));background=(18,18,18)
    amount=strength/31
    fg=tuple(round(a*(1-amount)+b*amount) for a,b in zip(foreground,rgb))
    bg=tuple(round(a*.96+b*.04*amount) for a,b in zip(background,rgb))
    return (glyph if char in (' ','▄','▀') else char),ink(*fg,background=bg)


class PointerTrail:
    duration=.6
    def __init__(self):self.points=deque(maxlen=24);self.overlay={};self.step=None
    @property
    def active(self):return bool(self.points or self.overlay)
    def move(self,x,y,now):
        if self.points and self.points[-1][:2]==(x,y):return
        self.points.append((x,y,now));self.step=None
    def update(self,now,width,height):
        step=int(now*30)
        if self.step==step:return set()
        self.step=step;old=self.overlay;new={}
        while self.points and now-self.points[0][2]>=self.duration:self.points.popleft()
        for index,(x,y,born) in enumerate(self.points):
            strength=round(31*max(0,1-(now-born)/self.duration)**2)
            if not strength:continue
            rgb=tuple(round(c*255) for c in colorsys.hsv_to_rgb((born*.35+(x+y)*.025)%1,.75,1))
            # Surround the native pointer. Never paint a replacement cursor at it.
            ring=((-1,-1,'/'),(1,-1,'\\'),(-1,1,'\\'),(1,1,'/')) if index==len(self.points)-1 else ((-1,0,'·'),)
            for dx,dy,glyph in ring:
                xx,yy=x+dx,y+dy
                if 0<=xx<width and 0<=yy<height:new[xx,yy]=(glyph,rgb,strength)
        if self.points:new.pop(self.points[-1][:2],None)
        self.overlay=new
        return {point for point in old.keys()|new.keys() if old.get(point)!=new.get(point)}
