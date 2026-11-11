"""Read-only adapter for the existing offline APRS engine; one bounded worker."""
import importlib.util
from pathlib import Path
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor,CancelledError
from dataclasses import dataclass
from functools import partial
import time
import math
import os
from array import array
from paint import ink,rgb

_BUNDLED=Path(__file__).resolve().parent/'vendor/packet-console'
ROOT=_BUNDLED
# Public regional viewpoints; the operator's saved QTH is separate.
PRESETS=(('Lakewood',(47.17,-122.52),2.),('Puget Sound',(47.25,-122.25),100.),('Tahoma',(46.8523,-121.7603),50.))


def raster_size(width,height):
    """Use dense desktop cells without enlarging work on small device displays."""
    from desktop_elevation import enabled
    desktop=enabled();budget=2097152 if desktop else 262144
    width=max(1,min(4096 if desktop else 1024,int(width)));height=max(1,min(2048 if desktop else 512,int(height)))
    if width*height>budget:
        scale=math.sqrt(budget/(width*height));width=max(1,int(width*scale));height=max(1,int(height*scale))
    return width,height


def map_cache_directory():
    override=os.environ.get('N810_MAP_BASES')
    if override:return Path(override).expanduser()
    return Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'current-world/map-bases'


@dataclass(frozen=True,slots=True)
class Image:
    width:int
    height:int
    cells:tuple
    legend:str
    places:tuple
    seconds:float
    projection:object=None
    source:str='rendered'
    features:object=None


@dataclass(frozen=True,slots=True)
class MapFeatures:
    terrain:array
    vectors:tuple
    labels:dict
    sample_width:int
    sample_height:int
    forest_roads:bool=False
    pixel_detail:bool=False


@dataclass(frozen=True,slots=True)
class MapSurface:
    """One displayed map image, its app annotations, and grid preference."""
    image:Image
    layer:tuple
    renderer:object
    key:tuple
    grid_mode:str='off'
    overlay_vectors:tuple=()
    terrain:bool=True
    roads:bool=True
    unavailable_reason:str=''
    content_width:int=0
    labels:bool=True
    inset:object=None
    box_plane:object=None
    def viewport(self):
        projection=self.image.projection;_,_,width,height,_=self.layer
        return self.renderer.module.Viewport(projection.center,projection.span,width,height,projection.cell_aspect)
    def features(self,view,base_cells):
        if self.unavailable_reason:raise ValueError(self.unavailable_reason)
        prepared=getattr(self.image,'features',None)
        projection=self.image.projection
        if (prepared is not None and projection is not None and
            prepared.forest_roads==bool(getattr(self.renderer,'forest_roads',False)) and
            prepared.pixel_detail and
            (view.width,view.height,tuple(view.center),view.span,view.cell_aspect)==
            (self.image.width,self.image.height,tuple(projection.center),projection.span,projection.cell_aspect)):
            from map_geography import grid_enabled,grid_features
            if not grid_enabled(self.grid_mode,view.span):
                if self.labels:return prepared
                return MapFeatures(prepared.terrain,prepared.vectors,{},prepared.sample_width,
                                   prepared.sample_height,prepared.forest_roads,prepared.pixel_detail)
            grid_vector,grid_labels=grid_features(view)
            annotations=prepared.labels if self.labels else {}
            return MapFeatures(prepared.terrain,(grid_vector,*prepared.vectors),
                               {**grid_labels,**annotations},prepared.sample_width,prepared.sample_height,
                               prepared.forest_roads,prepared.pixel_detail)
        features=self.renderer.semantic_features(view,base_cells,terrain=self.terrain,
                                                roads=self.roads,grid_mode=self.grid_mode,
                                                pixel_detail=True)
        if self.labels:return features
        return MapFeatures(features.terrain,features.vectors,{},features.sample_width,
                           features.sample_height,features.forest_roads,features.pixel_detail)


_Q5=tuple(round(round(value*31/255)*255/31) for value in range(256))
_Q6=tuple(round(round(value*63/255)*255/63) for value in range(256))
def map_rgb(color):
    """The same RGB565 quantization as paint.rgb, without repeated arithmetic."""
    r,g,b=color
    if type(r) is int and type(g) is int and type(b) is int and 0<=r<=255 and 0<=g<=255 and 0<=b<=255:
        return (_Q5[r]<<16)|(_Q6[g]<<8)|_Q5[b]
    return rgb(r,g,b)


class Plane:
    """Sparse app annotations over the shared immutable terrain cells."""
    __slots__=('base','overlay')
    def __init__(self,base,overlay):self.base,self.overlay=base,overlay
    def __getitem__(self,index):return self.overlay.get(index,self.base[index])
    def __len__(self):return len(self.base)


class SemanticPlane:
    """Terrain-only cell fallback over a semantic pixel frame."""
    __slots__=('samples','width','height')
    def __init__(self,samples,width,height):self.samples,self.width,self.height=samples,width,height
    def __len__(self):return self.width*self.height
    def __getitem__(self,index):
        if isinstance(index,slice):return tuple(self[i] for i in range(*index.indices(len(self))))
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        row,column=divmod(index,self.width)
        upper=self.samples[(row*2)*self.width+column]
        lower=self.samples[(row*2+1)*self.width+column]
        return (' ' if upper==lower else '▀',(1<<48)|(upper<<24)|lower)


class GridPlane(Plane):
    """TUI grid marks; pixel consumers use geographic grid features."""

class PathPlane(Plane):
    """TUI path dots; pixel consumers use the source endpoint geometry."""


def without_grid(layer):
    """Keep app annotations while removing TUI line presentations."""
    if layer is None:return None
    x,y,w,h,plane=layer
    def clean(value):
        if isinstance(value,(GridPlane,PathPlane)):return clean(value.base)
        if isinstance(value,Plane):
            base=clean(value.base)
            return value if base is value.base else Plane(base,value.overlay)
        return value
    return x,y,w,h,clean(plane)


def plane_identity(plane):
    """Stable identity for rebuilt annotation wrappers over retained cells."""
    if isinstance(plane,(GridPlane,PathPlane)):return plane_identity(plane.base)
    if isinstance(plane,Plane):return plane_identity(plane.base),tuple(sorted(plane.overlay.items()))
    return id(plane)


class ScaledPlane:
    __slots__=('base','sw','sh','width','height')
    def __init__(self,base,sw,sh,width,height):self.base,self.sw,self.sh,self.width,self.height=base,sw,sh,width,height
    def __getitem__(self,index):
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        x,y=index%self.width,index//self.width
        return self.base[min(self.sh-1,y*self.sh//self.height)*self.sw+min(self.sw-1,x*self.sw//self.width)]
    def __len__(self):return self.width*self.height

class ContextPlane(ScaledPlane):
    """Scale half-cell colours, never tile text glyphs into stripes or grids."""
    __slots__=('_cache',)
    def __init__(self,*args):
        super().__init__(*args);self._cache={}
    def __getitem__(self,index):
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        if (self.sw,self.sh)==(self.width,self.height):return self.base[index]
        if index in self._cache:return self._cache[index]
        x,y=index%self.width,index//self.width
        sx=min(self.sw-1,int((x+.5)*self.sw/self.width));colors=[]
        for half in (0,1):
            sample=min(2*self.sh-1,int((2*y+half+.5)*self.sh/self.height))
            char,style=self.base[(sample//2)*self.sw+sx]
            front=char=='█' or char=='▀' and sample%2==0 or char=='▄' and sample%2==1
            colors.append(tuple((style>>shift)&255 for shift in ((40,32,24) if front else (16,8,0))))
        a,b=colors
        value=(' ' if a==b else '▀',ink(*a,background=b))
        self._cache[index]=value
        return value


class ReprojectedPlane:
    """Translate retained cells, or resample terrain halves when scale changes."""
    __slots__=('original','base','sw','sh','width','height','xs','ys','half_ys','empty','resampled','_cache')
    def __init__(self,image,view):
        if isinstance(image.cells,ReprojectedPlane):image=image.cells.original
        self.original=image;self.base=image.cells;self.sw=image.width;self.sh=image.height
        self.width,self.height=view.width,view.height
        degrees=view.span/max(1,view.width-1)/111.32
        scale=max(.000001,math.cos(math.radians(view.center[0])))
        self.xs=tuple(round(image.projection.project(view.center[1]+(x-(view.width-1)/2)*degrees/scale,view.center[0])[0]) for x in range(view.width))
        self.ys=tuple(round(image.projection.project(view.center[1],view.center[0]-(y-(view.height-1)/2)*degrees*view.cell_aspect)[1]) for y in range(view.height))
        old=image.projection
        old_step=old.span/max(1,old.width-1)
        self.resampled=abs(old_step-view.span/max(1,view.width-1))/max(1e-12,old_step)*max(view.width,view.height)>.25 or old.cell_aspect!=view.cell_aspect
        self.half_ys=tuple(math.floor((image.projection.project(view.center[1],view.center[0]-(y/2-.25-(view.height-1)/2)*degrees*view.cell_aspect)[1]+.5)*2) for y in range(2*view.height)) if self.resampled else ()
        self.empty=(' ',ink(16,24,24,background=(16,24,24)));self._cache={}
    def __len__(self):return self.width*self.height
    def __getitem__(self,index):
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError(index)
        x=self.xs[index%self.width];row=index//self.width
        if not self.resampled:
            y=self.ys[row]
            return self.base[y*self.sw+x] if 0<=x<self.sw and 0<=y<self.sh else self.empty
        if index in self._cache:return self._cache[index]
        colors=[]
        for half in self.half_ys[2*row:2*row+2]:
            if not (0<=x<self.sw and 0<=half<2*self.sh):color=self.empty[1]&0xffffff
            else:
                char,style=self.base[(half//2)*self.sw+x]
                front=char=='█' or char=='▀' and half%2==0 or char=='▄' and half%2==1
                color=((style>>24) if front else style)&0xffffff
            colors.append(color)
        a,b=colors
        value=(' ' if a==b else '▀',(1<<48)|(a<<24)|b)
        self._cache[index]=value
        return value


class Renderer:
    def __init__(self,root=ROOT,maps=None):
        from data_paths import map_directory
        self.root=Path(root);self.maps=Path(maps) if maps is not None else map_directory(self.root/'maps');self.pool=None;self.pending=None;self.ready=OrderedDict();self.error=None;self.failed={}
        self.module=self.engine=None;self.meshes=OrderedDict();self.latest3d=None;self._wanted=None
        from map_regions import Regions
        self.reuse_regions=False;self.regions=Regions();self.completion_wakeup=None;self.loading_phase='idle'
        self.presentation='cells'
        self.timing_enabled=False;self._request_timing={};self._worker_timing={};self._worker_counts={};self._wanted_since=None
    def _completed(self,future):
        callback=self.completion_wakeup
        if callback:
            try:callback()
            except Exception:pass
    def region_compatible(self,span):return span>=20
    def supports_semantic_image(self,image):
        return getattr(image,'features',None) is not None or getattr(self,'provider_selection',None) is None
    def set_presentation(self,mode):
        if mode not in ('cells','semantic'):raise ValueError('Unknown map presentation')
        if self.pending or self.ready:raise RuntimeError('Select map presentation before the first frame')
        self.presentation=mode
    def semantic_features(self,view,terrain_cells,*,terrain=True,roads=True,grid_mode='off',pixel_detail=False):
        """Give a pixel backend clean terrain, geographic lines, and labels."""
        if self.engine is None:raise ValueError('Offline map engine is not ready')
        if len(terrain_cells)!=view.width*view.height:raise ValueError('Map terrain dimensions differ')
        self.engine.forest_roads=bool(getattr(self,'forest_roads',False))
        from map_geography import vector_segments,label_annotations,grid_features,grid_enabled
        # The cell plane contains TUI road strokes and labels. Never infer a
        # pixel map's terrain from those painted glyphs. Sample the engine's
        # terrain source at the same projection instead.
        frame,_=self.engine._rgb_terrain(view,terrain)
        return self._features_from_terrain(view,frame,roads,grid_mode,pixel_detail)
    def _features_from_terrain(self,view,frame,roads=True,grid_mode='off',pixel_detail=False):
        from map_geography import vector_segments,label_annotations,grid_features,grid_enabled
        samples=array('I')
        for row in range(view.height):
            cells=frame[row*view.width:(row+1)*view.width]
            samples.extend(map_rgb(upper) for _,upper,_ in cells)
            samples.extend(map_rgb(lower) for _,_,lower in cells)
        detail_pixels=8 if pixel_detail else 1
        vectors=list(vector_segments(self.engine,view,roads=roads,detail_pixels=detail_pixels))
        labels=label_annotations(self.engine,view,roads=roads,detail_pixels=detail_pixels)
        if grid_enabled(grid_mode,view.span):
            grid_vector,grid_labels=grid_features(view)
            vectors.insert(0,grid_vector)
            labels={**grid_labels,**labels}
        return MapFeatures(samples,tuple(vectors),labels,view.width,view.height*2,
                           bool(getattr(self,'forest_roads',False)),pixel_detail)
    def region_identity(self):return getattr(self.engine,'cache_identity',id(self.engine.palette))
    def region_status(self,image=None):
        return dict(source=getattr(image,'source',None),regions=len(self.regions.ready),
                    hits=self.regions.hits,builds=self.regions.builds,
                    retained_cells=sum(view.width*view.height for view,_,_ in self.regions.ready.values()),
                    reused_cells=self.regions.reused_cells,prepared_cells=self.regions.prepared_cells)
    def loading_message(self):
        if self.pending and self.pending[0]!=self._wanted:return 'Waiting for earlier map view…'
        if self.pending and self.pending[1].done():return 'Displaying completed map…'
        if self.engine is None:return 'Loading offline map library…'
        return {'region':'Reusing geographic region…','saved':'Loading saved map view…',
                'build':'Building missing map view…','memory':'Reusing map in memory…',
                'ready':'Map ready'}.get(self.loading_phase,'Finding reusable map view…')
    def timing_snapshot(self):
        return dict(requests=dict(self._request_timing),worker=dict(self._worker_timing),outcomes=dict(self._worker_counts))
    def _count_request(self,name):
        self._request_timing[name]=self._request_timing.get(name,0)+1
    def _stage(self,name,started):
        self._worker_timing=dict(self._worker_timing,**{name:time.monotonic()-started})
    def _timed_render(self,key,queued,requested=None):
        started=time.monotonic()
        self._worker_timing=dict(status='running',started_at=started,queue_seconds=started-queued,request_to_start_seconds=started-(requested if requested is not None else queued))
        status='completed'
        try:return self._render(key)
        except CancelledError:
            status='superseded' if key!=self._wanted else 'cancelled'
            raise
        except Exception:
            status='failed'
            raise
        finally:
            finished=time.monotonic()
            self._worker_timing=dict(self._worker_timing,status=status,total_seconds=finished-started,finished_at=finished)
            self._worker_counts[status]=self._worker_counts.get(status,0)+1
    def _render(self,key):
        if key!=self._wanted:raise CancelledError()
        began=time.monotonic();self.loading_phase='lookup'
        stage=time.monotonic() if self.timing_enabled else None
        if self.module is None:
            path=self.root/'n810-map-next.py'
            spec=importlib.util.spec_from_file_location('framework_offline_map',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            self.module=module;self.engine=module.Engine(self.maps,'rgb',cache_directory=map_cache_directory())
        from desktop_elevation import configure
        configure(self.engine)
        from elevation_display import configure as configure_portable
        configure_portable(self.engine)
        self.engine.forest_roads=getattr(self,'forest_roads',False)
        if stage is not None:self._stage('initialize_seconds',stage)
        if key[0]=='3d':return self._render3d(key[1:])
        if key[0] in ('map','context') and self.presentation=='semantic':
            return self._render_semantic(key,began)
        _,center,span,width,height,terrain,roads=key
        viewport=self.module.Viewport(center,span,width,height)
        projection=None;source=None
        if key[0] in ('map','context') and self.reuse_regions and self.region_compatible(span) and width>1:
            signature=(self.region_identity(),bool(terrain),bool(roads))
            projection=self.regions.cached(viewport,signature)
            prepared=getattr(self.engine,'prepared',None)
            disk=prepared.disk_path(('next-rgb-v1',(viewport.key,bool(terrain),bool(roads)))) if prepared else None
            if projection is None and not (disk and Path(disk).is_file()):
                projection=self.regions.frame(viewport,lambda view:self._packed_view(view,terrain,roads,display_span=viewport.span),signature,padding=key[0]=='map')
            if projection is not None:
                self.loading_phase='region'
                cells=tuple(projection.cells);legend=projection.legend+' · regional base'
                source='region-reused' if projection.reused else 'region-prepared' if self.engine.stats.get('cache')=='prepared' else 'region-built'
            else:cells,legend=self._packed_view(viewport,terrain,roads)
        else:cells,legend=self._packed_view(viewport,terrain,roads)
        if key!=self._wanted:raise CancelledError()
        if source is None:source={'prepared':'prepared','ram':'memory'}.get(getattr(self.engine,'stats',{}).get('cache'),'rendered')
        stage=time.monotonic() if self.timing_enabled else None
        places=tuple((p['name'] if 'name' in p else p.get('label',''),p['lon'],p['lat']) for p in self.engine.places(viewport))
        if stage is not None:self._stage('places_seconds',stage)
        self.loading_phase='ready'
        return Image(width,height,cells,legend,places,time.monotonic()-began,projection or viewport,source)
    def _render_semantic(self,key,began):
        """Prepare one clean source frame; native and TUI share the map engine."""
        _,center,span,width,height,terrain,roads=key
        view=self.module.Viewport(center,span,width,height)
        frame,legend=self.engine._rgb_terrain(view,terrain)
        features=self._features_from_terrain(view,frame,roads,pixel_detail=self.presentation=='semantic')
        if key!=self._wanted:raise CancelledError()
        places=tuple((p['name'] if 'name' in p else p.get('label',''),p['lon'],p['lat']) for p in self.engine.places(view))
        self.loading_phase='ready'
        return Image(width,height,SemanticPlane(features.terrain,width,height),legend,places,
                     time.monotonic()-began,view,'semantic',features)
    def _packed_view(self,viewport,terrain,roads,display_span=None):
        prepared=getattr(self.engine,'prepared',None)
        cache_key=(viewport.key,bool(terrain),bool(roads)) if hasattr(viewport,'key') else None
        disk=prepared.disk_path(('next-rgb-v1',cache_key)) if prepared and cache_key else None
        self.loading_phase='memory' if cache_key in getattr(self.engine,'cache',{}) else 'saved' if disk and Path(disk).is_file() else 'build'
        stage=time.monotonic() if self.timing_enabled else None
        from map_geography import covers
        from desktop_elevation import enabled as desktop_map
        # A complete regional vector layer replaces the old mixed-detail road
        # rasters on desktop; station/path overlays are composed afterward.
        frame,legend=self.engine.prepare(viewport,terrain,roads and not (desktop_map() and covers(viewport)))
        from map_geography import decorate
        if desktop_map():frame=decorate(self.engine,viewport,frame,roads,display_span=display_span)
        if stage is not None:self._stage('prepare_seconds',stage)
        colors={}
        def color(fg,bg):
            pair=fg,bg
            if pair not in colors:colors[pair]=(1<<48)|(map_rgb(fg)<<24)|map_rgb(bg)
            return colors[pair]
        stage=time.monotonic() if self.timing_enabled else None
        cells=tuple((char,color(fg,bg)) for char,fg,bg in frame)
        if stage is not None:self._stage('pack_seconds',stage)
        return cells,legend
    def frame(self,center,span,width,height,terrain=True,roads=True):
        width,height=raster_size(width,height)
        key=('map',tuple(center),float(span),width,height,bool(terrain),bool(roads))
        return self._request(key)
    def frame3d(self,center,span,map_width,map_height,width,height,yaw=0,tilt=.75,exaggeration=1,scenic=True,camera_mix=None):
        yaw=round(math.remainder(yaw,math.tau),10)
        scale=min(1,180/max(1,width),70/max(1,height))
        mix=(0. if scenic else 1.) if camera_mix is None else round(max(0,min(1,camera_mix)),3)
        key=('3d',tuple(center),float(span),map_width,map_height,max(1,round(width*scale)),max(1,round(height*scale)),yaw,tilt,exaggeration,mix)
        image=self._request(key)
        if image is None and self.latest3d and getattr(self,'provider_selection',None) is None:
            previous,value=self.latest3d
            if previous[:7]==key[:7] and previous[9]==key[9]:return value
        return image
    def _request(self,key):
        from desktop_elevation import enabled,signature
        if enabled() and time.monotonic()-getattr(self,'_dem_checked',0)>1:
            self._dem_checked=time.monotonic()
            revision=signature()
            if revision!=getattr(self,'_dem_revision',None):
                self._dem_revision=revision;self.ready.clear()
        if self.timing_enabled and key!=self._wanted:
            self._count_request('changed');self._wanted_since=time.monotonic()
        selection=getattr(self,'provider_selection',None)
        if selection is not None:key=(*key,selection)
        self._wanted=key
        if self.pending and self.pending[0]!=key and self.pending[1].cancel():
            if self.timing_enabled:self._count_request('cancelled_before_start')
            self.pending=None
        if self.pending and self.pending[1].done():
            old,future=self.pending;self.pending=None
            try:
                value=future.result()
                old_selection=old[-1] if old and getattr(old[-1],'is_map_provider',False) else None
                if old_selection==getattr(self,'provider_selection',None):self.ready[old]=value
                self.error=None
                if self.timing_enabled:
                    self._count_request('collected')
                    if old==key and self._wanted_since is not None:self._request_timing['request_to_collection_seconds']=max(0,time.monotonic()-self._wanted_since)
                    finished=self._worker_timing.get('finished_at')
                    if finished is not None:self._request_timing['completion_to_collection_seconds']=max(0,time.monotonic()-finished)
                if old[0]=='3d' and old in self.ready:self.latest3d=(old,self.ready[old])
            except CancelledError:pass
            except Exception as error:
                old_selection=old[-1] if old and getattr(old[-1],'is_map_provider',False) else None
                if old_selection==getattr(self,'provider_selection',None):self.failed[old]=f'Offline map unavailable: {type(error).__name__}: {error}'
            while len(self.failed)>4:self.failed.pop(next(iter(self.failed)))
            while len(self.ready)>4:self.ready.popitem(last=False)
        self.error=self.failed.get(key)
        if key in self.ready:
            if self.timing_enabled:self._count_request('cache_hits')
            self.ready.move_to_end(key);return self.ready[key]
        if self.pending is None and self.error is None:
            if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='offline-map')
            job=partial(self._timed_render,queued=time.monotonic(),requested=self._wanted_since) if self.timing_enabled else self._render
            if self.timing_enabled:self._count_request('submitted')
            self.pending=key,self.pool.submit(job,key)
            self.pending[1].add_done_callback(self._completed)
        return None
    def _render3d(self,key):
        from geometry import HeightField,Vec,Mesh,Model,Camera,render,unit
        import math
        began=time.monotonic()
        center,span,mw,mh,width,height,yaw,tilt,exaggeration,camera_mix=key
        from data_paths import data_root
        selected_catalogue=(data_root()/'elevation.json').is_file()
        field_key=(center,span,mw,mh,exaggeration)
        if selected_catalogue:
            from local_elevation import revision
            field_key=(*field_key,revision())
        if field_key in self.meshes:
            field,mesh=self.meshes[field_key];self.meshes.move_to_end(field_key)
            nx,nz=field.nx,field.nz;values=field.values
        else:
            nx=65;nz=2*max(4,min(64,round(mh/max(1,mw)*nx)))
            view=self.module.Viewport(center,span,nx,nz//2)
            rows,fine,stats=self.engine.atlas.raster(center,span,nx,nz//2)
            heights=None;nodata=None
            if selected_catalogue:
                from elevation_display import sample as display_heights
                heights=display_heights(view)
            elif span>5 and self.engine.terrain:
                heights,_,_=self.engine.terrain.sample(view);nodata=self.engine.terrain.nodata
            values=[];known=[]
            for z in range(nz):
                for x in range(nx):
                    value=heights[z][x] if heights is not None else (fine[z][x]-1)*5 if fine[z][x]!=255 else 0 if rows[z][x]==0 else None
                    valid=value is not None and (nodata is None or value!=nodata)
                    known.append(valid);values.append(value*exaggeration if valid else 0)
            if not any(known):raise ValueError('No offline elevation coverage for this patch')
            step=span*1000/(nx-1)
            field=HeightField(nx,nz,Vec(-span*500,0,-(nz-1)*step/2),step,step,tuple(values),'meters')
            mesh=field.mesh();mesh=Mesh(mesh.vertices,tuple(t for t in mesh.triangles if all(known[i] for i in t[:3])))
            self.meshes[field_key]=(field,mesh)
            while len(self.meshes)>2:self.meshes.popitem(last=False)
        target=(max(values)+min(values))/2;distance=span*1000*1.10
        origin=Vec(-math.sin(yaw)*distance*math.cos(tilt),target+distance*math.sin(tilt),-math.cos(yaw)*distance*math.cos(tilt))
        sx=span*1000*1.25;sy=sx/max(.3,width/max(1,height*2))
        elevation=tilt
        bird_camera=Camera(origin=origin,yaw=yaw,elevation=tilt,span_x=sx,span_y=sy,focal=distance)
        if camera_mix<1:
            peak=values.index(max(values));tx=field.origin.x+(peak%nx)*field.dx;tz=field.origin.z+(peak//nx)*field.dz
            distance=span*1000*.45;ex=tx-math.sin(yaw)*distance;ez=tz-math.cos(yaw)*distance
            ground=field.height(max(field.origin.x,min(field.origin.x+(nx-1)*field.dx,ex)),max(field.origin.z,min(field.origin.z+(nz-1)*field.dz,ez)))
            ey=ground+max(250,span*1000*.012)+(tilt-.75)*span*1000*.25
            target=min(values)+.38*(max(values)-min(values))
            elevation=math.atan2(ey-target,distance)
            origin=Vec(ex,ey,ez);sy=span*1000*.18;sx=sy*max(.3,width/max(1,height*2))
        camera=Camera(origin=origin,yaw=yaw,elevation=elevation,span_x=sx,span_y=sy,focal=distance)
        from geometry import interpolate_camera
        camera=interpolate_camera(camera,bird_camera,camera_mix)
        from lighting import environment
        cells,_=render(Model(field,mesh,camera,unit(Vec(-.6,1,-.5))),width,height,cast_shadows=False,environment=environment(0))
        return Image(width,height,tuple(cells[x,y] for y in range(height) for x in range(width)),f'{nx} x {nz} samples / Z {exaggeration:g}x',(),time.monotonic()-began)
    def close(self):
        if getattr(self,'_closed',False):return
        self._closed=True
        cleanup=getattr(self,'_retire_provider',None)
        selected=getattr(self,'_provider_lifecycle',False)
        if self.pool:
            if cleanup and selected:
                self._wanted=None;self.completion_wakeup=None
                if self.pending:self.pending[1].cancel()
                self.pool.submit(cleanup)
                self.pool.shutdown(wait=False,cancel_futures=False)
            else:self.pool.shutdown(wait=True,cancel_futures=True)
        self.pending=None;self.ready.clear();self.meshes.clear();self.regions.ready.clear();self.latest3d=None
