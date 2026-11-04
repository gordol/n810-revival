"""Room-owned view surfaces and stillness effect; no shared-engine edits."""
from dataclasses import replace
import math,time
from geometry import render,raster,Vec
from surface_renderer import GlyphRenderer,SurfaceFrame
from coverage_adapter import frame
from room import rift_scene,portal_materials,mirror_visible_mesh
from loading import prepare
from effects import sample
from paint import shade_ink


def render_experience(age,x,z,yaw,width,height,idle=0,renderer=None,pitch=0.):
    renderer=renderer or GlyphRenderer(max_cells=width*height,max_glyphs=min(4000,width*height))
    materials=portal_materials();model,env,coordinates=rift_scene(age,x,z,yaw,width,height,pitch=pitch)
    amount=max(0,min(1,(idle-1.8)/4.2))
    t=time.perf_counter();base,_=render(model,width,height,environment=env,cast_shadows=False,prepare_wire=amount>0,grid_strength=0)
    coverage=raster(model,width,height,False)
    # One coverage-to-material walk serves glyph output and aperture admission.
    surface_records=tuple(frame(model,coverage,base,width,height,coordinates=coordinates).cells)
    surface_frame=SurfaceFrame(width,height,surface_records)
    patch=renderer.render(surface_frame,materials);cells=dict(base);cells.update(patch.cells)
    primary_seconds=time.perf_counter()-t;view_seconds=0;view_kind=None
    # Retain only visible sample references, then one bounded secondary camera pass.
    apertures={}
    for c in surface_records:
        if c.upper and c.lower and c.upper.owner==c.lower.owner and c.upper.owner in ('rift:mirror','rift:portal'):
            apertures.setdefault(c.upper.owner,[]).append(c)
    if apertures and amount<1:
        view_kind=max(apertures,key=lambda k:len(apertures[k]));t=time.perf_counter()
        if view_kind=='rift:mirror':
            target=(x,6600-z,math.pi-yaw);map_point=lambda p:Vec(*p)
        else:
            target=(x,z-7050,yaw);map_point=lambda p:Vec(p[0],p[1],p[2]-7050)
        other,other_env,other_coords=rift_scene(age,*target,width,height,include_views=False,pitch=pitch)
        if view_kind=='rift:mirror':other=replace(other,mesh=mirror_visible_mesh(other.mesh))
        scale=min(1,80/width,27/height);sw=max(8,round(width*scale));sh=max(6,round(height*scale))
        reflected,_=render(other,sw,sh,environment=other_env,cast_shadows=False)
        reflected_patch=renderer.render(frame(other,raster(other,sw,sh,False),reflected,sw,sh,coordinates=other_coords),materials)
        reflected=dict(reflected);reflected.update(reflected_patch.cells)
        for c in apertures[view_kind]:
            p=tuple((a+b)*.5 for a,b in zip(c.upper.position,c.lower.position));u,v,d=other.camera.project(map_point(p))
            if d>0 and 0<=u<1 and 0<=v<1:
                cells[c.x,c.y]=reflected[min(sw-1,int(u*sw)),min(sh-1,int(v*sh))]
        view_seconds=time.perf_counter()-t
    if amount:
        draw=prepare(width,height,age*5,wire=base.wireframe,wire_progress=1)
        for point,cell in tuple(cells.items()):
            xx,yy=point
            if sample(yy*width+xx,71)<amount:cells[point]=draw(xx,yy)
            else:cells[point]=(cell[0],shade_ink(cell[1],amount*.45))
    return cells,dict(primary_seconds=primary_seconds,view_seconds=view_seconds,view=view_kind,aperture_cells=sum(map(len,apertures.values())),dissolution=amount)


def scripted_experience(t):
    """Walk, stop until only intro wire remains, move again, cross the portal."""
    if t<5:
        q=t/5;return 170*math.sin(q*math.pi),-900+3400*q,-.12*math.sin(q*math.pi),0,'MOVE / the room holds'
    if t<12:return 0,2500,0,t-5,'STILL / what is left?'
    if t<18:
        q=(t-12)/6;z=2500+4400*q
        if z>=6200:z-=7050
        return 0,z,0,0,'MOVE / return, then cross the portal'
    return 0,-150+(t-18)*130,.10*math.sin((t-18)*.5),0,'ELSEWHERE / still the same room?'
