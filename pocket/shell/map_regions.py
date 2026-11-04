"""Bounded prepared-region reuse with explicit cropped projection; no I/O."""
from collections import OrderedDict
from dataclasses import dataclass
import math


class Cells:
    __slots__=('base','stride','x','y','width','height')
    def __init__(self,base,stride,x,y,width,height):
        self.base,self.stride,self.x,self.y,self.width,self.height=base,stride,x,y,width,height
    def __len__(self):return self.width*self.height
    def __getitem__(self,index):
        if not 0<=index<len(self):raise IndexError(index)
        return self.base[(self.y+index//self.width)*self.stride+self.x+index%self.width]


@dataclass(frozen=True)
class Crop:
    cells:object
    base_view:object
    x:int
    y:int
    width:int
    height:int
    legend:str
    reused:bool
    requested_view:object=None
    @property
    def center(self):return self.requested_view.center if self.requested_view is not None else self.unproject((self.width-1)/2,(self.height-1)/2)
    @property
    def span(self):return self.requested_view.span if self.requested_view is not None else self.base_view.span*(self.width-1)/max(1,self.base_view.width-1)
    @property
    def cell_aspect(self):return self.base_view.cell_aspect
    def project(self,lon,lat):
        x,y=self.base_view.project(lon,lat)
        return x-self.x,y-self.y
    def unproject(self,x,y):
        view=self.base_view;lat,lon=view.center
        degrees=view.span/max(1,view.width-1)/111.32
        return (lat-(y+self.y-(view.height-1)/2)*degrees*view.cell_aspect,
                lon+(x+self.x-(view.width-1)/2)*degrees/max(.000001,math.cos(math.radians(lat))))


class Regions:
    """Two regions at most, with a shared cell budget and explicit LOD keys."""
    def __init__(self,entries=2,max_cells=240000):
        self.entries=max(1,min(2,entries));self.max_cells=max(1,max_cells)
        self.ready=OrderedDict();self.builds=0;self.hits=0
    @staticmethod
    def _lod(view):return (view.span/max(1,view.width-1),view.cell_aspect)
    def _crop(self,base,view):
        # Bound scale drift from the latitude-dependent local projection.
        old=math.cos(math.radians(base.center[0]));new=math.cos(math.radians(view.center[0]))
        if abs(old-new)/max(.000001,abs(new))*max(1,view.width-1)>.25:return None
        x,y=base.project(view.center[1],view.center[0])
        x=round(x-(view.width-1)/2);y=round(y-(view.height-1)/2)
        if x<0 or y<0 or x+view.width>base.width or y+view.height>base.height:return None
        return x,y
    def cached(self,view,signature=()):
        lod=self._lod(view)
        for key,(base,cells,legend) in reversed(self.ready.items()):
            if key[0]!=signature or key[1]!=lod:continue
            offset=self._crop(base,view)
            if offset is None:continue
            self.ready.move_to_end(key);self.hits+=1
            return Crop(Cells(cells,base.width,*offset,view.width,view.height),base,*offset,view.width,view.height,legend,True,view)
        return None
    def frame(self,view,prepare,signature=()):
        cached=self.cached(view,signature)
        if cached is not None:return cached
        lod=self._lod(view)
        # Even padding keeps the original center exactly on the same cell lattice.
        width=view.width+2*max(1,view.width//2);height=view.height+2*max(1,view.height//2)
        if width*height>self.max_cells or view.width==1:
            cells,legend=prepare(view);self.builds+=1
            return Crop(cells,view,0,0,view.width,view.height,legend,False,view)
        base=type(view)(view.center,view.span*(width-1)/max(1,view.width-1),width,height,view.cell_aspect)
        west,south,east,north=base.bbox
        if west<-180 or east>180 or south<-85 or north>85:
            cells,legend=prepare(view);self.builds+=1
            return Crop(cells,view,0,0,view.width,view.height,legend,False,view)
        cells,legend=prepare(base);cells=tuple(cells);self.builds+=1
        if len(cells)!=width*height:raise ValueError('Prepared region dimensions differ')
        key=(signature,lod,tuple(base.center),width,height)
        self.ready[key]=(base,cells,legend)
        while len(self.ready)>self.entries or sum(v[0].width*v[0].height for v in self.ready.values())>self.max_cells:
            self.ready.popitem(last=False)
        x,y=(width-view.width)//2,(height-view.height)//2
        return Crop(Cells(cells,width,x,y,view.width,view.height),base,x,y,view.width,view.height,legend,False,view)
