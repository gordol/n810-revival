"""Pinned local terrain cache plus one display-scale vector layer.

Terrain patches stay at fixed geographic bounds. They never replace the entire
viewport when a zoom happens to fit inside a patch. No new measured data.
"""
import gzip,json,math,time,importlib.util,hashlib
from functools import lru_cache
from array import array
from pathlib import Path
from types import MappingProxyType
from concurrent.futures import CancelledError
from offline_map import Renderer as VanillaRenderer,Image
from packed_map import Renderer as PreparedRenderer,DEFAULT as PREPARED_DEFAULT
from dataclasses import dataclass
import os,struct,sys,io
from paint import ink

HERE=Path(__file__).resolve().parent/'map-assets/accepted-preview'

RECEIPT_SHA256='66d4272bdcaa6903fa25cfd669a60142a324f385af787eee14da35ee6f83633d'
SOURCES_SHA256='863f28e6a56acc9090114944bedd9e55e6573358c1cacb7362fa208a20853c02'
PALETTE_SHA256='bba79870ecff7d1d686530c3fdb32973464492b22e5590e49625e77af472d636'
PALETTE_SOURCE=Path(__file__).with_name('map_palette.py')

def file_digest(path):
    value=hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda:source.read(65536),b''):value.update(chunk)
    return value.hexdigest()

def pinned_json(path,digest):
    with path.open('rb') as source:raw=source.read(65537)
    if len(raw)>65536 or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Map asset identity differs: '+path.name)
    return json.loads(raw)

def decode_terrain(raw,row):
    """Decode only the fixed, bounded compact terrain representation."""
    if len(raw)>1024*1024:raise ValueError('Terrain cache too large')
    if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Terrain cache differs from pinned receipt')
    width,height=row['width'],row['height']
    if not (2<=width<=800 and 1<=height<=400):raise ValueError('Invalid terrain dimensions')
    expected=width*height*8
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as source:
        header=source.read(33)
        if len(header)!=33 or header[:5]!=b'N8TC1':raise ValueError('Invalid terrain header')
        w,h,lat,lon,span=struct.unpack('<HHddd',header[5:])
        if (w,h)!=(width,height) or not (-85<=lat<=85 and -180<=lon<=180 and 0<span<=2000):raise ValueError('Invalid terrain dimensions')
        payload=source.read(expected+1)
    if len(payload)!=expected:raise ValueError('Invalid terrain payload length')
    values=array('I');values.frombytes(payload)
    if sys.byteorder!='little':values.byteswap()
    if any(v>0xffffff for v in values):raise ValueError('Invalid terrain color')
    return dict(version=1,width=width,height=height,center=(lat,lon),span=span,cells=values)

@lru_cache(maxsize=1)
def terrain_data():
    receipt=pinned_json(HERE/'terrain-cache/RECEIPT.json',RECEIPT_SHA256)
    result=[]
    for name in ('overview','rainier','detail','lakewood-fine'):
        row=receipt['layers'][name];path=HERE/'terrain-cache'/f'{name}.rgb.gz'
        if path.stat().st_size>1024*1024:raise ValueError('Terrain cache too large')
        with path.open('rb') as source:raw=source.read(1024*1024+1)
        result.append((name,decode_terrain(raw,row)))
    return tuple(result)


def sample_terrain(view,layers,cancel=lambda:False):
    center,span,width,height=view.center,view.span,view.width,view.height
    # Sample each patch in its own projection, with the same geographic
    # pixel-center convention as the engine. Detail can cover part of a view.
    cells=[None]*(width*height);used=[]
    for name,source,values in layers:
        xs=[];ys=[]
        for x in range(width):
            lon=center[1]+(x-(width-1)/2)*span/max(1,width-1)/111.32/math.cos(math.radians(center[0]))
            xs.append(round(source.project(lon,center[0])[0]))
        for y in range(height*2):
            lat=center[0]-(y-(height*2-1)/2)*span/max(1,width-1)/111.32
            # The prepared image stores two independent terrain half-cells.
            yy=(source.center[0]-lat)*111.32*(source.width-1)/source.span+(source.height*2-1)/2
            ys.append(round(yy))
        touched=False
        for y in range(height):
            if not any(0<=ys[y*2+h]<source.height*2 for h in (0,1)):continue
            if cancel():raise CancelledError()
            for x,sx in enumerate(xs):
                if not 0<=sx<source.width:continue
                index=y*width+x;old=cells[index];colors=list(old or (None,None))
                for half in (0,1):
                    sy=ys[y*2+half]
                    if 0<=sy<source.height*2:
                        colors[half]=values[((sy//2)*source.width+sx)*2+sy%2];touched=True
                cells[index]=tuple(colors)
        if touched:used.append(name)
    if any(c is None or any(half is None for half in c) for c in cells):raise ValueError('No prepared terrain covers this view')
    result=[]
    for a,b in cells:
        result.append((' ' if a==b else '▀', (1<<48)|(a<<24)|b))
    return result,used


def draw_vectors(engine,view,result,roads=True):
    width=view.width
    lines,candidates=engine._lines(view) if roads else ({},0)
    streams,water_candidates=engine._lines(view,True)
    m=view.ground_m_per_halfcell
    opacity={0:round(256*max(0,min(1,(150-m)/120))),1:256,2:round(256*max(0,min(1,(250-m)/200)))}
    for marks,water in ((lines,False),(streams,True)):
        for (x,y),(char,role) in marks.items():
            i=y*width+x;_,style=result[i];bg=style&0xffffff
            rgb=((bg>>16)&255,(bg>>8)&255,bg&255);alpha=opacity[role]
            target=engine.rgb.CREEK if water else (173,181,159) if role==0 else (218,222,207)
            if not alpha:continue
            fg=tuple((b*(256-alpha)+t*alpha+128)//256 for b,t in zip(rgb,target))
            result[i]=(char,ink(*fg,background=rgb))
    return len(lines),len(streams)

@dataclass(frozen=True,slots=True)
class TerrainImage(Image):
    pack_status:object=None

class Renderer(PreparedRenderer):
    """Use accepted prepared colors only with matching original source data.

    Missing/mismatched assets, disabled terrain and uncovered views retain the
    ordinary renderer. Worker count, frame bounds and caches are inherited.
    """
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.pack_state={};self._asset_checked=False;self._asset_ready=False;self.asset_reason=None
    def prepared_available(self):
        if self._asset_checked:return self._asset_ready
        self._asset_checked=True
        try:
            if file_digest(PALETTE_SOURCE)!=PALETTE_SHA256:raise ValueError('Terrain palette identity differs')
            for row in pinned_json(HERE/'SOURCES.json',SOURCES_SHA256):
                relative=Path(row['file'])
                if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid map source path')
                path=self.maps/Path(*relative.parts[1:]) if relative.parts[0]=='maps' else self.root/relative
                if file_digest(path)!=row['sha256']:raise ValueError('Map source identity differs: '+row['file'])
            terrain_data();self._asset_ready=True
        except (OSError,ValueError,KeyError,TypeError) as error:self.asset_reason=str(error)
        return self._asset_ready
    def region_status(self,image=None):
        result=super().region_status(image)
        result['terrain_assets']=dict(available=self._asset_ready,checked=self._asset_checked,reason=self.asset_reason)
        result['pack']=dict(getattr(image,'pack_status',None) or self.pack_state)
        return result

    def _fallback(self,key):
        # Preserve the accepted prepared-only policy wherever packs are explicitly
        # configured or installed. Classic/3D and source-only portable launches
        # retain the original renderer without bypassing a configured pack reader.
        if key[0]=='map' and os.environ.get('CW_MAP_STYLE')!='classic' and (os.environ.get('N810_MAP_PACKS') or PREPARED_DEFAULT.is_dir()):
            return PreparedRenderer._render(self,key)
        return VanillaRenderer._render(self,key)

    def context_frame(self,center,span,width,height):
        from desktop_elevation import enabled
        from offline_map import raster_size
        width,height=raster_size(width,height) if enabled() else (max(2,min(160,width)),max(2,min(80,height)))
        return self._request(('context',tuple(center),float(span),width,height,True,True))

    def _terrain_layers(self):
        if hasattr(self,'terrain_layers'):return self.terrain_layers
        self.terrain_layers=[]
        for name,data in terrain_data():
            view=self.module.Viewport(data['center'],data['span'],data['width'],data['height'])
            self.terrain_layers.append((name,view,data['cells']))
        return self.terrain_layers

    def _render(self,key):
        if key!=self._wanted:raise CancelledError()
        if key and getattr(key[-1],'is_map_provider',False):
            if key[0] not in ('map','context'):raise ValueError('Imported maps provide prepared 2D views only')
            return self._render_provider(key)
        from desktop_elevation import enabled
        if enabled() and key[0] in ('map','context'):
            return VanillaRenderer._render(self,key)
        if key[0] not in ('map','context') or not key[5] or os.environ.get('CW_MAP_STYLE')=='classic' or not self.prepared_available():
            if key[0]=='context':raise ValueError('Local overview requires matching prepared terrain assets')
            return self._fallback(key)
        start=time.monotonic();_,center,span,width,height,terrain,roads=key
        if self.module is None:
            spec=importlib.util.spec_from_file_location('preview_map_layers',self.root/'n810-map-next.py')
            self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        if self.engine is None:self.engine=self.module.Engine(self.maps,'rgb')
        self.loading_phase='pack';view=self.module.Viewport(center,span,width,height)
        try:result,used=sample_terrain(view,self._terrain_layers(),lambda:key!=self._wanted)
        except ValueError:
            if key[0]=='context':raise
            self.pack_state=dict(state='fallback',reason='Outside accepted prepared terrain coverage')
            return self._fallback(key)
        road_cells,stream_cells=draw_vectors(self.engine,view,result,roads)
        state=dict(state='ready',pack='layers',coverage=True,reason=None,sources=used,
                   requested_spacing_m=1000*span/max(1,width-1),dem_resolution='DEM 329×487 m; local Lakewood 10×14 m',
                   sampling='fixed geographic terrain patches; display-scale vector strokes',road_cells=road_cells,stream_cells=stream_cells)
        self.pack_state=state;self.loading_phase='ready'
        return TerrainImage(width,height,tuple(result),'Local overview' if key[0]=='context' else 'Prepared terrain · one vector road/stream layer',(),time.monotonic()-start,view,'cached-overview' if key[0]=='context' else 'regional-pack',MappingProxyType(state))
