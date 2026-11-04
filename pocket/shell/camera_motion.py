"""Short camera easing over retained terrain rasters; no intermediate geometry jobs."""
from collections.abc import Mapping


def pose(desktop, overview, parallax, zoom):
    return ((desktop-1)*parallax, (zoom-1)*600/.65/8500 if overview else 0,
            zoom if overview else 1)


def mix(a, b, amount):
    # RGB half-block cells pack six channels. Blend alternate bytes together,
    # using the vacant bytes as multiplication carry space.
    if a == b or amount == 0:return a
    if amount == 256:return b
    if a < 1<<48 or b < 1<<48:return a if amount < 128 else b
    mask=0xff00ff00ff
    even=(((a&mask)*(256-amount)+(b&mask)*amount)>>8)&mask
    odd=((((a>>8)&mask)*(256-amount)+((b>>8)&mask)*amount)>>8)&mask
    return (1<<48)|even|(odd<<8)


class Frame(Mapping):
    """Immutable sampling plan. Existing compositor chunks do the pixel work."""
    def __init__(self, source, target, axes, width, height, amount):
        self.source,self.target=source,target
        self.ax,self.ay,self.bx,self.by=axes
        self.width,self.height,self.amount=width,height,amount

    def __len__(self):return self.width*self.height
    def __iter__(self):
        return ((x,y) for y in range(self.height) for x in range(self.width))
    def __getitem__(self,xy):
        x,y=xy
        if not (0<=x<self.width and 0<=y<self.height):raise KeyError(xy)
        a=self.source.get((self.ax[x],self.ay[y]));b=self.target.get((self.bx[x],self.by[y]))
        if a is None and b is None:
            b=self.target.get((max(0,min(self.width-1,self.bx[x])),max(0,min(self.height-1,self.by[y]))))
        if a is None:cell=b
        elif b is None or a==b:cell=a
        else:cell=type(a)(a.char if self.amount<128 else b.char,mix(a.color,b.color,self.amount))
        if cell is None:raise KeyError(xy)
        return cell


class Motion:
    def __init__(self, source, start, end, width, height, duration):
        # Reversal may retain a sampled frame. Flatten only that interrupted
        # snapshot, so repeated reversals cannot build a recursive sampler chain.
        self.source=dict(source) if isinstance(source,Frame) else source
        self.start=start;self.end=end
        self.width=width;self.height=height;self.duration=duration
        self.target=None;self.began=None;self.step=-1
        self.current=start

    def frame(self, now):
        if self.began is None:return self.source
        t=min(1,max(0,(now-self.began)/self.duration))
        if t>=1:return self.target
        if t<=0:return self.source
        eased=t*t*(3-2*t)
        current=tuple(a+(b-a)*eased for a,b in zip(self.start,self.end))
        self.current=current
        w,h=self.width,self.height
        def coordinates(endpoint):
            dx,dy,scale=endpoint
            xs=[round((x-(w-1)/2)*current[2]/scale+(w-1)/2+(current[0]-dx)*w/scale) for x in range(w)]
            ys=[round((y-(h-1)/2)*current[2]/scale+(h-1)/2-(current[1]-dy)*h/scale) for y in range(h)]
            return xs,ys
        ax,ay=coordinates(self.start);bx,by=coordinates(self.end)
        return Frame(self.source,self.target,(ax,ay,bx,by),w,h,round(eased*256))
