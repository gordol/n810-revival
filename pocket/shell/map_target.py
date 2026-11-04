"""A manually accepted geographic camera; no automatic commit or timer."""
import math


class Target:
    def __init__(self):
        self.view=None;self.held=False;self.revision=0
    def choose(self,center,span):
        view=(tuple(center),float(span))
        if view==self.view:return False
        self.revision+=1;self.view=view
        return True
    def cancel(self):
        self.revision+=1;self.view=None;self.held=False
    def take(self,force=False):
        if not force or self.view is None or self.held:return None
        view=self.view;self.cancel();return view
    def zoom(self,center,span,inward):
        center,span=self.view or (center,span)
        target=max(getattr(self,'minimum_span',.25),min(2000.,span*(.8 if inward else 1.25)))
        if target==span:return False
        return self.choose(center,target)
    def pan(self,center,span,key):
        center,span=self.view or (center,span);lat,lon=center;delta=span*.15/111.32
        if key in ('up','down'):lat+=delta*(1 if key=='up' else -1)
        else:lon+=delta*(1 if key=='right' else -1)/max(.1,math.cos(math.radians(lat)))
        self.choose((max(-85,min(85,lat)),(lon+180)%360-180),span)
