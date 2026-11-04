"""One precomputed regional image from the existing prepared-map provider."""
from functools import lru_cache
import hashlib,json,math
from pathlib import Path

SHA256='e31078767b6ac0fee8f015b60345e057890789afb0a612fe8f98b51d84258c45'

@lru_cache(maxsize=1)
def data():
    with (Path(__file__).parent/'map-assets/accepted-preview/puget-overview.json').open('rb') as source:raw=source.read(1024*1024+1)
    if len(raw)>1024*1024 or hashlib.sha256(raw).hexdigest()!=SHA256:raise ValueError('Regional overview differs from pinned image')
    value=json.loads(raw)
    if value['version']!=1 or (value['width'],value['height'])!=(192,96) or len(value['cells'])!=192*96:raise ValueError('Invalid regional image')
    value['cells']=tuple((str(char),int(color)) for char,color in value['cells'])
    return value

class CropCells:
    def __init__(self,cells,source_width,x,y,width,height):self.cells,self.source_width,self.x,self.y,self.width,self.height=cells,source_width,x,y,width,height
    def __len__(self):return self.width*self.height
    def __getitem__(self,index):return self.cells[(self.y+index//self.width)*self.source_width+self.x+index%self.width]

class CropProjection:
    def __init__(self,source,x,y,width,height):
        self.source=source;self.x=x;self.y=y;self.width=width;self.height=height;self.cell_aspect=source.cell_aspect
        self.center=self.unproject((width-1)/2,(height-1)/2);self.span=source.span*(width-1)/max(1,source.width-1)
    def project(self,lon,lat):
        x,y=self.source.project(lon,lat);return x-self.x,y-self.y
    def unproject(self,x,y):
        source=self.source;x+=self.x;y+=self.y;degrees=source.span/max(1,source.width-1)/111.32
        return (source.center[0]-(y-(source.height-1)/2)*degrees*source.cell_aspect,
                source.center[1]+(x-(source.width-1)/2)*degrees/max(.000001,math.cos(math.radians(source.center[0]))))

def corners(center,span,width,height):
    lat,lon=center;half_lon=span/111.32/2/max(.000001,math.cos(math.radians(lat)))
    half_lat=span/111.32*max(0,height-1)/max(1,width-1)
    return (lon-half_lon,lat+half_lat),(lon+half_lon,lat-half_lat)

def contains(image,center,span,width,height):
    if image is None or image.projection is None:return False
    a,b=corners(center,span,width,height);points=[image.projection.project(*point) for point in (a,b)]
    return all(-.01<=x<=image.width-1+.01 and -.01<=y<=image.height-1+.01 for x,y in points)

class Overview:
    def __init__(self):
        try:self.data=data()
        except (OSError,ValueError,KeyError,TypeError):self.data=None
        self.cached=None;self.key=None
    def image(self,module,width,height):
        if not callable(getattr(module,'Viewport',None)) or self.data is None:return None
        from offline_map import Image
        key=(width,height)
        if self.key!=key:
            d=self.data;sw,sh=d['width'],d['height'];w=sw;h=max(2,round(w*height/max(1,width)))
            if h>sh:h=sh;w=max(2,round(h*width/max(1,height)))
            x,y=(sw-w)//2,(sh-h)//2
            projection=CropProjection(module.Viewport(d['center'],d['span'],sw,sh),x,y,w,h)
            self.cached=Image(w,h,CropCells(d['cells'],sw,x,y,w,h),'Cached Puget regional overview',(),0.,projection,'cached-overview')
            self.key=key
        return self.cached


class LocalOverview:
    """Request bounded context through the map's existing single worker."""
    def __init__(self,renderer):self.renderer=renderer;self.key=None;self.coarse=None;self.refined=None
    def image(self,module,width,height,center,span,engine=None):
        from desktop_elevation import enabled
        from offline_map import raster_size
        if enabled():
            width,height=raster_size(width,height);key=(tuple(center),span,width,height)
            if key!=self.key:self.key=key;self.coarse=None;self.refined=None
            if self.refined is not None:return self.refined
            w=min(160,max(2,width));h=max(2,round((w-1)*max(1,height-1)/max(1,width-1))+1)
            if self.coarse is None:
                self.coarse=self.renderer.context_frame(center,span,w,h)
                if self.coarse is None:return None
            if (w,h)==(width,height):self.refined=self.coarse
            else:self.refined=self.renderer.context_frame(center,span,width,height)
            return self.refined or self.coarse
        w=min(160,max(2,width));h=max(2,round((w-1)*max(1,height-1)/max(1,width-1))+1)
        scale=min(1,80/h);w=max(2,round((w-1)*scale)+1);h=max(2,round((h-1)*scale)+1)
        return self.renderer.context_frame(center,span,w,h)

def zoom_context(image,overview,module,center,span,width,height):
    """Immediate zoom-box backdrop from retained cells; never queue another render."""
    from offline_map import Image
    if image is not None and contains(image,center,span,width,height):return image
    projection=getattr(image,'projection',None)
    base=getattr(projection,'base_view',None)
    cells=getattr(getattr(projection,'cells',None),'base',None)
    if base is not None and cells is not None:
        candidate=Image(base.width,base.height,cells,image.legend,(),0.,base,'zoom-context')
        if contains(candidate,center,span,width,height):return candidate
    regional=overview.image(module,width,height)
    if regional is None:return image
    w=min(160,max(2,width));h=max(2,min(80,round(w*height/max(1,width))))
    view=module.Viewport(center,span*1.6,w,h)
    from paint import ink
    def sample_color(lon,lat):
        sx,sy=regional.projection.project(lon,lat)
        x,y=math.floor(sx+.5),math.floor(sy+.5)
        if not (0<=x<regional.width and 0<=y<regional.height):return (16,24,24)
        char,style=regional.cells[y*regional.width+x]
        top=(sy+.5-y)<.5
        foreground=char=='█' or char=='▀' and top or char=='▄' and not top
        shifts=(40,32,24) if foreground else (16,8,0)
        return tuple((style>>shift)&255 for shift in shifts)
    values=[]
    for y in range(h):
        for x in range(w):
            degrees=view.span/max(1,w-1)/111.32
            lon=center[1]+(x-(w-1)/2)*degrees/max(.000001,math.cos(math.radians(center[0])))
            lat=center[0]-(y-(h-1)/2)*degrees*view.cell_aspect
            a=sample_color(lon,lat+degrees*view.cell_aspect/4)
            b=sample_color(lon,lat-degrees*view.cell_aspect/4)
            values.append((' ' if a==b else '▀',ink(*a,background=b)))
    return Image(w,h,tuple(values),'Cached zoom context',(),0.,view,'zoom-context')
