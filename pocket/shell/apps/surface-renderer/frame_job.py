"""Pure app frame preparation job; shared Inbox/Trace own execution and wakeup."""
from dataclasses import dataclass
import time
from core import Cell
from geometry import render,raster
from room import scene,portal_scene
from coverage_adapter import frame

@dataclass(frozen=True)
class Request:
    body_width:int
    body_height:int
    width:int
    height:int
    age:float
    x:float
    z:float
    yaw:float
    idle:float
    rift:bool
    portal:bool
    input_sequence:int
    requested_at:float
    outdoors:bool=False
    pitch:float=0.
    world_detail:bool=True
    approved_forest:bool=False


def resize_cells(source,width,height,target_width,target_height):
    """Scale RGB half samples; keep texture marks at one destination cell each."""
    if (width,height)==(target_width,target_height):return source
    packed=[]
    for y in range(height):
        upper=[];lower=[]
        for cell in source[y*width:(y+1)*width]:
            fore,back=(cell.color>>24)&0xffffff,cell.color&0xffffff
            a,b=(fore,back) if cell.char=='▀' else (back,fore) if cell.char=='▄' else (fore,fore) if cell.char=='█' else (back,back)
            upper.append(a);lower.append(b)
        packed.extend(upper);packed.extend(lower)
    # Sample half rows independently. Whole-cell repetition produces ABAB bands;
    # nearest half samples preserve crisp silhouettes without a full RGB filter.
    xs=[min(width-1,int((x+.5)*width/target_width)) for x in range(target_width)]
    ys=[min(height*2-1,int((y+.5)*height/target_height)) for y in range(target_height*2)]
    result=[];rows={}
    for y in range(target_height):
        upper=ys[y*2]*width;lower=ys[y*2+1]*width
        key=upper,lower
        row=rows.get(key)
        if row is None:
            colors=tuple(Cell('▀',(1<<48)|(packed[upper+x]<<24)|packed[lower+x]) for x in range(width))
            row=tuple(colors[x] for x in xs);rows[key]=row
        result.extend(row)
    for y in range(height):
        for x in range(width):
            cell=source[y*width+x]
            if cell.char in ('▀','▄','█',' '):continue
            xx=min(target_width-1,int((x+.5)*target_width/width))
            yy=min(target_height-1,int((y+.5)*target_height/height))
            # Glyph backgrounds already represent the lit surface beneath the mark.
            result[yy*target_width+xx]=cell
    return tuple(result)


def prepare(request,implementation,materials,*,scene_backend=None):
    r=request;stats={};started=time.monotonic()
    if r.outdoors:
        import outdoors
        model,env,origins,metadata=outdoors.scene(r.age,r.x,r.z,r.yaw,r.pitch,r.width,r.height,world_detail=r.world_detail,approved_forest=r.approved_forest)
        t=time.perf_counter();base,_=render(model,r.width,r.height,environment=env,cast_shadows=False,season='summer')
        stats['last_scene_triangles']=metadata['triangles'];stats['last_world_marmot']=int(metadata['marmot_detail']=='world')
        coverage=raster(model,r.width,r.height,False);stats['geometry_seconds']=time.perf_counter()-t
        recipes=outdoors.materials()
        if r.approved_forest:recipes={k:v for k,v in recipes.items() if k in ('terrain','metal')}
        t=time.perf_counter();output=dict(base)
        if r.approved_forest:
            forest=outdoors.forest_profile().overlay(model,coverage,base,r.width,r.height,seed=12345,season='summer')
            output.update(forest);stats['forest_overlay_cells']=len(forest)
        # Ground marks derive their ink from the approved forest's lit tones.
        # Existing forest glyphs are ineligible, so their detail is retained.
        patch=implementation.render(frame(model,coverage,output,r.width,r.height),recipes)
        output.update(patch.cells)
        output.update(outdoors.overlay(model,coverage,base,r.width,r.height,origins))
        stats['surface_seconds']=time.perf_counter()-t
    elif r.rift:
        from experience import render_experience
        output,details=render_experience(r.age,r.x,r.z,r.yaw,r.width,r.height,idle=r.idle,renderer=implementation,pitch=r.pitch)
        stats.update(experience_seconds=details['primary_seconds']+details['view_seconds'],secondary_view_seconds=details['view_seconds'],reality=1-details['dissolution'])
    else:
        model,env,coordinates=(portal_scene if r.portal else scene)(r.age,r.x,r.z,r.yaw,r.width,r.height,pitch=r.pitch)
        t=time.perf_counter()
        if scene_backend is None:
            base,_=render(model,r.width,r.height,environment=env,cast_shadows=False)
            coverage=raster(model,r.width,r.height,False)
        else:
            # The backend returns the existing semantic coverage contract.
            # Host, material marks, cells, input and terminal output stay shared.
            base,coverage=scene_backend.render(model,env,r.width,r.height)
            stats['last_scene_backend']=scene_backend.name
        stats['geometry_seconds']=time.perf_counter()-t
        t=time.perf_counter();patch=implementation.render(frame(model,coverage,base,r.width,r.height,coordinates=coordinates),materials)
        stats['surface_seconds']=time.perf_counter()-t
        output=dict(base);output.update(patch.cells)
    t=time.perf_counter()
    cells=tuple(Cell(*output[x,y]) for y in range(r.height) for x in range(r.width))
    stats['cell_pack_seconds']=time.perf_counter()-t
    t=time.perf_counter()
    cells=resize_cells(cells,r.width,r.height,r.body_width,r.body_height)
    stats['resize_seconds']=time.perf_counter()-t
    stats['preparation_seconds']=time.monotonic()-started
    return r,cells,stats
