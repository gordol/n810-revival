"""Quality selection and the canopy height map, in scene metres."""
import math
import os


class RiverQuality:
    def __init__(self):
        mode=os.environ.get('POCKET_RIVER_QUALITY','auto').lower()
        self.auto=mode not in ('high','low')
        self.high=mode!='low'
        if self.auto:
            try:
                ram=os.sysconf("SC_PHYS_PAGES")*os.sysconf("SC_PAGE_SIZE")
                if 0<ram<3*1024**3:self.high=False
            except (OSError,ValueError,AttributeError):pass
        self.slow=0
        self.last=None

    def frame(self,now):
        # The idle walk requests 20 Hz. Ignore suspension and scene preparation.
        if self.auto and self.high and self.last is not None:
            dt=now-self.last
            self.slow=self.slow+1 if .075<dt<1.5 else 0
            if self.slow>=24:self.high=False
        self.last=now


def shade_tree(mask,x,z,height,texel=1):
    """Store the tallest conifer crown in each texel (3 units/m, up to 85 m)."""
    width=math.isqrt(len(mask))
    x=x/texel+width/2
    z=z/texel+width/2
    radius=max(.8,height*.23/texel)
    for j in range(max(0,int(z-radius)),min(width,math.ceil(z+radius))):
        for i in range(max(0,int(x-radius)),min(width,math.ceil(x+radius))):
            r=math.hypot(i+.5-x,j+.5-z)/radius
            if r<1:
                k=j*width+i
                mask[k]=max(mask[k],min(255,round(3*height*(1.-.72*r))))
