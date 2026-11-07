"""Portable terminal display of the shared height catalogue, including overviews.

No NumPy/GDAL dependency on Nokia. Analysis stays on local_elevation's fine grid;
only display sampling uses reduced levels. The graphical reader keeps its vector
height/shading path rather than decoding a terminal terrain pack.
"""
import math
import types
from pathlib import Path


def configure(engine):
    from data_paths import data_root
    if getattr(engine,'_desktop_dem_signature',None) is not None or not (data_root()/'elevation.json').is_file():return
    if not hasattr(engine,'_catalogue_original_rgb'):
        engine._catalogue_original_rgb=engine._rgb_terrain
        engine._rgb_terrain=types.MethodType(render,engine)
    from local_elevation import revision
    identity=repr(revision())
    if getattr(engine,'_catalogue_identity',None)!=identity:
        import hashlib
        engine._catalogue_identity=identity
        engine.cache_identity=hashlib.sha256(identity.encode()+Path(__file__).read_bytes()).hexdigest()
        engine.cache.clear()
        if engine.prepared:
            engine.prepared.fingerprint=[v for v in engine.prepared.fingerprint if not v[0].startswith('elevation-catalogue:')]
            engine.prepared.fingerprint.append(('elevation-catalogue:v1',engine.cache_identity))


def sample(view):
    from local_elevation import display_sources,read_index,_sample_entry
    step=view.span/max(1,view.width-1)
    pixels=step*1000*min(1,view.cell_aspect/2)
    entries=[]
    for path in display_sources(pixels):
        m=read_index(path,path.stat().st_mtime_ns,path.stat().st_size)
        entries.append((path,m))
    def rank(entry):
        metres=abs(entry[1]['latitude_step'])*111320
        return (metres>pixels,-metres if metres<=pixels else metres)
    entries.sort(key=rank)
    buckets={}
    for entry in entries:
        m=entry[1];e=m['extent']
        for bx in range(math.floor(e['xmin']*4),math.floor(e['xmax']*4)+1):
            for by in range(math.floor(e['ymin']*4),math.floor(e['ymax']*4)+1):buckets.setdefault((bx,by),[]).append(entry)
    dx=step/(111.32*math.cos(math.radians(view.center[0])))
    dy=step*view.cell_aspect/2/111.32
    result=[]
    for y in range(view.height*2):
        lat=view.center[0]-(y-(view.height*2-1)/2)*dy;row=[]
        for x in range(view.width):
            lon=view.center[1]+(x-(view.width-1)/2)*dx
            value=None
            for path,m in buckets.get((math.floor(lon*4),math.floor(lat*4)),()):
                value=_sample_entry(path,m,lat,lon,clamp_edges=True)
                if value is not None:break
            row.append(value)
        result.append(row)
    return result


def render(engine,view,terrain):
    # Flat base keeps mapped water/land, without decoding legacy terrain-next.n8t.
    frame,legend=engine._catalogue_original_rgb(view,False)
    if not terrain:return frame,legend
    heights=sample(view);known=[v for row in heights for v in row if v is not None]
    if not known:return frame,'No selected-area elevation coverage'
    interval=5 if view.span<=2.5 else 10 if view.span<=5 else 25
    low=math.floor(min(known)/interval)*interval;high=math.floor(max(known)/interval+1)*interval
    kinds,_,_=engine.atlas.raster(view.center,view.span,view.width,view.height)
    colors={}
    for y in range(view.height):
        for x in range(view.width):
            _,a,b=frame[y*view.width+x];pair=[a,b]
            for j in (0,1):
                height=heights[y*2+j][x]
                if kinds[y*2+j][x]==0 or height is None:continue
                band=math.floor(height/interval)*interval
                if band not in colors:colors[band]=engine.palette.band_color(band,low,high)
                pair[j]=colors[band]
            frame[y*view.width+x]=(' ' if pair[0]==pair[1] else '▀',*pair)
    return frame,f'Selected-area elevation · {interval} m display bands · local overviews'
