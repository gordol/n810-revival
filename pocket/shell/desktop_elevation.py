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

@lru_cache(maxsize=256)
def metadata(path,modified,size):
    from local_elevation import read_index
    return read_index(path,modified,size)


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


def sample(view,land_mask=None,source_pixel_metres=None):
    import numpy as np
    import zlib
    h,w=view.height*2,view.width
    dx=view.span/max(1,w-1)/(111.32*np.cos(np.radians(view.center[0])))
    dy=view.span/max(1,w-1)*view.cell_aspect/2/111.32
    lon=view.center[1]+(np.arange(w)-(w-1)/2)*dx
    lat=view.center[0]-(np.arange(h)-(h-1)/2)*dy
    result=np.full((h,w),np.nan);spacing=np.full((h,w),np.inf)
    pixel_metres=(source_pixel_metres if source_pixel_metres is not None else
                  view.span*1000/max(1,w-1)*min(1,view.cell_aspect/2))
    from local_elevation import display_sources
    paths=sources()
    if any('overviews' in metadata(p,p.stat().st_mtime_ns,p.stat().st_size) for p in paths):paths=display_sources(pixel_metres,paths)
    packs=[(p,metadata(p,p.stat().st_mtime_ns,p.stat().st_size)) for p in paths]
    packs.sort(key=lambda item:abs(item[1]['longitude_step']*item[1]['latitude_step']),reverse=True)
    for path,m in packs:
        xx=(lon-m['longitude_first'])/m['longitude_step'];yy=(lat-m['latitude_first'])/m['latitude_step']
        cols=np.where((xx>=-.5)&(xx<=m['nx']-.5))[0];rows=np.where((yy>=-.5)&(yy<=m['nz']-.5))[0]
        if not len(cols) or not len(rows):continue
        source_metres=abs(m['latitude_step'])*111320
        region=np.ix_(rows,cols)
        needed=(~np.isfinite(result[region])) | (spacing[region]>max(pixel_metres,source_metres)*(1+1e-9))
        if land_mask is not None:needed &= land_mask[region]
        if not needed.any():continue
        rr,cc=np.nonzero(needed)
        xs=np.clip(xx[cols[cc]],0,m['nx']-1);ys=np.clip(yy[rows[rr]],0,m['nz']-1)
        ix=np.minimum(xs.astype(int),m['nx']-2);iy=np.minimum(ys.astype(int),m['nz']-2)
        values=np.full(xs.shape,np.nan)
        cache={}
        def gather(x,y):
            x,y=np.broadcast_arrays(x,y);out=np.full(x.shape,np.nan)
            tile_x,tile_y=x//256,y//256
            columns=(m['nx']+255)//256
            for number in np.unique(tile_y*columns+tile_x):
                tx,ty=int(number%columns),int(number//columns)
                key=f'{tx},{ty}';item=m['tiles'].get(key)
                if item is None:continue
                if key not in cache:
                    from local_elevation import tile
                    values,stride=tile(path,m['_index_stamp'],int(tx),int(ty))
                    cache[key]=np.frombuffer(values,dtype=np.int16).reshape(item['height'],stride)
                mask=(tile_x==tx)&(tile_y==ty);out[mask]=cache[key][y[mask]%256,x[mask]%256]
            out[out==m['nodata']]=np.nan
            return out
        fx=xs-ix;fy=ys-iy
        for ox,oy,weight in ((0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),(0,1,(1-fx)*fy),(1,1,fx*fy)):
            v=gather(ix+ox,iy+oy)
            if ox==oy==0:values=v*weight
            else:values+=v*weight
        valid=np.isfinite(values)
        result[rows[rr[valid]],cols[cc[valid]]]=values[valid]
        spacing[rows[rr[valid]],cols[cc[valid]]]=abs(m['latitude_step'])*111320
    return result,spacing


def pixel_samples(engine,view,source_pixel_metres=None):
    """Dense semantic pixels without building an intermediate glyph-cell frame."""
    if not getattr(engine,'_desktop_dem_signature',None):return None
    import numpy as np
    from array import array
    from desktop_shoreline import mask
    from offline_map import _Q5,_Q6,map_rgb
    water=mask(view)
    heights,_=sample(view,land_mask=water!=0 if water is not None else None,
                     source_pixel_metres=source_pixel_metres)
    rows,_,_=engine.atlas.raster(view.center,view.span,view.width,view.height)
    atlas=np.asarray(rows)
    land=np.where(water>=0,water>0,atlas!=0) if water is not None else atlas!=0
    known=np.isfinite(heights)
    filled=np.where(known,heights,0)
    metres=max(.1,view.ground_m_per_halfcell)
    gy,gx=np.gradient(filled,metres,metres)
    shade=np.clip((1-gx*.8+gy*.8)/np.sqrt(1+gx*gx+gy*gy),.4,1.3)
    stops=np.array([-100,0,100,300,700,1500,3000,5000])
    colors=np.array([[23,68,60],[35,88,51],[65,106,55],[106,121,66],[142,132,96],[163,151,130],[210,206,197],[245,245,245]])
    rgb=np.stack([np.interp(filled,stops,colors[:,i]) for i in range(3)],axis=-1)
    rgb=np.clip(rgb*shade[...,None],0,255).astype(np.uint8)
    q5=np.asarray(_Q5,dtype=np.uint32);q6=np.asarray(_Q6,dtype=np.uint32)
    packed=(q5[rgb[:,:,0]]<<16)|(q6[rgb[:,:,1]]<<8)|q5[rgb[:,:,2]]
    unknown=land&~known
    if np.any(unknown):
        from offline_map import map_rgb
        frame,_=engine._original_rgb_terrain(view,True)
        fallback=np.empty((view.height*2,view.width),dtype=np.uint32)
        for row in range(view.height):
            cells=frame[row*view.width:(row+1)*view.width]
            fallback[row*2]=[map_rgb(top) for _,top,_ in cells]
            fallback[row*2+1]=[map_rgb(bottom) for _,_,bottom in cells]
        packed[unknown]=fallback[unknown]
    packed[~land]=map_rgb(engine.palette.WATER)
    result=array('I');result.frombytes(np.ascontiguousarray(packed,dtype=np.uint32).tobytes())
    return result,view.width,view.height*2

def render(engine,view,terrain):
    frame,legend=engine._original_rgb_terrain(view,terrain)
    if view.width<2:return frame,legend
    import numpy as np
    from desktop_shoreline import mask
    water=mask(view)
    heights,spacing=sample(view,land_mask=water!=0 if water is not None else None);known=np.isfinite(heights)
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
