"""Small Rainier exploration producer, using canonical terrain and Lab assets.

Terrain coordinates/elevations stay in metres. This supplies geometry/camera only;
projection, near clipping, coverage, light and composition remain shared engine.
"""
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
import importlib.util,math,sys
from geometry import Camera,Mesh,Model,Vec,merge,unit,intersect
from landscape_detail import box,beam
from lighting import environment

HERE=Path(__file__).resolve().parent;LAB=HERE.parent/'landscape-lab'

@lru_cache(maxsize=1)
def assets():
    # Reuse owner files, never copy their animal generators.
    result=[]
    for name in ('marmot_art','eagle_art'):
        path=LAB/(name+'.py')
        existing=sys.modules.get(name)
        if existing is not None and Path(existing.__file__).resolve()==path.resolve():module=existing
        else:
            spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
            sys.modules[name]=module
            try:spec.loader.exec_module(module)
            except Exception:
                if existing is None:sys.modules.pop(name,None)
                else:sys.modules[name]=existing
                raise
        result.append(module)
    return tuple(result)

@lru_cache(maxsize=9)
def animal_mesh(species,pose,detail='inspection'):
    marmot,eagle=assets()
    if species=='marmot':return marmot.marmot(Vec(0.,0.,0.),pose=pose,detail=detail)
    return eagle.eagle(Vec(0.,0.,0.),pose=pose)


def translate(mesh,origin):
    return Mesh(tuple(Vec(p.x+origin.x,p.y+origin.y,p.z+origin.z) for p in mesh.vertices),mesh.triangles)

@lru_cache(maxsize=4)
def terrain_mesh(field):return field.mesh()

@lru_cache(maxsize=2048)
def ground_height(field,x,z):
    # Use the engine's triangle intersection rather than assuming the bilinear
    # height helper equals the diagonal triangulation between source vertices.
    hit=intersect(terrain_mesh(field),Vec(x,max(field.values)+100,z),Vec(0,-1,0),100000)
    return hit.point.y if hit is not None else field.height(x,z)

@lru_cache(maxsize=1)
def forest_profile():
    path=HERE.parent/'mixed-forest'/'mixed_forest.py'
    spec=importlib.util.spec_from_file_location('_walk_approved_forest',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=4)
def source_world(approved_forest=False,seed=12345,season='summer'):
    from model_scene import tahoma
    model=tahoma(8)
    if not approved_forest:return model,{}
    # Selection uses the fixed source camera, never the moving walk camera.
    result,metadata=forest_profile().build(model,seed=seed,season=season)
    if len(result.mesh.triangles)-len(model.mesh.triangles)>64000:
        raise ValueError('approved forest triangle budget exceeded')
    return result,metadata


@lru_cache(maxsize=2)
def world(approved_forest=False):
    from model_scene import tahoma
    # Existing canonical stride API; coarse actual 3DEP terrain for this walk proof.
    model,_=source_world(approved_forest);field=model.terrain;anchor=model.camera.origin
    x,z=anchor.x,anchor.z+4000
    # Ground-level source viewpoint: the original elevated camera sits behind
    # an intervening ridge when lowered. This point has an open summit sightline.
    parts=[model.mesh]
    def base(dx,dz):return Vec(x+dx,ground_height(field,x+dx,z+dz),z+dz)
    # Fictional small stone remains, seated on this same height field.
    left,right=base(-3,9),base(3,9)
    for i,p in enumerate((left,right)):
        parts.append(box(Vec(p.x-.35,p.y,p.z-.35),.7,2.7 if i==0 else 2.1,.7,'metal',f'ruin:pillar:{i}'))
    parts.append(beam(Vec(left.x,left.y+2.7,left.z),Vec(right.x-1.8,right.y+2.25,right.z),.45,'metal','ruin:broken-lintel'))
    for i in range(5):
        p=base(-4+i*.9,11+(i%2)*.8)
        parts.append(box(Vec(p.x,p.y,p.z),.5,.25+(i%3)*.15,.7,'metal',f'ruin:fallen:{i}'))
    return field,merge(parts),Vec(x,ground_height(field,x,z),z)


def near_options(distance=.1):
    fields=Camera.__dataclass_fields__
    if 'near_distance' in fields:return {'near_distance':distance}
    if 'near' in fields:return {'near':distance}
    raise RuntimeError('Ground-level Rainier needs the shared Camera.near_distance API; legacy near plane is 100 metres')


def scene(age,x,z,yaw,pitch,width,height,world_detail=True,approved_forest=False):
    field,static,anchor=world(approved_forest);cx,cz=anchor.x+x,anchor.z+z
    # Clamp only to source extent, keeping camera height authoritative.
    cx=max(field.origin.x+.1,min(field.origin.x+(field.nx-1)*field.dx-.1,cx))
    cz=max(field.origin.z+.1,min(field.origin.z+(field.nz-1)*field.dz-.1,cz))
    eye=Vec(cx,ground_height(field,cx,cz)+1.7,cz)
    camera=Camera(eye,yaw=yaw,elevation=pitch,span_x=1.25*width/(height*2),span_y=1.25,focal=1,**near_options())
    mpose=('forage','look','walk')[int(age//3)%3]
    mx=anchor.x-1.35+(.3*math.sin(age*.45) if mpose=='walk' else 0);mz=anchor.z+4.8
    morigin=Vec(mx,ground_height(field,mx,mz),mz)
    epose=('glide','bank','upstroke')[int(age//2)%3]
    ex=anchor.x+5+math.sin(age*.25)*3;ez=anchor.z+18+math.cos(age*.25)*4
    eorigin=Vec(ex,field.height(ex,ez)+5.5,ez)
    _,_,depth=camera.project(morigin)
    projected_width=width*.9/max(.1,depth)/camera.span_x if depth>0 else 0
    detail='world' if world_detail and projected_width<=12 else 'inspection'
    mesh=merge((static,translate(animal_mesh('marmot',mpose,detail),morigin),translate(animal_mesh('eagle',epose),eorigin)))
    env=environment(0)._replace(sun=unit(Vec(-.45,.75,-.45)),sunlight=1,moonlight=0,ambient=(.52,.55,.50),sky=(90,130,165),haze=(127,149,165))
    model=Model(field,mesh,camera,env.sun,haze_strength=.22)
    return model,env,dict(marmot=morigin,eagle=eorigin),dict(eye=list(eye),terrain_units=field.units,terrain_grid=[field.nx,field.nz],triangles=len(mesh.triangles),marmot_pose=mpose,marmot_detail=detail,marmot_projected_width=projected_width,eagle_pose=epose,near_distance=.1)


def overlay(model,coverage,cells,width,height,origins):
    marmot,eagle=assets();result={}
    result.update(marmot.fur_overlay(model,coverage,cells,width,height,origin=origins['marmot']))
    result.update(eagle.feather_overlay(model,coverage,cells,width,height,origin=origins['eagle']))
    return result


def materials():
    from profiles import LANDSCAPE
    from surface_renderer import Material
    return dict(LANDSCAPE,
        terrain=Material(.45,',.;:',.42,.10,.28,'stone',8,65),
        wood=Material(.18,'|/\\:',.65,.12,.35,'grain',8,65),
        metal=Material(.35,'_:/.',.65,.16,.45,'masonry',6,55))
