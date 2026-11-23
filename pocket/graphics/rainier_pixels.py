"""Perspective terrain for the graphical Rainier walk. World coordinates are metres."""
from array import array
from concurrent.futures import ThreadPoolExecutor
import ctypes as C
import math
import random

from geometry import Vec, cross, sub, unit
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


def build_world():
    from model_scene import tahoma
    from outdoors import world, animal_mesh
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

    def face(a,b,c,color):
        n=unit(cross(sub(b,a),sub(c,a)))
        light=.74+.26*(n.y*.78-n.x*.52-n.z*.35)
        rgb=tuple(v*light for v in color)
        for p in (a,b,c):triangles.extend(vertex(p,rgb))

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
            if field.values[k]>2500:
                # Snow collects above the treeline and on gentler faces.
                point=mesh.vertices[k]
                cover=max(0.,min(1.,(point.y-2500)/650+(n.y-.88)*7+
                                    (noise(point.x,point.z,610)-.5)*1.2))
                rgb=tuple(a+(b-a)*cover for a,b in zip((103,99,98),(232,235,237)))
            colors.append(vertex(mesh.vertices[k],tuple(c*light for c in rgb),1.))
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
    for species,pose,dx,dz,up in [('marmot','look',-1.35,4.8,0),('eagle','glide',5,18,5.5)]:
        x,z=origin.x+dx,origin.z+dz
        place(animal_mesh(species,pose,'world'),Vec(x,surface(field,x,z)+up,z),
              lambda m,o:(107,89,68) if m!='snow' else (214,211,190))

    rng=random.Random(3918)
    def pine(x,z,h):
        y=surface(field,x,z)-.14
        def ring(height,radius,angle,count):
            return [Vec(x+math.cos(angle+i*math.tau/count)*radius,y+height,
                        z+math.sin(angle+i*math.tau/count)*radius) for i in range(count)]
        bottom=ring(0,h*.023,0,6);top=ring(h*.88,h*.009,0,6)
        for i in range(6):
            j=(i+1)%6
            face(bottom[i],top[i],bottom[j],(86,69,50))
            face(bottom[j],top[i],top[j],(86,69,50))
        shade=rng.uniform(.82,1.13)
        for layer in range(7):
            t=layer/7;angle=rng.random()*math.tau
            apex=Vec(x,y+h*(.50+.50*t),z)
            crown=ring(h*(.16+.76*t),h*(.23-.18*t),angle,14)
            for i,p in enumerate(crown):
                spread=rng.uniform(.60,.80) if i%2 else rng.uniform(1,1.18)
                crown[i]=Vec(x+(p.x-x)*spread,p.y+h*(.034 if i%2 else -.025),z+(p.z-z)*spread)
            for i,p in enumerate(crown):
                face(apex,p,crown[(i+1)%14],tuple(v*shade*(.78+.23*t) for v in (43,87,61)))
    for i in range(290):
        distance=rng.uniform(12,130) if i<45 else rng.uniform(140,1600)
        angle=rng.random()*math.tau
        dx,dz=distance*math.sin(angle),distance*math.cos(angle)
        if dz>0 and abs(dx+dz*EAST/SOUTH)<max(6.,.19*dz):continue
        pine(origin.x+dx,origin.z+dz,rng.uniform(6,18))
    for dx,dz,h in [(-12,23,10),(2.8,28,9),(-15,37,12),(7.5,42,13)]:
        pine(origin.x+dx,origin.z+dz,h)

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
    return field,origin,triangles


class RainierView:
    name='Rainier walk'
    def __init__(self,host):
        self.host=host
        self.closed=False
        self.pixel_dirty=True
        self.pixel_jobs=self.pixel_frames=0
        self.pool=self.job=self.world=self.camera=None
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
        if self.camera!=camera:self.camera=camera;self.pixel_dirty=True

    def draw_rainier(self,ctx):
        self.pixel_dirty=False
        if self.world is None or self.camera is None:return ()
        field,origin,data=self.world
        x,z,yaw,pitch=self.camera
        eye=surface(field,x+origin.x,z+origin.z)-origin.y+1.7
        wx,wy,w,h=self.host.bounds(self.host.window(self.name))
        ox,oy=self.host.origin
        rect=((wx+ox+1)*8,(wy+oy+1)*16,(w-2)*8,(h-3)*16)
        if min(rect[2:])<1:return ()
        draw=ctx.lib.pocket_scene_rainier
        draw.argtypes=[C.c_void_p]+[C.c_int]*4+[C.c_void_p,C.c_uint]+[C.c_float]*5
        ctx.check(draw(ctx.handle,*rect,data.buffer_info()[0] if self.upload else None,len(data)//7,
                       x,eye,z,yaw,pitch))
        self.context=ctx
        self.upload=False
        self.pixel_jobs+=1;self.pixel_frames+=1
        return rect
