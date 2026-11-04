"""Laptop-only fixed physical elevation colors; relative rendering is preserved."""
import hashlib,importlib.util
from concurrent.futures import CancelledError
from pathlib import Path
from offline_map import Renderer,map_cache_directory

# Metres above sea level, followed by RGB. Water is a separate land-cover class.
BREAKPOINTS=((0,(18,43,39)),(25,(29,70,47)),(75,(61,99,51)),(150,(94,114,57)),
             (350,(107,113,65)),(750,(116,118,75)),(1500,(143,130,102)),
             (2500,(164,158,145)),(3500,(198,199,196)),(4300,(237,240,241)))
PALETTE_VERSION='fixed-geographic-elevation-low-relief-v2'


def fixed_color(height):
    if height<=BREAKPOINTS[0][0]:return BREAKPOINTS[0][1]
    for (low,a),(high,b) in zip(BREAKPOINTS,BREAKPOINTS[1:]):
        if height<=high:
            fraction=(height-low)/(high-low)
            return tuple(round(x+(y-x)*fraction) for x,y in zip(a,b))
    return BREAKPOINTS[-1][1]


def engine_class(module):
    class GeographicEngine(module.Engine):
        def __init__(self,*args,palette_mode='fixed',**kwargs):
            super().__init__(*args,**kwargs)
            self.cancel_requested=None
            self._base_fingerprint=list(self.prepared.fingerprint) if self.prepared else []
            self.palette_mode=None;self.set_palette_mode(palette_mode)
        def set_palette_mode(self,mode):
            if mode not in ('fixed','relative'):raise ValueError('Unknown geographic palette')
            if self.palette_mode==mode:return
            self.palette_mode=mode
            self.cache_identity=(PALETTE_VERSION,mode,BREAKPOINTS)
            if self.prepared:
                source_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                self.prepared.fingerprint=self._base_fingerprint+[(PALETTE_VERSION,repr((mode,BREAKPOINTS,source_hash)))]
            self.clear_cache()
        def _abort_if_needed(self):
            if self.cancel_requested is not None and self.cancel_requested():raise CancelledError()
        def _lines(self,*args,**kwargs):
            self._abort_if_needed()
            result=super()._lines(*args,**kwargs)
            self._abort_if_needed()
            return result
        def _rgb_terrain(self,view,terrain):
            self._abort_if_needed()
            if self.palette_mode=='relative':return super()._rgb_terrain(view,terrain)
            p=self.palette;rows,fine,stats=self.atlas.raster(view.center,view.span,view.width,view.height)
            self._abort_if_needed()
            heights=None
            if terrain and self.terrain:
                heights,_,levels=self.terrain.sample(view);self.stats['height_levels']=levels
            self._abort_if_needed()
            nodata=self.terrain.nodata if heights is not None else None
            colors={}
            def color(kind,value,height):
                if kind==0:return p.WATER
                if not terrain:return p.LAND
                if height is not None and height!=nodata:key=('metres',height)
                elif value!=255:key=('metres',(value-1)*5)
                else:key=('class',kind)
                if key not in colors:colors[key]=fixed_color(key[1]) if key[0]=='metres' else p.REGIONAL[key[1]]
                return colors[key]
            frame=[]
            for y in range(view.height):
                self._abort_if_needed()
                for x in range(view.width):
                    a=color(rows[y*2][x],fine[y*2][x],heights[y*2][x] if heights is not None else None)
                    b=color(rows[y*2+1][x],fine[y*2+1][x],heights[y*2+1][x] if heights is not None else None)
                    frame.append((' ' if a==b else '▀',a,b))
            self.stats.update(stats)
            legend='Fixed elevation metres: 0/25/75/150/350/750/1500/2500/3500/4300 · coarse bands without heights'
            if stats['unknown']==stats['samples']:legend='No offline elevation coverage'
            if not terrain:legend='Flat land/water · terrain OFF'
            return frame,legend
    return GeographicEngine


class PaletteRenderer(Renderer):
    def __init__(self,*args,palette_mode='fixed',**kwargs):
        super().__init__(*args,**kwargs);self.palette_mode=palette_mode
    def region_compatible(self,span):return self.palette_mode=='fixed' or super().region_compatible(span)
    def set_palette_mode(self,mode):
        if self.pending is not None:return False
        if mode==self.palette_mode:return True
        self.palette_mode=mode
        if self.engine is not None:self.engine.set_palette_mode(mode)
        self.ready.clear();self.failed.clear();self.regions.ready.clear();self._wanted=None
        return True
    def _render(self,key):
        if self.module is None:
            spec=importlib.util.spec_from_file_location('trial_geographic_engine',self.root/'n810-map-next.py')
            self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
            self.engine=engine_class(self.module)(self.maps,'rgb',cache_directory=map_cache_directory(),palette_mode=self.palette_mode)
        return super()._render(key)
