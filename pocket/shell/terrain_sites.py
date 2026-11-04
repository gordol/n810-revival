"""Bounded local candidate screening against an observed target."""
import math
import time
from functools import lru_cache
from terrain_elevation import calculate,coordinate,classify_path


def search(start,end,*,radius_km=2,frequency_mhz=144.39,tx_height_m=2,rx_height_m=10,cancelled=lambda:False):
    center=coordinate(start);coordinate(end)
    if not math.isfinite(radius_km) or not .1<=radius_km<=100:raise ValueError('Search radius must be 0.1–100 km')
    candidates=[];skipped=0
    for north in range(-2,3):
        for east in range(-2,3):
            offset=math.hypot(north,east)*radius_km/2
            if offset>radius_km:continue
            if cancelled():return None
            lat=center[0]+north*radius_km/2/111.32
            lon=center[1]+east*radius_km/2/(111.32*math.cos(math.radians(center[0])))
            position=f'{lat:.7f},{lon:.7f}'
            try:r=calculate(position,end,frequency_mhz=frequency_mhz,tx_height_m=tx_height_m,rx_height_m=rx_height_m,count=129)
            except ValueError:skipped+=1;continue
            if r['coarse'] or r['missing_samples']:skipped+=1;continue
            interior=r['samples'][1:-1]
            clearance=min(row['fresnel_clearance_m'] for row in interior)
            candidates.append(dict(position=(lat,lon),offset_km=offset,north_km=north*radius_km/2,east_km=east*radius_km/2,
                                   clearance_m=clearance,los=r['sampled_los'],fresnel=r['sampled_fresnel'],profile=r))
    candidates.sort(key=lambda c:(c['los']=='clear',c['fresnel']=='clear',c['clearance_m'],-c['offset_km']),reverse=True)
    if not candidates:raise ValueError('No candidates with detailed elevations. Install finer terrain for this area.')
    return dict(candidates=candidates,skipped=skipped,radius_km=radius_km,center=center,target=coordinate(end))


@lru_cache(maxsize=16384)
def _cached_path(start,end,frequency,tx,rx,revision):
    return classify_path(start,end,frequency_mhz=frequency,tx_height_m=tx,rx_height_m=rx)

def cached_path(start,end,frequency,tx,rx):
    from local_elevation import revision
    return _cached_path(start,end,frequency,tx,rx,revision())
cached_path.cache_clear=_cached_path.cache_clear
cached_path.cache_info=_cached_path.cache_info


def viewshed(start,*,radius_km=5,frequency_mhz=144.39,tx_height_m=2,rx_height_m=2,cancelled=lambda:False,grid_steps=6,progress=None,viewport=None,refine_only=False):
    center=coordinate(start)
    if not math.isfinite(radius_km) or not .1<=radius_km<=100:raise ValueError('Overlay radius must be 0.1–100 km')
    if not all(math.isfinite(v) for v in (frequency_mhz,tx_height_m,rx_height_m)) or not 0<frequency_mhz<=100000 or not 0<=tx_height_m<=10000 or not 0<=rx_height_m<=10000:
        raise ValueError('Invalid frequency or antenna height')
    if type(grid_steps) is not int or not 6<=grid_steps<=24:raise ValueError('Invalid overlay detail')
    cells=[];levels=[level for level in (1,2,5,10,20,50,100) if level<radius_km]+[radius_km]
    inner=0;last_publish=time.monotonic();published=0
    def snapshot(done=False):
        return dict(center=center,radius_km=radius_km,step_km=radius_km/grid_steps,grid_steps=grid_steps,cells=list(cells),frequency_mhz=frequency_mhz,tx_height_m=tx_height_m,rx_height_m=rx_height_m,complete=done)
    if viewport is not None:
        view_center,span,width,height=viewport
        view_center=coordinate(f'{view_center[0]},{view_center[1]}')
        if not math.isfinite(span) or not .01<=span<=2000 or not 2<=width<=192 or not 2<=height<=128:
            raise ValueError('Invalid coverage viewport')
        step=span/(width-1)
        points=sorted(((row,col) for row in range(height) for col in range(width)),
                      key=lambda p:((view_center[0]-(p[0]-(height-1)/2)*step*2/111.32-center[0])*111.32)**2+
                      ((view_center[1]+(p[1]-(width-1)/2)*step/(111.32*math.cos(math.radians(view_center[0])))-center[1])*111.32*math.cos(math.radians(center[0])))**2)
        for row,col in points:
            if cancelled():return None
            lat=view_center[0]-(row-(height-1)/2)*step*2/111.32
            lon=view_center[1]+(col-(width-1)/2)*step/(111.32*math.cos(math.radians(view_center[0])))
            distance=math.hypot((lat-center[0])*111.32,(lon-center[1])*111.32*math.cos(math.radians(center[0])))
            if distance>radius_km:continue
            try:r=cached_path(start,f'{lat:.7f},{lon:.7f}',frequency_mhz,tx_height_m,rx_height_m)
            except ValueError:r=dict(los='unknown',fresnel='unknown')
            cells.append(dict(position=(lat,lon),los=r['los'],fresnel=r['fresnel'],step_km=step,
                              sample_spacing_m=r.get('resolution_m',100),raster_km=(step,step*2),
                              inner_radius_km=0,outer_radius_km=distance))
            if progress and ((published==0 and len(cells)>=16) or time.monotonic()-last_publish>=.5):
                progress(snapshot());published=len(cells);last_publish=time.monotonic()
    for outer in (() if refine_only else levels):
        step=outer/grid_steps
        points=sorted(((north,east) for north in range(-grid_steps,grid_steps+1) for east in range(-grid_steps,grid_steps+1)),key=lambda p:p[0]*p[0]+p[1]*p[1])
        for north,east in points:
            distance=math.hypot(north,east)*step
            if not inner<distance<=outer:continue
            if cancelled():return None
            lat=center[0]+north*step/111.32
            lon=center[1]+east*step/(111.32*math.cos(math.radians(center[0])))
            status='unknown';fresnel='unknown';resolution=100
            try:
                r=cached_path(start,f'{lat:.7f},{lon:.7f}',frequency_mhz,tx_height_m,rx_height_m)
                status=r['los'];fresnel=r['fresnel'];resolution=r.get('resolution_m',100)
            except ValueError:pass
            # Yield the interpreter to map input/rendering between path tests.
            time.sleep(.001)
            cells.append(dict(position=(lat,lon),los=status,fresnel=fresnel,step_km=step,sample_spacing_m=resolution,inner_radius_km=inner,outer_radius_km=outer))
            if progress and ((published==0 and len(cells)>=16) or time.monotonic()-last_publish>=.5):
                progress(snapshot());published=len(cells);last_publish=time.monotonic()
        inner=outer
    result=snapshot(True)
    if progress:progress(result)
    return result
