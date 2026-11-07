"""Bounded prepared-region reuse with explicit cropped projection; no I/O."""
from collections import OrderedDict
from dataclasses import dataclass
import math


def exposed_strips(width, height, overlap):
    """Non-overlapping rectangles outside a retained rectangle; right/bottom exclusive."""
    left, top, right, bottom = overlap
    return tuple(bounds for bounds in (
        (0, 0, width, top), (0, bottom, width, height),
        (0, top, left, bottom), (right, top, width, bottom),
    ) if bounds[0] < bounds[2] and bounds[1] < bounds[3])


def patch_view(view, bounds, halo=2):
    """Keep the display spacing while adding edge samples for slope/line calculations."""
    left, top, right, bottom = bounds
    left, top = max(0, left-halo), max(0, top-halo)
    right, bottom = min(view.width, right+halo), min(view.height, bottom+halo)
    degrees = view.span / max(1, view.width-1) / 111.32
    latitude, longitude = view.center
    center = (
        latitude - ((top+bottom-1)/2 - (view.height-1)/2) * degrees * view.cell_aspect,
        longitude + ((left+right-1)/2 - (view.width-1)/2) * degrees / max(.000001, math.cos(math.radians(latitude))),
    )
    width, height = right-left, bottom-top
    span = view.span * max(1, width-1) / max(1, view.width-1)
    return type(view)(center, span, width, height, view.cell_aspect), left, top


def overlap_samples(base, view):
    """Reproject retained cells, including longitude scale changes during north/south pans."""
    degrees = view.span / max(1, view.width-1) / 111.32
    latitude, longitude = view.center
    longitude_step = degrees / max(.000001, math.cos(math.radians(latitude)))
    xs = tuple(round(base.project(longitude+(x-(view.width-1)/2)*longitude_step, latitude)[0])
               for x in range(view.width))
    ys = tuple(round(base.project(longitude, latitude-(y-(view.height-1)/2)*degrees*view.cell_aspect)[1])
               for y in range(view.height))
    columns = [x for x, source in enumerate(xs) if 0 <= source < base.width]
    rows = [y for y, source in enumerate(ys) if 0 <= source < base.height]
    if not columns or not rows:
        return None
    return xs, ys, (columns[0], rows[0], columns[-1]+1, rows[-1]+1)


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
        self.ready=OrderedDict();self.builds=0;self.hits=0;self.reused_cells=0;self.prepared_cells=0
    @staticmethod
    def _lod(view):return (round(view.span/max(1,view.width-1),12),view.cell_aspect)
    def _offset(self,base,view):
        # Bound scale drift from the latitude-dependent local projection.
        old=math.cos(math.radians(base.center[0]));new=math.cos(math.radians(view.center[0]))
        if abs(old-new)/max(.000001,abs(new))*max(1,view.width-1)>.25:return None
        x,y=base.project(view.center[1],view.center[0])
        x=round(x-(view.width-1)/2);y=round(y-(view.height-1)/2)
        return x,y
    def _crop(self,base,view):
        offset=self._offset(base,view)
        if offset is None:return None
        x,y=offset
        if x<0 or y<0 or x+view.width>base.width or y+view.height>base.height:return None
        return x,y

    def _extend(self, view, prepare, signature):
        """Copy overlap and prepare only exposed strips, with a relief halo."""
        best = None
        best_area = 0
        for key, (base, cells, legend) in self.ready.items():
            if key[:2] != (signature, self._lod(view)):
                continue
            samples = overlap_samples(base, view)
            if samples is None:
                continue
            xs, ys, (left, top, right, bottom) = samples
            area = (right-left) * (bottom-top)
            if area > best_area:
                best_area = area
                best = (base, cells, legend, xs, ys, (left, top, right, bottom))
        if best is None:
            cells, legend = prepare(view)
            self.prepared_cells += view.width * view.height
            return tuple(cells), legend

        base, old, legend, xs, ys, overlap = best
        left, top, right, bottom = overlap
        cells = [None] * (view.width * view.height)
        for row in range(top, bottom):
            source_start = ys[row] * base.width
            cells[row*view.width+left:row*view.width+right] = [
                old[source_start+xs[column]] for column in range(left, right)
            ]

        for bounds in exposed_strips(view.width, view.height, overlap):
            left, top, right, bottom = bounds
            patch, patch_left, patch_top = patch_view(view, bounds)
            prepared, legend = prepare(patch)
            self.prepared_cells += patch.width * patch.height
            for row in range(top, bottom):
                source_start = (row-patch_top) * patch.width + left-patch_left
                cells[row*view.width+left:row*view.width+right] = prepared[source_start:source_start+right-left]
        self.reused_cells += best_area
        return tuple(cells), legend
    def cached(self,view,signature=()):
        lod=self._lod(view)
        for key,(base,cells,legend) in reversed(self.ready.items()):
            if key[0]!=signature or key[1]!=lod:continue
            offset=self._crop(base,view)
            if offset is None:continue
            self.ready.move_to_end(key);self.hits+=1
            return Crop(Cells(cells,base.width,*offset,view.width,view.height),base,*offset,view.width,view.height,legend,True,view)
        return None
    def frame(self,view,prepare,signature=(),padding=True):
        cached=self.cached(view,signature)
        if cached is not None:return cached
        lod=self._lod(view)
        # Even padding keeps the original center exactly on the same cell lattice.
        width=view.width+2*max(1,view.width//8) if padding else view.width
        height=view.height+2*max(1,view.height//8) if padding else view.height
        if width*height>self.max_cells or view.width==1:
            cells,legend=prepare(view);self.builds+=1
            return Crop(cells,view,0,0,view.width,view.height,legend,False,view)
        base=type(view)(view.center,view.span*(width-1)/max(1,view.width-1),width,height,view.cell_aspect)
        west,south,east,north=base.bbox
        if west<-180 or east>180 or south<-85 or north>85:
            cells,legend=prepare(view);self.builds+=1
            return Crop(cells,view,0,0,view.width,view.height,legend,False,view)
        cells,legend=self._extend(base,prepare,signature);self.builds+=1
        if len(cells)!=width*height:raise ValueError('Prepared region dimensions differ')
        key=(signature,lod,tuple(base.center),width,height)
        self.ready[key]=(base,cells,legend)
        while len(self.ready)>self.entries or sum(v[0].width*v[0].height for v in self.ready.values())>self.max_cells:
            self.ready.popitem(last=False)
        x,y=(width-view.width)//2,(height-view.height)//2
        return Crop(Cells(cells,width,x,y,view.width,view.height),base,x,y,view.width,view.height,legend,False,view)
