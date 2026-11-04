"""Bounded, world-space illustrative scenery; DEM remains the terrain authority."""
from collections import namedtuple
from functools import lru_cache
import math
from geometry import Vec,Mesh,Triangle,merge,cone,add,mul,sub,unit,cross
from vegetation import forest,noise

Nature=namedtuple('Nature','season foliage animals flowers lookout seed grid scenery',defaults=('summer',True,True,True,False,0,.08,None))
SEASONS=('auto','spring','summer','autumn','winter')


def resolve(nature,age):
    if nature is None:return None
    season=('spring','summer','autumn','winter')[int(max(0,age)//225)%4] if nature.season=='auto' else nature.season
    # Bounded appearance windows, with no per-animal worker or mutable simulation.
    return nature._replace(season=season,animals=nature.animals and int(max(0,age)//20)%6<4)


def box(origin,width,height,depth,material,owner):
    x,y,z=origin
    vertices=tuple(Vec(x+dx*width,y+dy*height,z+dz*depth) for dx,dy,dz in ((0,0,0),(1,0,0),(0,1,0),(1,1,0),(0,0,1),(1,0,1),(0,1,1),(1,1,1)))
    faces=((0,2,1),(1,2,3),(4,5,6),(5,7,6),(0,4,2),(2,4,6),(1,3,5),(3,7,5),(2,6,3),(3,6,7),(0,1,4),(1,5,4))
    return Mesh(vertices,tuple(Triangle(*f,material,owner) for f in faces))


def beam(a,b,width,material,owner):
    direction=unit(sub(b,a));right=cross(direction,Vec(0,1,0))
    if sum(v*v for v in right)<.001:right=Vec(1,0,0)
    right=mul(unit(right),width/2);front=mul(unit(cross(direction,right)),width/2)
    vertices=tuple(add(p,add(mul(right,r),mul(front,f))) for p in (a,b) for r,f in ((-1,-1),(1,-1),(-1,1),(1,1)))
    faces=((0,1,2),(1,3,2),(4,6,5),(5,6,7),(0,4,1),(1,4,5),(2,3,6),(3,7,6),(0,2,4),(2,6,4),(1,5,3),(3,5,7))
    return Mesh(vertices,tuple(Triangle(*f,material,owner) for f in faces))


@lru_cache(maxsize=2)
def lookout(field,eye):
    """Fictional timber fire lookout, four rooted legs, bracing, cabin and roof."""
    x,z=eye.x+180,eye.z+1500;ground=field.height(x,z);deck=ground+22
    owner='landmark:fire-lookout';meshes=[]
    corners=((-7,-6),(7,-6),(-7,6),(7,6))
    for dx,dz in corners:
        bottom=Vec(x+dx,field.height(x+dx,z+dz),z+dz);top=Vec(x+dx,deck,z+dz)
        meshes.append(beam(bottom,top,1,'wood',owner))
    for a,b in ((0,1),(1,3),(3,2),(2,0)):
        ax,az=corners[a];bx,bz=corners[b]
        meshes.append(beam(Vec(x+ax,ground+3,z+az),Vec(x+bx,deck,z+bz),.55,'wood',owner))
        meshes.append(beam(Vec(x+bx,ground+3,z+bz),Vec(x+ax,deck,z+az),.55,'wood',owner))
    meshes.append(box(Vec(x-9,deck, z-8),18,1,16,'wood',owner))
    meshes.append(box(Vec(x-6,deck+1,z-5),12,5,10,'wood',owner))
    meshes.append(box(Vec(x-5.5,deck+3,z-5.2),11,2,.3,'glass',owner))
    roof=(Vec(x-8,deck+6,z-7),Vec(x+8,deck+6,z-7),Vec(x-8,deck+6,z+7),Vec(x+8,deck+6,z+7),Vec(x,deck+10,z))
    meshes.append(Mesh(roof,tuple(Triangle(a,b,4,'roof',owner) for a,b in ((0,1),(1,3),(3,2),(2,0)))))
    meshes.append(beam(Vec(x,deck+10,z),Vec(x,deck+16,z),.25,'metal',owner))
    return merge(meshes)


@lru_cache(maxsize=3)
def grove(field,eye,seed):
    meshes=[]
    shift=((seed*2654435761)&0xffffffff)/4294967296
    for i in range(360):
        u=(i*.61803398875+shift*.438)%1;v=(i*.75487766625+shift*.873)%1
        depth=1250+(v**1.25)*6200
        # Match the usual landscape frustum: spend instances in the visible valley.
        x=eye.x+(u-.5)*depth*.56;z=eye.z+depth
        y=field.height(x,z)
        if (x-eye.x-180)**2+(z-eye.z-1500)**2<70**2:continue
        if y>2150 or noise(x,z,900)<(.14 if y<1700 else .28+(y-1700)/750):continue
        h=32+noise(x,z,55)*34;material='cedar' if i%4==0 else 'fir';owner=f'grove:{i}'
        for offset,scale in ((.12,.85),(.40,.65),(.65,.40)):
            meshes.append(cone(Vec(x,y+h*offset,z),h*(.35 if material=='fir' else .45)*scale,h*scale,material,owner))
        if i%4==0:
            meshes.append(box(Vec(x-1,y,z-1),2,h*.4,2,'wood',owner))
    for i in range(36):
        depth=1250+((i*.75487766625)%1)*2200
        x=eye.x+(((i*.61803398875)%1)-.5)*depth*.52;z=eye.z+depth;y=field.height(x,z)
        owner=f'fern:{i}'
        for angle in (0,math.pi/3,math.pi*2/3):
            dx,dz=math.cos(angle)*5,math.sin(angle)*5
            meshes.append(Mesh((Vec(x,y,z),Vec(x-dx,y+1,z-dz),Vec(x,y+4,z),Vec(x+dx,y+1,z+dz)),(Triangle(0,1,2,'fern',owner),Triangle(0,2,3,'fern',owner))))
    return merge(meshes)


@lru_cache(maxsize=2)
def ground_mesh(field):
    return field.mesh()


def details(field,eye,nature):
    return _details(field,eye,geometry_nature(nature))


def geometry_nature(nature,scenery=False):
    """Normalize appearance-only values without losing geometry switches.

    Spring/summer share flowers; autumn/winter share their absence. Grid and
    seasonal ground color belong to shading, not the retained mesh key.
    """
    if nature is None:return None
    flowers=nature.flowers and nature.season in ('spring','summer')
    return nature._replace(season='summer',flowers=flowers,grid=0,
                           scenery=nature.scenery if scenery else None)


@lru_cache(maxsize=4)
def _details(field,eye,nature):
    parts=[ground_mesh(field)]
    if nature.foliage:parts.extend((forest(field),grove(field,eye,nature.seed)))
    if nature.lookout:parts.append(lookout(field,eye))
    if nature.flowers and nature.season in ('spring','summer'):
        for i in range(26):
            x=eye.x-2000+((i*.61803398875)%1)*4200;z=eye.z+900+((i*.75487766625)%1)*2400
            y=field.height(x,z)
            if y<1750:parts.append(cone(Vec(x,y+1,z),1.8,2,'flower',f'flowers:{i}'))
    if nature.animals:
        # Tiny illustrative forms, not wildlife simulation or a GIS animal layer.
        for i in range(3):
            x,z=eye.x-600+i*110,eye.z+1700+i*80;y=field.height(x,z)
            owner=f'animal:marmot:{i}'
            parts.append(box(Vec(x,y+1,z),1.4,1.1,2,'fur',owner))
            parts.append(cone(Vec(x+.7,y+1.5,z),.5,.8,'fur',owner))
        x,y,z=eye.x+250,eye.y+250,eye.z+5000
        parts.append(Mesh((Vec(x-3,y,z),Vec(x,y+.8,z),Vec(x+3,y,z),Vec(x,y,z-1)),(Triangle(0,1,3,'bird','animal:eagle'),Triangle(1,2,3,'bird','animal:eagle'))))
    return merge(parts)


details.cache_clear=_details.cache_clear
details.cache_info=_details.cache_info
