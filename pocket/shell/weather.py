"""Synthetic weather observations and bounded surface decoration."""
from collections import namedtuple
import math

Weather = namedtuple('Weather','label wind_x wind_y temperature source precipitation intensity cloud',defaults=('none',0.0,.2))
PRESETS = (
    Weather('Calm',0,0,8,'synthetic'),
    Weather('Breeze',4,.3,8,'synthetic'),
    Weather('Snow wind',-3,.2,-4,'synthetic','snow',.65,.8),
    Weather('Rain wind',5,.5,5,'synthetic','rain',.75,.9),
)


def detail_budget(width,height):
    return min(768,max(64,width*height//8))


def wind_field(weather,x,y,seconds):
    # Shared coherent gust with local phase; particles lag rather than jitter.
    pulse=.65+.35*math.sin(seconds*.7+x/40+y/25)
    return weather.wind_x*pulse,weather.wind_y*pulse


class Surfaces:
    """At most 64 deposits and 48 detached drops; no fluid solver."""
    def __init__(self):
        self.deposits={}
        self.drops=[]
        self.pools={}

    def clear(self):
        self.deposits.clear();self.drops.clear();self.pools.clear()

    def update(self,cells,windows,kind,temperature,step,now,width,height):
        output=dict(cells)
        self.drops=[p for p in self.drops if now-p[2]<1.5]
        def drop(x,y,glyph,color):
            if len(self.drops)<48:self.drops.append((x,y,now,glyph,color))
        active={name:rect for name,rect in windows}
        for key,(rect,amount) in list(self.deposits.items()):
            name,x=key
            if name not in active or active[name]!=rect:
                drop(x,rect[1]-1,'*' if kind=='snow' else '|',10 if kind=='snow' else 9)
                del self.deposits[key]
        for (x,y),_ in cells.items():
            for name,rect in reversed(windows):
                wx,wy,ww,wh=rect
                if wx<=x<wx+ww and y==wy-1 and wy>0:
                    key=(name,x)
                    if key in self.deposits or len(self.deposits)<64:
                        _,amount=self.deposits.get(key,(rect,0))
                        self.deposits[key]=(rect,min(3,amount+1))
                    break
        for (name,x),(rect,amount) in list(self.deposits.items()):
            wx,wy,ww,wh=rect
            output[x,wy-1]=('_',10) if kind=='snow' else ('~',9)
            if kind=='snow' and temperature<0 and amount>=2:
                # Icicles hang off the outer corners, behind the opaque frame.
                edge=wx-1 if x<wx+ww//2 else wx+ww
                for i in range(min(2,amount)):
                    if 0<=edge<width and wy+wh+i<height:output[edge,wy+wh+i]=('|',10)
            if step%6==0 and (kind=='rain' or temperature>0):
                edge=wx-1 if x<wx+ww//2 else wx+ww
                drop(edge,wy+wh,'|' if kind=='rain' else '*',9 if kind=='rain' else 10)
                if amount<=1:del self.deposits[name,x]
                else:self.deposits[name,x]=(rect,amount-1)
        for x,y,born,glyph,color in self.drops:
            yy=y+int((now-born)*6)
            if 0<=x<width and 0<=yy<height:output[x,yy]=(glyph,color)
            if kind=='rain' and 0<=x<width and yy>=height-1 and (x in self.pools or len(self.pools)<32):
                self.pools[x]=min(3,self.pools.get(x,0)+1)
        for x,amount in list(self.pools.items()):
            for dx in range(amount):
                if x+dx<width:output[x+dx,height-1]=('~',9)
            if step%12==0:
                if amount<=1:del self.pools[x]
                else:self.pools[x]=amount-1
        return {xy:v for xy,v in output.items() if 0<=xy[0]<width and 0<=xy[1]<height}
