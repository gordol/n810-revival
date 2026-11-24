"""Quality selection and the static forest shadow mask, in scene metres."""
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


def shade_tree(mask,x,z,height):
    """Project the evergreen crown down-sun into the meadow's 1 m shadow texels."""
    if max(abs(x),abs(z))>269:return
    length=.85*height
    width=.20*height
    for j in range(max(0,int(z+256-width)),min(512,math.ceil(z+256+.6*length+width)+1)):
        for i in range(max(0,int(x+256-width)),min(512,math.ceil(x+256+.8*length+width)+1)):
            dx,dz=i-255.5-x,j-255.5-z
            t=(dx*.8+dz*.6)/length
            if -.13<t<1:
                breadth=width*max(.08,1-abs(t-.30)/.73)
                cover=max(0.,min(1.,(1-abs(dz*.8-dx*.6)/breadth)*2))
                k=j*512+i
                mask[k]=max(mask[k],int(cover*190))
