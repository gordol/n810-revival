"""Desktop-only DEM shading, sampled on demand; prepared RGB views retain disk caching."""
import hashlib,json,platform,types
from functools import lru_cache
from pathlib import Path


def enabled():
    import os
    return os.environ.get('POCKET_DESKTOP_TERRAIN','1')!='0' and platform.machine().lower() not in ('armv6l','armv7l','armv7','arm')


def sources():
    from local_elevation import sources as installed
    return installed()

def signature():
    from data_paths import data_root,content_identity
    renderers=[Path(__file__).with_name(n) for n in ('map_hydrography.py','map_geography.py')]
    data=[data_root()/name for name in ('shoreline-puget.json.gz','geography/index.json','map-geography.json.gz','hydrography/index.json')]
    return tuple(content_identity(p) for p in [*sources(),*renderers,*data])

@lru_cache(maxsize=128)
def metadata(path,modified,size):
    value=json.loads(path.read_text());value.pop('maximum_bounds',None)
    return value


def configure(engine):
    if not enabled():return
    try:import numpy
    except ImportError:return
    identity=signature()
    if getattr(engine,'_desktop_dem_signature',None)==identity:return
    engine._desktop_dem_signature=identity;engine.cache.clear()
    engine.cache_identity=hashlib.sha256(repr(identity).encode()).hexdigest()
    if engine.prepared:
        engine.prepared.fingerprint=[v for v in engine.prepared.fingerprint if not v[0].startswith('desktop-dem:')]
        engine.prepared.fingerprint.append(('desktop-dem:v3',hashlib.sha256(repr(identity).encode()+Path(__file__).read_bytes()+Path(__file__).with_name('desktop_shoreline.py').read_bytes()).hexdigest()))
    if not hasattr(engine,'_original_rgb_terrain'):engine._original_rgb_terrain=engine._rgb_terrain
    engine._rgb_terrain=types.MethodType(render,engine)
    if not hasattr(engine,'_original_map_lines'):engine._original_map_lines=engine._lines
    engine._lines=types.MethodType(geography_lines,engine)

def geography_lines(engine,view,streams=False):
    from map_geography import covers
    return ({},0) if covers(view) else engine._original_map_lines(view,streams)


def sample(view):
    import numpy as np
    import zlib
    paths=sources();packs=[(p,metadata(p,p.stat().st_mtime_ns,p.stat().st_size)) for p in paths]
    packs.sort(key=lambda item:abs(item[1]['longitude_step']*item[1]['latitude_step']),reverse=True)
    h,w=view.height*2,view.width
    dx=view.span/max(1,w-1)/(111.32*np.cos(np.radians(view.center[0])))
    dy=view.span/max(1,w-1)*view.cell_aspect/2/111.32
    lon=view.center[1]+(np.arange(w)-(w-1)/2)*dx
    lat=view.center[0]-(np.arange(h)-(h-1)/2)*dy
    result=np.full((h,w),np.nan);spacing=np.full((h,w),np.inf)
    for path,m in packs:
        xx=(lon-m['longitude_first'])/m['longitude_step'];yy=(lat-m['latitude_first'])/m['latitude_step']
        cols=np.where((xx>=0)&(xx<m['nx']-1))[0];rows=np.where((yy>=0)&(yy<m['nz']-1))[0]
        if not len(cols) or not len(rows):continue
        xs=xx[cols];ys=yy[rows];ix=xs.astype(int);iy=ys.astype(int)
        values=np.full((len(rows),len(cols)),np.nan)
        cache={}
        def gather(x,y):
            x,y=np.broadcast_arrays(x,y);out=np.full(x.shape,np.nan)
            for tx,ty in set(zip((x//256).ravel(),(y//256).ravel())):
                key=f'{tx},{ty}';item=m['tiles'].get(key)
                if item is None:continue
                if key not in cache:
                    raw=(path.parent/item['file']).read_bytes()
                    if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('DEM integrity failure')
                    cache[key]=np.frombuffer(zlib.decompress(raw),dtype='<i2').reshape(item['height'],item['width'])
                mask=(x//256==tx)&(y//256==ty);out[mask]=cache[key][y[mask]%256,x[mask]%256]
            out[out==m['nodata']]=np.nan
            return out
        fx=xs-ix;fy=(ys-iy)[:,None]
        for ox,oy,weight in ((0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),(0,1,(1-fx)*fy),(1,1,fx*fy)):
            v=gather(ix[None,:]+ox,iy[:,None]+oy)
            if ox==oy==0:values=v*weight
            else:values+=v*weight
        rr,cc=np.meshgrid(rows,cols,indexing='ij');valid=np.isfinite(values)
        result[rr[valid],cc[valid]]=values[valid]
        spacing[rr[valid],cc[valid]]=abs(m['latitude_step'])*111320
    return result,spacing


def render(engine,view,terrain):
    frame,legend=engine._original_rgb_terrain(view,terrain)
    if view.width<2:return frame,legend
    import numpy as np
    heights,spacing=sample(view);known=np.isfinite(heights)
    # Smooth colour interpolation from actual heights, with slope relief at display resolution.
    filled=np.where(known,heights,0)
    metres=max(.1,view.ground_m_per_halfcell)
    gy,gx=np.gradient(filled,metres,metres)
    shade=np.clip((1-gx*.8+gy*.8)/np.sqrt(1+gx*gx+gy*gy),.4,1.3)
    stops=np.array([-100,0,100,300,700,1500,3000,5000])
    colors=np.array([[23,68,60],[35,88,51],[65,106,55],[106,121,66],[142,132,96],[163,151,130],[210,206,197],[245,245,245]])
    rgb=np.stack([np.interp(filled,stops,colors[:,i]) for i in range(3)],axis=-1)
    rgb=np.clip(rgb*shade[...,None],0,255).astype(np.uint8)
    # Keep existing mapped water and all roads/streams, which Engine adds after this call.
    rows,_,_=engine.atlas.raster(view.center,view.span,view.width,view.height)
    from desktop_shoreline import mask
    water=mask(view)
    for y in range(view.height):
        for x in range(view.width):
            char,a,b=frame[y*view.width+x];pair=[a,b]
            for j in (0,1):
                yy=2*y+j
                land=(water[yy,x]>0) if water is not None and water[yy,x]>=0 else rows[yy][x]!=0
                if not land:pair[j]=engine.palette.WATER
                elif terrain and known[yy,x]:pair[j]=tuple(map(int,rgb[yy,x]))
                elif rows[yy][x]==0:pair[j]=engine.palette.LAND
            frame[y*view.width+x]=(' ' if pair[0]==pair[1] else '▀',*pair)
    if not terrain or not known.any():return frame,legend
    return frame,f'Local DEM · {np.nanmin(spacing[known]):.0f}–{np.nanmax(spacing[known]):.0f} m source spacing · cached desktop relief'
