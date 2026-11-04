"""Small world-space geometry proof. Height fields carry explicit units."""
from collections import namedtuple
from dataclasses import dataclass
import math
from array import array
from functools import lru_cache
from build_trace import checkpoint


def checked(items,interval=256):
    """Bounded cancellation points shared by CPU and native stage adapters."""
    for index,item in enumerate(items):
        if index%interval==0:checkpoint()
        yield item

Vec=namedtuple('Vec','x y z')
Triangle=namedtuple('Triangle','a b c material owner')
Mesh=namedtuple('Mesh','vertices triangles')
Hit=namedtuple('Hit','distance point owner')
Surface=namedtuple('Surface','identity origin right up width height view_ref space')


def add(a,b):return Vec(*(x+y for x,y in zip(a,b)))
def sub(a,b):return Vec(*(x-y for x,y in zip(a,b)))
def mul(a,s):return Vec(*(x*s for x in a))
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def cross(a,b):return Vec(a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x)
def unit(a):
    size=math.sqrt(dot(a,a))
    if size<1e-12:raise ValueError('zero direction')
    return mul(a,1/size)


@dataclass(frozen=True)
class Camera:
    origin: Vec=Vec(0,1.0,-3)
    yaw: float=0.0
    elevation: float=.40
    span_x: float=3.2
    span_y: float=2.3
    focal: float=0.0
    near_distance: float=100.0

    def __post_init__(self):
        if type(self.near_distance) not in (int,float) or not math.isfinite(self.near_distance) or self.near_distance<=0:
            raise ValueError('camera near distance must be finite and positive')

    def axes(self):
        right=Vec(math.cos(self.yaw),0,-math.sin(self.yaw))
        forward=Vec(math.sin(self.yaw)*math.cos(self.elevation),-math.sin(self.elevation),math.cos(self.yaw)*math.cos(self.elevation))
        return right,unit(cross(right,forward)),forward

    def project(self,point):
        right,down,forward=self.axes();p=sub(point,self.origin)
        depth=dot(p,forward)
        scale=self.focal/depth if self.focal and abs(depth)>1e-9 else 1
        return dot(p,right)*scale/self.span_x+.5,dot(p,down)*scale/self.span_y+.5,depth

    def project_many(self,points,workspace=None):
        from geometry_compute import project
        return project(self,points,workspace)

    def depths(self,points):
        if not points:return []
        if type(self) is Camera:
            from geometry_compute import native_depths
            prepared=native_depths(self,points)
            if prepared is not None:return prepared
        _,_,forward=self.axes()
        ox,oy,oz=self.origin;fx,fy,fz=forward
        result=[]
        for index,point in enumerate(points):
            if index%256==0:checkpoint()
            x,y,z=point
            result.append(sum(((x-ox)*fx,(y-oy)*fy,(z-oz)*fz)))
        return result

    def ray(self,u,v):
        right,down,forward=self.axes()
        if self.focal:
            return self.origin,unit(add(forward,add(mul(right,(u-.5)*self.span_x/self.focal),mul(down,(v-.5)*self.span_y/self.focal))))
        origin=add(self.origin,add(mul(right,(u-.5)*self.span_x),mul(down,(v-.5)*self.span_y)))
        return origin,forward


def interpolate_camera(a,b,t):
    """Interpolate transforms and frustum values, taking the short yaw arc."""
    t=max(0,min(1,t));yaw=a.yaw+math.remainder(b.yaw-a.yaw,math.tau)*t
    return Camera(Vec(*(x+(y-x)*t for x,y in zip(a.origin,b.origin))),yaw,
                  a.elevation+(b.elevation-a.elevation)*t,
                  a.span_x+(b.span_x-a.span_x)*t,a.span_y+(b.span_y-a.span_y)*t,
                  a.focal+(b.focal-a.focal)*t,
                  a.near_distance+(b.near_distance-a.near_distance)*t)


@dataclass(frozen=True)
class HeightField:
    nx: int
    nz: int
    origin: Vec
    dx: float
    dz: float
    values: tuple
    units: str='demo units'

    def height(self,x,z):
        fx=(x-self.origin.x)/self.dx;fz=(z-self.origin.z)/self.dz
        if not 0<=fx<=self.nx-1 or not 0<=fz<=self.nz-1:raise ValueError('outside terrain')
        ix=min(self.nx-2,int(fx));iz=min(self.nz-2,int(fz));u=fx-ix;v=fz-iz
        a=self.values[iz*self.nx+ix];b=self.values[iz*self.nx+ix+1]
        c=self.values[(iz+1)*self.nx+ix];d=self.values[(iz+1)*self.nx+ix+1]
        return (a*(1-u)+b*u)*(1-v)+(c*(1-u)+d*u)*v

    def mesh(self):
        vertices=tuple(Vec(self.origin.x+x*self.dx,self.values[z*self.nx+x],self.origin.z+z*self.dz) for z in range(self.nz) for x in range(self.nx))
        triangles=[]
        for z in range(self.nz-1):
            for x in range(self.nx-1):
                a=z*self.nx+x;b=a+1;c=a+self.nx;d=c+1
                triangles.extend((Triangle(a,c,b,'terrain','terrain'),Triangle(b,c,d,'terrain','terrain')))
        return Mesh(vertices,tuple(triangles))


def intersect(mesh,origin,direction,max_distance=math.inf):
    """Reference triangle picking, linear in triangle count; not an RF solver."""
    direction=unit(direction);best=None
    for triangle in mesh.triangles:
        a,b,c=(mesh.vertices[i] for i in triangle[:3])
        e1,e2=sub(b,a),sub(c,a);p=cross(direction,e2);det=dot(e1,p)
        if abs(det)<1e-10:continue
        inverse=1/det;tvec=sub(origin,a);u=dot(tvec,p)*inverse
        if not 0<=u<=1:continue
        q=cross(tvec,e1);v=dot(direction,q)*inverse
        if v<0 or u+v>1:continue
        distance=dot(e2,q)*inverse
        if 1e-7<distance<max_distance and (best is None or distance<best.distance):
            best=Hit(distance,add(origin,mul(direction,distance)),triangle.owner)
    return best


def surface_mesh(surface):
    if surface.space!='world':raise ValueError('screen surfaces belong to the UI compositor')
    r=mul(unit(surface.right),surface.width);u=mul(unit(surface.up),surface.height)
    if abs(dot(unit(r),unit(u)))>1e-6:raise ValueError('surface axes must be orthogonal')
    vertices=(surface.origin,add(surface.origin,r),add(surface.origin,u),add(add(surface.origin,r),u))
    return Mesh(vertices,(Triangle(0,1,2,'panel',surface.identity),Triangle(1,3,2,'panel',surface.identity)))


def merge(meshes):
    vertices=[];triangles=[]
    for mesh in meshes:
        offset=len(vertices);vertices.extend(mesh.vertices)
        if offset==0:triangles.extend(mesh.triangles)
        else:triangles.extend(Triangle(t.a+offset,t.b+offset,t.c+offset,t.material,t.owner) for t in mesh.triangles)
    return Mesh(tuple(vertices),tuple(triangles))


def cone(origin,radius,height,material,owner):
    ring=tuple(add(origin,Vec(math.cos(i*math.tau/6)*radius,0,math.sin(i*math.tau/6)*radius)) for i in range(6))
    vertices=ring+(add(origin,Vec(0,height,0)),)
    return Mesh(vertices,tuple(Triangle(i,(i+1)%6,6,material,owner) for i in range(6)))


@dataclass(frozen=True)
class Model:
    terrain: HeightField
    mesh: Mesh
    camera: Camera
    light: Vec
    surfaces: tuple=()
    sample_limit: int=470400
    sample_edge: int=1024
    haze_strength: float=.88


def build(seed=0):
    from effects import sample
    nx,nz=33,25;dx=2.8/(nx-1);dz=2.5/(nz-1)
    phase=sample(0,seed,81)*math.tau
    values=[]
    for z in range(nz):
        zz=z*dz
        for x in range(nx):
            xx=-1.4+x*dx
            r=math.sqrt((xx/.82)**2+((zz-1.5)/.78)**2)
            height=.035+min(1.15,max(0,1-r)**1.2*1.4)
            height+=max(0,1-r)*(.03*math.sin(xx*20+zz*5+phase))
            height+=.018*(1+math.sin(xx*5+zz*4+phase))
            values.append(height)
    terrain=HeightField(nx,nz,Vec(-1.4,0,0),dx,dz,tuple(values))
    meshes=[terrain.mesh()]
    for i in range(12):
        x=-1.15+sample(i,seed,82)*2.3;z=.1+sample(i,seed,83)*.65
        y=terrain.height(x,z);height=.16+.13*sample(i,seed,84)
        meshes.append(cone(Vec(x,y,z),height*.25,height,'tree',f'tree:{i}'))
    # A view reference is carried on a real plane; it has no rasterized UI texture yet.
    surface=Surface('panel:example',Vec(-1,.3,.85),Vec(1,0,0),Vec(0,1,0),.45,.3,'Conversations','world')
    return Model(terrain,merge(meshes),Camera(),unit(Vec(-.6,1,-.5)),(surface,))


class Coverage:
    """Packed immutable-after-build coverage; no six-object tuple per sample."""
    __slots__=('ids','weights','size')
    empty=0xffffffff
    def __init__(self,size):
        self.size=size
        self.ids=array('I',[self.empty])*(size*3)
        self.weights=array('f',[0])*(size*2)
    def __len__(self):return self.size
    def __getitem__(self,index):
        if index<0:index+=self.size
        if not 0<=index<self.size:raise IndexError(index)
        a=self.ids[index*3]
        if a==self.empty:return None
        w1=self.weights[index*2];w2=self.weights[index*2+1]
        return a,self.ids[index*3+1],self.ids[index*3+2],w1,w2,1-w1-w2
    def __setitem__(self,index,value):
        a,b,c,w1,w2,_=value
        k=index*3;self.ids[k]=a;self.ids[k+1]=b;self.ids[k+2]=c
        self.weights[index*2]=w1;self.weights[index*2+1]=w2
    def __iter__(self):
        for i in range(self.size):yield self[i]


class Albedos:
    """Packed RGB8 material colors, with a sentinel for sky/non-terrain samples."""
    __slots__=('values',)
    def __init__(self,size):self.values=array('I',[0xffffffff])*size
    def __getitem__(self,index):
        color=self.values[index]
        return None if color==0xffffffff else ((color>>16)&255,(color>>8)&255,color&255)
    def __setitem__(self,index,value):
        r,g,b=value
        self.values[index]=(int(r)<<16)|(int(g)<<8)|int(b)


def clip_near(mesh,camera,distance=100):
    """Clip world triangles against the perspective near plane before projection."""
    if not camera.focal:return mesh
    vertices=list(mesh.vertices);triangles=[]
    depths=camera.depths(vertices)
    for index,tri in enumerate(mesh.triangles):
        if index%256==0:checkpoint()
        polygon=[]
        ids=tri[:3]
        da,db,dc=(depths[i] for i in ids)
        if da>=distance and db>=distance and dc>=distance:
            triangles.append(tri if type(tri) is Triangle else Triangle(*ids,tri.material,tri.owner));continue
        if da<distance and db<distance and dc<distance:continue
        for a,b in zip(ids,(ids[1],ids[2],ids[0])):
            da,db=depths[a],depths[b]
            if da>=distance:polygon.append(a)
            if (da>=distance)!=(db>=distance):
                t=(distance-da)/(db-da)
                vertices.append(add(vertices[a],mul(sub(vertices[b],vertices[a]),t)))
                polygon.append(len(vertices)-1)
        for i in range(1,len(polygon)-1):
            triangles.append(Triangle(polygon[0],polygon[i],polygon[i+1],tri.material,tri.owner))
    return Mesh(tuple(vertices),tuple(triangles))



def raster_size(width,height,limit=470400,edge=1024):
    """Native half-cell samples up to a bounded dense-terminal budget."""
    width,height=max(1,width),max(2,height*2)
    scale=min(1,edge/width,edge/height,math.sqrt(limit/(width*height)))
    return max(1,int(width*scale)),max(2,int(height*scale))


def cell_samples(packed,pw,ph,width,height):
    """Resample upper/lower halves at distinct pixel centers, without row overlap."""
    if pw==width and ph==height*2:
        for y in range(height):
            for x in range(width):
                yield packed[(y*2)*pw+x],packed[(y*2+1)*pw+x]
        return
    def axis(target,source):
        result=[]
        for i in range(target):
            position=max(0,min(source-1,(i+.5)*source/target-.5))
            lower=int(position);result.append((lower,min(source-1,lower+1),position-lower))
        return result
    xs,ys=axis(width,pw),axis(height*2,ph)
    def sample(x,y):
        x0,x1,tx=xs[x];y0,y1,ty=ys[y]
        a,b,c,d=(packed[index] for index in (y0*pw+x0,y0*pw+x1,y1*pw+x0,y1*pw+x1))
        result=0
        for shift in (16,8,0):
            top=((a>>shift)&255)*(1-tx)+((b>>shift)&255)*tx
            bottom=((c>>shift)&255)*(1-tx)+((d>>shift)&255)*tx
            result|=round(top*(1-ty)+bottom*ty)<<shift
        return result
    for y in range(height):
        for x in range(width):yield sample(x,y*2),sample(x,y*2+1)

@lru_cache(maxsize=2)
def raster(model,width,height,include_surfaces=False):
    """Retain geometry coverage once; lighting never rerasterizes triangles."""
    mesh=merge((model.mesh,*(surface_mesh(s) for s in model.surfaces))) if include_surfaces else model.mesh
    mesh=clip_near(mesh,model.camera,getattr(model.camera,'near_distance',100.0))
    pw,ph=raster_size(width,height,model.sample_limit,model.sample_edge)
    depths=array('f',[math.inf])*(pw*ph);samples=Coverage(pw*ph)
    workspace={}
    projected=model.camera.project_many(mesh.vertices,workspace) if type(model.camera) is Camera else model.camera.project_many(mesh.vertices)
    from geometry_compute import normal_data,coverage_data,finish_data
    prepared=normal_data(mesh,Vec,Triangle,checked,workspace)
    if prepared is None:
        sums=[[0,0,0] for _ in mesh.vertices]
        materials=['terrain']*len(mesh.vertices)
        for tri_index,triangle in enumerate(mesh.triangles):
            if tri_index%256==0:checkpoint()
            a,b,c=(mesh.vertices[i] for i in triangle[:3])
            ux,uy,uz=b.x-a.x,b.y-a.y,b.z-a.z
            vx,vy,vz=c.x-a.x,c.y-a.y,c.z-a.z
            nx,ny,nz=uy*vz-uz*vy,uz*vx-ux*vz,ux*vy-uy*vx
            if ny<0:nx,ny,nz=nx*-1,ny*-1,nz*-1
            for index in triangle[:3]:
                value=sums[index]
                value[0]=value[0]+nx;value[1]=value[1]+ny;value[2]=value[2]+nz
                materials[index]=triangle.material
        normals=tuple(unit(n) if dot(n,n)>1e-12 else Vec(0,1,0) for n in (Vec(*value) for value in sums))
    else:normals,materials=prepared
    if not coverage_data(mesh,projected,pw,ph,model.camera.focal,depths,samples,Triangle,checked,workspace):
        for tri_index,tri in enumerate(mesh.triangles):
            if tri_index%64==0:checkpoint()
            a,b,c=[(projected[i][0]*pw,projected[i][1]*ph,projected[i][2]) for i in tri[:3]]
            area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(area)<1e-8:continue
            x0=max(0,math.floor(min(p[0] for p in (a,b,c))));x1=min(pw-1,math.ceil(max(p[0] for p in (a,b,c))))
            y0=max(0,math.floor(min(p[1] for p in (a,b,c))));y1=min(ph-1,math.ceil(max(p[1] for p in (a,b,c))))
            for y in range(y0,y1+1):
                for x in range(x0,x1+1):
                    px,py=x+.5,y+.5
                    w1=((b[0]-px)*(c[1]-py)-(b[1]-py)*(c[0]-px))/area
                    w2=((c[0]-px)*(a[1]-py)-(c[1]-py)*(a[0]-px))/area
                    w3=1-w1-w2
                    if min(w1,w2,w3)<-1e-8:continue
                    if model.camera.focal:
                        depth=1/(w1/a[2]+w2/b[2]+w3/c[2])
                        w1,w2,w3=w1*depth/a[2],w2*depth/b[2],w3*depth/c[2]
                    else:depth=w1*a[2]+w2*b[2]+w3*c[2]
                    index=y*pw+x
                    if depth<depths[index]:
                        depths[index]=depth;samples[index]=(tri.a,tri.b,tri.c,w1,w2,w3)
    workspace.clear()
    prepared=finish_data(mesh,normals,materials,samples,depths,pw,ph,model.terrain,Vec,Albedos,checked,haze_strength=model.haze_strength)
    if prepared is not None:
        haze,albedos,water=prepared
        return mesh,normals,tuple(materials),samples,depths,haze,pw,ph,albedos,water
    finite=[d for d in depths if math.isfinite(d)]
    near=min(finite,default=0);span=max(finite,default=1)-near
    # Optical depth uses visible scene depth, not the arbitrary camera standoff.
    haze=array('f',(0 if not math.isfinite(d) else 1-math.exp(-model.haze_strength*max(0,d-near)/max(span,1e-9)) for d in depths))
    # Material detail is prepared once in world coordinates, shared by all lights.
    from vegetation import ground_color
    albedos=Albedos(pw*ph)
    water=[]
    for index,sample in enumerate(samples):
        if index%1024==0:checkpoint()
        if sample is None:water.append(None);continue
        a,b,c,w1,w2,w3=sample
        if materials[a]=='water':
            water.append(Vec(*(mesh.vertices[a][i]*w1+mesh.vertices[b][i]*w2+mesh.vertices[c][i]*w3 for i in range(3))))
        else:water.append(None)
        if materials[a]=='terrain' and model.terrain.units=='meters':
            point=Vec(*(mesh.vertices[a][i]*w1+mesh.vertices[b][i]*w2+mesh.vertices[c][i]*w3 for i in range(3)))
            normal=Vec(*(normals[a][i]*w1+normals[b][i]*w2+normals[c][i]*w3 for i in range(3)))
            albedos[index]=ground_color(point,normal)
    return mesh,normals,tuple(materials),samples,depths,haze,pw,ph,albedos,tuple(water)


class Frame(dict):
    __slots__=('wireframe',)


def render(model,width,height,include_surfaces=False,environment=None,moon_phase=0,cast_shadows=True,prepare_wire=False,season='summer',grid_strength=.08):
    """Cached orthographic coverage, vertex lighting, and depth-based atmosphere."""
    from lighting import mix,visibility
    from build_trace import mark
    mark('projecting',len(model.mesh.triangles))
    mesh,normals,materials,samples,depths,haze,pw,ph,albedos,water=raster(model,width,height,include_surfaces)
    mark('coverage',pw*ph)
    wire=None
    if prepare_wire:
        from loading import wires
        from build_trace import preview
        wire=wires(model,width,height,include_surfaces)
        preview(lambda:wire)
    if environment is None:
        from lighting import Environment
        environment=Environment(model.light,mul(model.light,-1),1,0,(.25,)*3,(15,17,18),(100,115,120))
    env=environment
    sun=visibility(model.terrain,env.sun) if env.sunlight and cast_shadows else ()
    moon=visibility(model.terrain,env.moon) if env.moonlight and cast_shadows else ()
    mark('lighting',len(mesh.vertices))
    from scene_acceleration import shade_pixels
    pixels=shade_pixels(model,(mesh,normals,materials,samples,depths,haze,pw,ph,albedos,water),env,sun,moon,season)
    if pixels is None:
        # Only sampled vertices contribute to this image. Clipping deliberately
        # retains vertex IDs, including vertices behind/outside the camera.
        # Keep indexed buffers, but avoid lighting all those invisible vertices.
        needed=set()
        for sample in checked(samples,1024):
            if sample is not None:needed.update(sample[:3])
        colors=[None]*len(mesh.vertices)
        lights=[None]*len(mesh.vertices)
        materials_rgb={'wood':(121,91,56),'roof':(52,65,66),'metal':(112,123,128),'glass':(210,166,89),'flower':(166,130,174),'fur':(108,87,62),'bird':(75,79,83),'fern':(45,82,47)}
        for ordinal,index in enumerate(sorted(needed)):
            if ordinal%256==0:checkpoint()
            point=mesh.vertices[index]
            snowline,transition=(3000,400) if model.terrain.units=='meters' else (.68,.15)
            snow=max(0,min(1,(point.y-snowline)/transition+.5))
            base=mix((56,81,67),(198,207,203),snow) if materials[index]=='terrain' else (28,67,47) if materials[index] in ('tree','fir') else (40,72,52) if materials[index]=='cedar' else materials_rgb.get(materials[index],(90,120,150))
            field=model.terrain
            ix=max(0,min(field.nx-1,round((point.x-field.origin.x)/field.dx)))
            iz=max(0,min(field.nz-1,round((point.z-field.origin.z)/field.dz)))
            shadow_index=iz*field.nx+ix
            sv=sun[shadow_index] if sun else 1
            mv=moon[shadow_index] if moon else 1
            direct=env.sunlight*max(0,dot(normals[index],env.sun))*sv
            lunar=env.moonlight*max(0,dot(normals[index],env.moon))*mv
            snow_light=snow if materials[index]=='terrain' else 0
            lunar*=1+.25*snow_light
            moon_tint=(.65+.17*snow_light,.8+.10*snow_light,1.0)
            light=tuple(min(1.2,env.ambient[c]+.72*direct+lunar*moon_tint[c]) for c in range(3))
            if materials[index]=='glass':light=tuple(a+b*(1-env.sunlight) for a,b in zip(light,(.18,.10,.025)))
            lights[index]=light
            colors[index]=tuple(base[c]*light[c] for c in range(3))
        from geometry_compute import pixel_data
        pixels=pixel_data((mesh,normals,materials,samples,depths,haze,pw,ph,albedos,water),colors,lights,env,season,model.camera)
        if pixels is None:
            pixels=[]
            for index,sample in enumerate(samples):
                if index%1024==0:checkpoint()
                if sample is None:
                    # Quiet vertical sky gradient, no screen-wide motion.
                    pixels.append(tuple(c*(.72+.28*(index//pw)/max(1,ph-1)) for c in env.sky));continue
                a,b,c,w1,w2,w3=sample
                color=tuple(colors[a][i]*w1+colors[b][i]*w2+colors[c][i]*w3 for i in range(3))
                albedo=albedos[index]
                if albedo is not None:
                    if season=='winter':albedo=mix(albedo,(205,214,213),.38)
                    elif season=='autumn':albedo=(albedo[0]*1.10,albedo[1]*.95,albedo[2]*.88)
                    elif season=='spring':albedo=(albedo[0]*.94,albedo[1]*1.08,albedo[2]*.98)
                    color=tuple(albedo[i]*(lights[a][i]*w1+lights[b][i]*w2+lights[c][i]*w3) for i in range(3))
                if water[index] is not None:
                    point=water[index]
                    view=unit(sub(model.camera.origin,point))
                    light=env.moon if env.moonlight else env.sun
                    half=unit(add(view,light))
                    glint=max(0,half.y)**48*(env.moonlight*180+env.sunlight*90)
                    ripple=.90+.1*math.sin(point.z*.13+point.x*.09)
                    color=tuple((env.sky[i]*.6+(7,16,20)[i]+glint)*ripple for i in range(3))
                exposure=1+.65*(1-env.sunlight)
                pixels.append(mix(tuple(v*exposure for v in color),env.haze,haze[index]))
    from night_scene import sky_details
    star_points=[]
    sky_details(pixels,samples,model,pw,ph,env,moon_phase,star_points)
    # Keep the terminal's full RGB gradients; RGB565 introduced visible bands
    # across broad slopes when small cells made the color steps easy to see.
    packer=getattr(pixels,'packed_rgb',None)
    packed=packer() if packer is not None else [(max(0,min(255,int(r)))<<16)|(max(0,min(255,int(g)))<<8)|max(0,min(255,int(b))) for r,g,b in pixels]
    cells=Frame();cells.wireframe={}
    for index,(upper,lower) in enumerate(cell_samples(packed,pw,ph,width,height)):
        cells[index%width,index//width]=('▄',(1<<48)|(lower<<24)|upper)
    if prepare_wire:
        from loading import surface_grid_ink
        cells.wireframe=wire
        # Faint lasting skyline accents leave the moonlit face and snow untouched.
        for point in wire.contours:
            if grid_strength<=0:continue
            char,color=cells[point]
            cells[point]=(char,surface_grid_ink(color,point,grid_strength*.45))
        # Low-contrast traces emphasize actual terrain folds and ridge curvature.
        for point in wire.accents:
            if grid_strength<=0 or point in wire.contours:continue
            char,color=cells[point]
            fore=tuple((color>>s)&255 for s in (40,32,24))
            if sum(fore)>390:continue  # Preserve bright snow and direct light.
            # Keep the actual surface texture; the retained mesh is an ink accent,
            # not replacement slash glyphs that read as freestanding structures.
            cells[point]=(char,surface_grid_ink(color,point,grid_strength*.65))
    from paint import ink
    for sx,sy,color,sky in star_points:
        if pixels[sy*pw+sx]!=sky:continue  # Moon covers this direction.
        x=min(width-1,sx*width//pw);y=min(height-1,sy*height//ph)
        xx=min(pw-1,x*pw//width);yy=min(ph-2,y*ph//height)
        if samples[yy*pw+xx] is not None or samples[(yy+1)*pw+xx] is not None:continue
        upper,lower=pixels[yy*pw+xx],pixels[(yy+1)*pw+xx]
        background=tuple((a+b)/2 for a,b in zip(upper,lower))
        cells[x,y]=('·',ink(*color,background=background))
    mark('cells',len(cells))
    return cells,depths
