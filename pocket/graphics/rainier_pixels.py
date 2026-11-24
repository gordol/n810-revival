"""Perspective terrain for the graphical Rainier walk. World coordinates are metres."""
from array import array
from concurrent.futures import ThreadPoolExecutor
import ctypes as C
import math
import random

from geometry import Vec, cross, sub, unit
from rainier_habitat import draw_watershed, forest_sites, shelf_height
from vegetation import ground_color, noise

# South-east of the DEM summit, looking back up the south flank.
EAST, SOUTH = 1800., 7350.


def surface(field,x,z):
    """Height on the two actual rendered triangles in this DEM cell."""
    fx=max(0.,min(field.nx-1.,(x-field.origin.x)/field.dx))
    fz=max(0.,min(field.nz-1.,(z-field.origin.z)/field.dz))
    i,j=min(int(fx),field.nx-2),min(int(fz),field.nz-2)
    u,v=fx-i,fz-j
    k=j*field.nx+i
    a,b,c,d=(field.values[k+n] for n in (0,1,field.nx,field.nx+1))
    return a+(b-a)*u+(c-a)*v if u+v<=1 else d+(c-d)*(1-u)+(b-d)*(1-v)



# Illustrative encounters around the starting meadow (east, north, model scale).
ENCOUNTERS=(('marmot',-1.35,4.8,.78),('eagle',1.,17.,1.),
            ('chipmunk',1.3,5.6,.30),('squirrel',-6.,9.,.45),
            ('pika',-9.,17.,.38),('goat',-3.,25.,1.45),('fox',1.,10.,.86))


class AnimalDraw(C.Structure):
    _fields_=[('first',C.c_uint),('second',C.c_uint),('index',C.c_uint),
              ('count',C.c_uint),('stride',C.c_uint),('blend',C.c_float),('x',C.c_float),
              ('y',C.c_float),('z',C.c_float),('heading',C.c_float)]


def append_animals(vertices):
    """Store each (vertex, material) once per pose, sharing indices across poses."""
    from wildlife_models import FOX_ASSETS, FOX_FRAMES, pose
    indices=array('I')
    spans=[]
    for species,_,_,scale in ENCOUNTERS:
        frames=FOX_FRAMES if species in FOX_ASSETS else 3
        first=len(vertices)//7
        offset=len(indices)
        _,faces=pose(species,0,False)
        palette={}
        for i in range(0,len(faces),4):
            a,b,c,color=faces[i:i+4]
            for j in (a,b,c):
                key=(j,color)
                indices.append(palette.setdefault(key,len(palette)))
        for frame in range(frames):
            points,_=pose(species,frame,False)
            for j,color in palette:
                x,y,z,light=points[j*4:j*4+4]
                vertices.extend((x*scale,y*scale,z*scale,((color>>16)&255)*light/255,
                                 ((color>>8)&255)*light/255,(color&255)*light/255,0.))
        spans.append((first,len(palette),frames,offset,len(indices)-offset))
    return indices,spans


def encounters(field,origin,spans,age):
    commands=(AnimalDraw*len(spans))()
    for i,((species,x,z,_),(first,stride,frames,index,count)) in enumerate(zip(ENCOUNTERS,spans)):
        heading=0.
        altitude=0.
        seconds=2.5
        if species=='fox' or species=='eagle':
            flying=species=='eagle'
            radius=4. if flying else 1.6
            angle=age*(.43 if flying else .48)
            x+=radius*math.sin(angle)
            z+=radius*(1-math.cos(angle))
            heading=-math.degrees(angle)
            altitude=4.8+.35*math.sin(angle) if flying else 0.
            seconds=1.8 if flying else (17/24)/frames
        phase=(age/seconds)%frames
        frame=int(phase);blend=phase-frame
        if species!='fox':blend=blend*blend*(3-2*blend)
        y=surface(field,origin.x+x,origin.z+z)-origin.y+altitude
        commands[i]=AnimalDraw(first+frame*stride,first+((frame+1)%frames)*stride,
                               index,count,stride,blend,x,y,z,heading)
    return commands


def build_world():
    from model_scene import tahoma
    from outdoors import world
    model=tahoma(1)
    field=model.terrain
    _,props,anchor=world()
    peak=field.values.index(max(field.values))
    ex=field.origin.x+(peak%field.nx)*field.dx+EAST
    ez=field.origin.z+(peak//field.nx)*field.dz-SOUTH
    origin=Vec(ex,surface(field,ex,ez),ez)
    triangles=array('f')

    def vertex(p,color,ground=0.):
        return (p.x-origin.x,p.y-origin.y,p.z-origin.z,*(max(0,min(255,c))/255 for c in color),ground)

    def face(a,b,c,color,material=0.):
        n=unit(cross(sub(b,a),sub(c,a)))
        light=.74+.26*(n.y*.78-n.x*.52-n.z*.35)
        rgb=tuple(v*light for v in color)
        for p in (a,b,c):triangles.extend(vertex(p,rgb,material))

    mesh=model.mesh
    colors=[]
    for iz in range(field.nz):
        for ix in range(field.nx):
            k=iz*field.nx+ix
            ax,bx=max(0,ix-1),min(field.nx-1,ix+1)
            az,bz=max(0,iz-1),min(field.nz-1,iz+1)
            sx=(field.values[iz*field.nx+bx]-field.values[iz*field.nx+ax])/((bx-ax)*field.dx)
            sz=(field.values[bz*field.nx+ix]-field.values[az*field.nx+ix])/((bz-az)*field.dz)
            n=unit(Vec(-sx,1,-sz))
            rgb=ground_color(mesh.vertices[k],n)
            light=.55+.45*max(0,n.y*.75-n.x*.51-n.z*.42)
            material=1.
            if field.values[k]>2500:
                # Snow collects above the treeline and on gentler faces.
                point=mesh.vertices[k]
                cover=max(0.,min(1.,(point.y-2500)/650+(n.y-.88)*7+
                                    (noise(point.x,point.z,610)-.5)*1.2))
                rgb=tuple(a+(b-a)*cover for a,b in zip((103,99,98),(232,235,237)))
                # A tapering illustrative ice tongue on the summit's south flank.
                south=origin.z+SOUTH-point.z
                along=south/4200
                if 0<along<1:
                    center=origin.x-EAST+south*.19+240*math.sin(along*6)
                    width=700*(1-along)**.55
                    if abs(point.x-center)<width:
                        material=.72
                        rgb=(164,196,206)
            colors.append(vertex(mesh.vertices[k],tuple(c*light for c in rgb),material))
    for a,b,c,material,_ in mesh.triangles:
        if material=='terrain':
            for i in (a,b,c):triangles.extend(colors[i])
        else:face(mesh.vertices[a],mesh.vertices[b],mesh.vertices[c],(46,80,62))

    # Keep the walking demo's stone remains and animals at their local offsets.
    def place(mesh,shift,color):
        for a,b,c,material,owner in mesh.triangles:
            rgb=color(material,owner)
            if rgb is None:continue
            points=[Vec(p.x+shift.x,p.y+shift.y,p.z+shift.z) for p in
                    (mesh.vertices[a],mesh.vertices[b],mesh.vertices[c])]
            if len(set(points))==3 and any(cross(sub(points[1],points[0]),sub(points[2],points[0]))):
                face(*points,rgb)
    place(props,Vec(origin.x-anchor.x+12,surface(field,origin.x+12,origin.z+16)-anchor.y,origin.z-anchor.z+7),lambda m,o:(115,112,99) if o.startswith('ruin:') else None)
    rng=random.Random(3918)
    def pine(x,z,h,near):
        y=surface(field,x,z)-.14
        def ring(height,radius,angle,count):
            return [Vec(x+math.cos(angle+i*math.tau/count)*radius,y+height,
                        z+math.sin(angle+i*math.tau/count)*radius) for i in range(count)]
        sides=5 if near else 3
        bottom=ring(0,h*.023,0,sides);top=ring(h*.88,h*.009,0,sides)
        for i in range(sides):
            j=(i+1)%sides
            face(bottom[i],top[i],bottom[j],(86,69,50))
            face(bottom[j],top[i],top[j],(86,69,50))
        shade=rng.uniform(.82,1.13)
        layers=rng.choice((5,7)) if near else 3
        needles=rng.choice(((37,75,58),(52,91,66),(64,98,76),(48,82,76)))
        breadth=rng.uniform(.8,1.24)
        tips=12 if near else 5
        for layer in range(layers):
            t=layer/layers;angle=rng.random()*math.tau
            apex=Vec(x,y+h*(.50+.50*t),z)
            crown=ring(h*(.16+.76*t),breadth*h*(.23-.18*t),angle,tips)
            for i,p in enumerate(crown):
                spread=rng.uniform(.60,.80) if i%2 else rng.uniform(1,1.18)
                crown[i]=Vec(x+(p.x-x)*spread,p.y+h*(.034 if i%2 else -.025),z+(p.z-z)*spread)
            for i,p in enumerate(crown):
                face(apex,p,crown[(i+1)%tips],tuple(v*shade*(.78+.23*t) for v in needles))
    for dx,dz,h,near in forest_sites(rng):
        pine(origin.x+dx,origin.z+dz,h,near)
    draw_watershed(origin,lambda x,z:surface(field,origin.x+x,origin.z+z),face)

    # Low plants and stones give the walker close-range parallax.
    for i in range(1100):
        angle=rng.random()*math.tau;radius=48*math.sqrt(rng.random())
        x=origin.x+radius*math.cos(angle);z=origin.z+radius*math.sin(angle)
        y=surface(field,x,z)
        height=rng.uniform(.13,.48)
        if i%9==0:
            foot=[Vec(x+height*math.cos(t),y-.025,z+.7*height*math.sin(t)) for t in range(6)]
            for j in range(6):face(foot[j],Vec(x-.08*height,y+height*.50,z),foot[(j+1)%6],(115,112,95))
        else:
            for j in range(4):
                t=angle+j*1.57;dx,dz=math.cos(t)*.07,math.sin(t)*.07
                face(Vec(x-dz,y,z+dx),Vec(x+dx*2,y+height*rng.uniform(.65,1),z+dz*2),
                     Vec(x+dz,y,z-dx),(90+i%21,106+i%18,62))
    terrain_count=len(triangles)//7
    indices,spans=append_animals(triangles)
    return field,origin,triangles,terrain_count,indices,spans


class RainierView:
    name='Rainier walk'
    def __init__(self,host):
        self.host=host
        self.closed=False
        self.pixel_dirty=True
        self.pixel_jobs=self.pixel_frames=0
        self.pool=self.job=self.world=self.camera=None
        self.age=0.
        self.upload=True
        self.context=None
        self.error=''

    def lines(self):
        if self.error:return ('Rainier terrain could not open.',self.error)
        return ('Preparing the 3D terrain...',) if self.world is None else ('',)*max(0,self.host.window(self.name).h-3)+('Drag to walk and steer. Lift to stop.',)

    def release(self):
        if self.context and self.context.handle:
            release=self.context.lib.pocket_scene_rainier_release
            release.argtypes=[C.c_void_p];release.restype=None
            release(self.context.handle)
        self.context=None
        self.age=0.
        self.upload=True
        self.camera=None
        self.error=''
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
        self.world=self.job=self.pool=None

    def close(self):
        self.release()
        self.closed=True

    def poll(self,owner):
        if self.error:return
        if self.world is None:
            if self.job is None:
                self.pool=ThreadPoolExecutor(max_workers=1)
                self.job=self.pool.submit(build_world)
            if not self.job.done():return
            try:self.world=self.job.result()
            except Exception as error:self.error=str(error);return
            finally:self.pool.shutdown(wait=False);self.pool=self.job=None
        camera=(owner.x,owner.z,owner.yaw,owner.pitch)
        age=owner.clock()-owner.started-owner.paused_total
        if self.camera!=camera or age-self.age>=1/20:
            self.camera=camera;self.age=age;self.pixel_dirty=True

    def draw_rainier(self,ctx):
        self.pixel_dirty=False
        if self.world is None or self.camera is None:return ()
        field,origin,data,terrain_count,indices,spans=self.world
        x,z,yaw,pitch=self.camera
        eye=surface(field,x+origin.x,z+origin.z)-origin.y+shelf_height(x,z)+1.7
        wx,wy,w,h=self.host.bounds(self.host.window(self.name))
        ox,oy=self.host.origin
        rect=((wx+ox+1)*8,(wy+oy+1)*16,(w-2)*8,(h-3)*16)
        if min(rect[2:])<1:return ()
        draw=ctx.lib.pocket_scene_rainier
        commands=encounters(field,origin,spans,self.age)
        draw.argtypes=[C.c_void_p]+[C.c_int]*4+[C.c_void_p,C.c_uint,C.c_uint,C.c_void_p,
                       C.c_uint,C.POINTER(AnimalDraw),C.c_uint]+[C.c_float]*6
        ctx.check(draw(ctx.handle,*rect,data.buffer_info()[0] if self.upload else None,len(data)//7,terrain_count,
                       indices.buffer_info()[0] if self.upload else None,len(indices),commands,len(commands),
                       x,eye,z,yaw,pitch,self.age))
        self.context=ctx
        self.upload=False
        self.pixel_jobs+=1;self.pixel_frames+=1
        return rect
