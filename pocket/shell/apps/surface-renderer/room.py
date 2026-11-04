"""Tiny fixture on the existing Model/Camera/Mesh, not a game/scene engine."""
from functools import lru_cache
import math
from geometry import Camera,HeightField,Mesh,Model,Vec,merge,unit
from landscape_detail import box
from lighting import environment


@lru_cache(maxsize=1)
def fixture():
    field=HeightField(17,17,Vec(-3200,0,-1600),400,450,(0.,)*289,'demo units')
    scene=merge((field.mesh(),box(Vec(-1400,0,900),160,850,3000,'metal','wall:left'),
        box(Vec(1240,0,900),160,850,3000,'metal','wall:right'),
        box(Vec(-1400,0,3600),980,850,160,'metal','wall:back-left'),
        box(Vec(420,0,3600),980,850,160,'metal','wall:back-right'),
        box(Vec(-420,620,3600),840,230,160,'metal','wall:lintel'),
        box(Vec(-580,0,3760),160,850,1800,'metal','corridor:left'),
        box(Vec(420,0,3760),160,850,1800,'metal','corridor:right'),
        box(Vec(-850,0,2700),340,420,340,'fern','prop:green'),
        box(Vec(-65,0,1420),130,600,130,'metal','wall:occluder')))
    obj=box(Vec(-180,0,-180),360,520,360,'wood','prop:moving')
    env=environment(0)._replace(sun=unit(Vec(-.5,.8,-.4)),ambient=(.44,.42,.39),sky=(22,28,36),haze=(50,64,75))
    return field,scene,obj,env


def scene(age,x,z,yaw,width,height,pitch=0.):
    field,static,obj,env=fixture()
    angle=.15+age*.4;tx=math.sin(age*.35)*180;tz=2050
    ca,sa=math.cos(angle),math.sin(angle)
    moving=Mesh(tuple(Vec(ca*p.x+sa*p.z+tx,p.y,-sa*p.x+ca*p.z+tz) for p in obj.vertices),obj.triangles)
    camera=Camera(Vec(x,340,z),yaw=yaw,elevation=.05+pitch,span_x=1085*width/(height*2),span_y=1085,focal=1000)
    model=Model(field,merge((static,moving)),camera,env.sun,haze_strength=.015)
    def coordinates(owner,p,n):
        if owner!='prop:moving':return p,n
        xx,yy,zz=p[0]-tx,p[1],p[2]-tz
        return (ca*xx-sa*zz,yy,sa*xx+ca*zz),(ca*n[0]-sa*n[2],n[1],sa*n[0]+ca*n[2])
    return model,env,coordinates


@lru_cache(maxsize=1)
def portal_fixture():
    """Portal-inspired geometric gallery; no recursive scene or new shader."""
    from geometry import Triangle
    from landscape_detail import beam
    field=HeightField(9,17,Vec(-3200,0,-1800),800,600,(0.,)*153,'demo units')
    ground=field.mesh()
    ground=Mesh(ground.vertices,tuple(Triangle(t.a,t.b,t.c,'metal','gallery:floor') for t in ground.triangles))
    parts=[ground,
        box(Vec(-1500,0,-1300),130,1200,8500,'roof','gallery:left'),
        box(Vec(1370,0,-1300),130,1200,8500,'roof','gallery:right'),
        box(Vec(-1500,0,7100),3000,1200,100,'metal','gallery:back')]
    for j,z in enumerate((900,2300,3900,5500)):
        # Each frame is a real hollow ring: the distant room remains depth-visible.
        for i in range(20):
            a,b=i*math.tau/20,(i+1)*math.tau/20
            p=Vec(math.cos(a)*1020,570+math.sin(a)*570,z)
            q=Vec(math.cos(b)*1020,570+math.sin(b)*570,z)
            parts.append(beam(p,q,55,'flower' if (i//5+j)%2 else 'glass',f'portal:{j}:segment:{i}'))
        for x in (-1220,1220):
            parts.append(box(Vec(x-18,0,z-190),36,1000,36,'flower' if j%2 else 'glass',f'portal:{j}:rail:{x}'))
    for j in range(17):
        z=-700+j*430
        for x in (-1000,1000):
            parts.append(box(Vec(x-70,2,z),140,8,190,'flower' if j%2 else 'glass',f'floor:inlay:{j}:{x}'))
    obj=box(Vec(-180,-180,-180),360,360,360,'wood','portal:prop')
    env=environment(0)._replace(sun=unit(Vec(-.45,.85,-.3)),ambient=(.50,.44,.62),sky=(10,8,24),haze=(36,22,61))
    return field,merge(parts),obj,env


def portal_scene(age,x,z,yaw,width,height,pitch=0.):
    field,static,obj,env=portal_fixture()
    moving=[];transforms={}
    for i in range(3):
        owner=f'portal:prop:{i}';angle=age*.55+i*1.7
        ca,sa=math.cos(angle),math.sin(angle)
        tx=math.sin(age*.45+i*2.1)*620;ty=430+math.sin(age*.7+i)*110;tz=1600+i*1750
        transforms[owner]=(ca,sa,tx,ty,tz)
        material=('wood','flower','glass')[i]
        from geometry import Triangle
        moving.append(Mesh(tuple(Vec(ca*p.x+sa*p.z+tx,p.y+ty,-sa*p.x+ca*p.z+tz) for p in obj.vertices),
                           tuple(Triangle(t.a,t.b,t.c,material,owner) for t in obj.triangles)))
    camera=Camera(Vec(x,410,z),yaw=yaw,elevation=.025+pitch,span_x=1340*width/(height*2),span_y=1340,focal=1000)
    model=Model(field,merge((static,*moving)),camera,env.sun,haze_strength=.008)
    def coordinates(owner,p,n):
        if owner not in transforms:return p,n
        ca,sa,tx,ty,tz=transforms[owner];xx,yy,zz=p[0]-tx,p[1]-ty,p[2]-tz
        return (ca*xx-sa*zz,yy,sa*xx+ca*zz),(ca*n[0]-sa*n[2],n[1],sa*n[0]+ca*n[2])
    return model,env,coordinates


def walkthrough_pose(phase):
    """Closed walking path: forward through arches, turn, return and turn again."""
    u=phase%1
    def smooth(t):return t*t*(3-2*t)
    if u<.43:
        q=u/.43;return 260*math.sin(q*math.pi),-900+6500*smooth(q),.17*math.sin(q*math.tau)
    if u<.50:return 0,5600,math.pi*smooth((u-.43)/.07)
    if u<.93:
        q=(u-.50)/.43;return -260*math.sin(q*math.pi),5600-6500*smooth(q),math.pi+.17*math.sin(q*math.tau)
    return 0,-900,math.pi+math.pi*smooth((u-.93)/.07)


def portal_materials():
    """Room-owned art recipes using the unchanged shared surface renderer API."""
    from profiles import ROOM
    from surface_renderer import Material
    return dict(ROOM,roof=Material(95,'/\\:+=',.8,.18,.5,'masonry',1800,8500),
                flower=Material(65,'+x*/\\',.92,.22,.7,'grain',1600,8500),
                glass=Material(65,'+:/|=',.92,.20,.65,'masonry',1600,8500))


_float_coordinates=False

def configure_numeric(float_coordinates=False):
    """App-side measured numeric-domain experiment, not a native guard bypass."""
    global _float_coordinates
    _float_coordinates=bool(float_coordinates)

def rift_scene(age,x,z,yaw,width,height,include_views=True,pitch=0.):
    """Experience geometry only; uses the same canonical renderer for every view."""
    from geometry import Triangle
    from landscape_detail import beam
    model,env,coordinates=portal_scene(age,x,z,yaw,width,height,pitch=pitch)
    parts=[model.mesh]
    for i in range(7):
        angle=age*.43+i*math.tau/7
        a=Vec(0,1080,4500)
        b=Vec(math.sin(angle)*1270,80+100*(.5+.5*math.sin(angle*1.7)),4500+math.cos(angle)*2100)
        parts.append(beam(a,b,10,'flower' if i%2 else 'glass',f'rave:laser:{i}'))
    if include_views:
        # Planar apertures are actual depth-tested engine geometry.
        for owner,x0,x1,z0 in (('rift:mirror',-1240,-300,3300),('rift:portal',-530,530,6200)):
            vertices=(Vec(x0,90,z0),Vec(x1,90,z0),Vec(x0,1060,z0),Vec(x1,1060,z0))
            parts.append(Mesh(vertices,(Triangle(0,2,1,'glass',owner),Triangle(1,2,3,'glass',owner))))
            for a,b in ((vertices[0],vertices[1]),(vertices[1],vertices[3]),(vertices[3],vertices[2]),(vertices[2],vertices[0])):
                parts.append(beam(a,b,28,'flower' if owner.endswith('mirror') else 'glass',owner+':frame'))
    mesh=merge(parts)
    # Scene positions are explicitly floating-point engine coordinates.
    # Keep native adapter arithmetic guards intact; do not coerce in the engine.
    if _float_coordinates:mesh=Mesh(tuple(Vec(float(p.x),float(p.y),float(p.z)) for p in mesh.vertices),mesh.triangles)
    return Model(model.terrain,mesh,model.camera,env.sun,haze_strength=model.haze_strength),env,coordinates


def teleport_step(old_x,old_z,x,z,yaw):
    """One paired-space crossing, not a physics/portal engine."""
    if old_z<6200<=z and abs(x)<530:
        return x,z-7050,yaw,True
    return x,z,yaw,False


def mirror_visible_mesh(mesh,plane_z=3300):
    """Fixture clipping at the mirror plane; projection/depth stay canonical."""
    from geometry import Triangle
    vertices=[];triangles=[]
    for tri in mesh.triangles:
        polygon=[mesh.vertices[i] for i in (tri.a,tri.b,tri.c)];out=[]
        for a,b in zip(polygon,polygon[1:]+polygon[:1]):
            inside_a=a.z<=plane_z;inside_b=b.z<=plane_z
            if inside_a:out.append(a)
            if inside_a!=inside_b:
                t=(plane_z-a.z)/(b.z-a.z)
                out.append(Vec(a.x+(b.x-a.x)*t,a.y+(b.y-a.y)*t,plane_z))
        start=len(vertices);vertices.extend(out)
        for i in range(1,len(out)-1):triangles.append(Triangle(start,start+i,start+i+1,tri.material,tri.owner))
    return Mesh(tuple(vertices),tuple(triangles))
