"""Perspective terrain for the graphical Rainier walk. World coordinates are metres."""
from array import array
from concurrent.futures import ThreadPoolExecutor
import ctypes as C
import math
import random
import struct
import zlib

from geometry import Vec, cross, sub, unit
from river_detail import RiverQuality, shade_tree
from forest_floor import blade, fern, snag, spruce_sprays
from rainier_habitat import forest_sites
from river_party import PartyMenu
from river_explore import DIPPER_ROCK, OTTER_POOL, bank_sign, ground_target, read_photo, save_photo, sighting, walk_to
from pnw_species import REGIONAL, group
from river_walk import BUSHES, FOX, BerryTrail, blueberry_patch, river_gain, river_mesh, site, wet
from vegetation import ground_color, noise

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
ENCOUNTERS=(('marmot',-95.,153.,.78),('eagle',1.,17.,1.),
            ('chipmunk',1.3,5.6,.30),('squirrel',-6.,9.,.45),
            ('pika',-82.,126.,.38),('goat',-117.,187.,1.45),('fox',*FOX,.86),('bear',40.,28.,1.4),('trout',15.,8.,.65))


def regional_encounters():
    _,segments=site()
    # Distribute encounters back along the mapped watercourse and its banks.
    reach=[seg for seg in segments if all(abs(v)<550 for v in seg[:2])]
    sites=[]
    for i,(key,spec) in enumerate(REGIONAL.items()):
        if spec.form=='salmon':continue  # Slippery Falls lies below the playable reach.
        a,b,u,v,length=reach[(i*7)%len(reach)]
        along=length*((i%5+1)/7)
        kind=group(spec.form)
        across=0 if kind=='Fish' else (12+i%23)*(1 if i%2 else -1)
        x=a+along*u+across*v;z=b+along*v-across*u
        if key=='american_dipper':x,z=DIPPER_ROCK
        if key=='north_american_river_otter':x,z=OTTER_POOL
        if key=='american_crow':x,z=-3.,12.
        if key=='barred_owl':x,z=-4.,24.
        if key=='western_tiger_swallowtail':x,z=1.2,9.
        sites.append((key,x,z,spec.length))
    return tuple(sites)


ENCOUNTERS+=regional_encounters()
PERCHES={'owl','tufted owl','crested','climber','woodpecker','kingfisher','tit','wren','finch','songbird'}



class AnimalDraw(C.Structure):
    _fields_=[('first',C.c_uint),('second',C.c_uint),('index',C.c_uint),
              ('count',C.c_uint),('stride',C.c_uint),('blend',C.c_float),('x',C.c_float),
              ('y',C.c_float),('z',C.c_float),('heading',C.c_float),('shadow',C.c_float),('slope_x',C.c_float),('slope_z',C.c_float)]


def append_animals(vertices,high=False):
    """Store each (vertex, material) once per pose, sharing indices across poses."""
    from wildlife_models import FOX_ASSETS, FOX_FRAMES, pose
    indices=array('I')
    spans=[]
    for species,x,z,scale in ENCOUNTERS:
        low_mesh=species in REGIONAL and not (high and math.hypot(x,z)<30)
        frames=FOX_FRAMES if species in FOX_ASSETS else 3
        first=len(vertices)//7
        offset=len(indices)
        _,faces=pose(species,0,False,low_mesh)
        palette={}
        for i in range(0,len(faces),4):
            a,b,c,color=faces[i:i+4]
            for j in (a,b,c):
                key=(j,color)
                indices.append(palette.setdefault(key,len(palette)))
        for frame in range(frames):
            points,_=pose(species,frame,False,low_mesh)
            for j,color in palette:
                x,y,z,light=points[j*4:j*4+4]
                vertices.extend((x*scale,y*scale,z*scale,((color>>16)&255)*light/255,
                                 ((color>>8)&255)*light/255,(color&255)*light/255,0.))
        spans.append((first,len(palette),frames,offset,len(indices)-offset))
    return indices,spans


def encounters(field,origin,spans,age,fed=False,observer=(0.,0.),subjects=None):
    draws=[]
    for i,((species,x,z,_),(first,stride,frames,index,count)) in enumerate(zip(ENCOUNTERS,spans)):
        distance=math.hypot(x-observer[0],z-observer[1])
        if distance>230:continue
        heading=0.
        altitude=0.
        seconds=2.5
        if species=='fox' or species=='eagle':
            flying=species=='eagle'
            radius=4. if flying else .65
            angle=age*(.43 if flying else .48)
            x+=radius*math.sin(angle)
            z+=radius*(1-math.cos(angle))
            heading=-math.degrees(angle)
            altitude=4.8+.35*math.sin(angle) if flying else 0.
            seconds=1.8 if flying else (17/24)/frames
        if species=='fox' and fed:
            x,z=FOX
            heading=30.
            altitude=.15*abs(math.sin(age*4))
        if species=='trout':
            z+=1.6*math.sin(age*.8)
            x+=.3*math.cos(age*.8)
            heading=-90 if math.cos(age*.8)>0 else 90
            altitude=.17+.32*max(0.,math.sin(age*2.1))**5
        if species in REGIONAL:
            spec=REGIONAL[species]
            kind=group(spec.form)
            heading=(i*137)%360
            if species=='american_dipper':altitude=.50+.025*math.sin(age*3.)
            if species=='north_american_river_otter':
                x+=1.8*math.sin(age*.38);z+=.6*math.cos(age*.38)
                heading=math.degrees(math.atan2(.6*math.sin(age*.38),1.8*math.cos(age*.38)))
                altitude=.04+.04*math.cos(age*2.)
            if spec.form in PERCHES:altitude=1.6
            if kind=='Fish':altitude=.16+.22*max(0.,math.sin(age+i))**8
            if spec.form in ('butterfly','swallowtail','bee','dragonfly','moth','bat','hummer'):
                altitude=.68+.18*math.sin(age*2+i)
                x+=.55*math.cos(age+i);z+=.35*math.sin(age+i)
        phase=(age/seconds)%frames
        frame=int(phase);blend=phase-frame
        if species!='fox':blend=blend*blend*(3-2*blend)
        y=surface(field,origin.x+x,origin.z+z)-origin.y+altitude
        shadow=0. if altitude>.05 or distance>38 else ENCOUNTERS[i][3]
        slope_x=surface(field,origin.x+x+1,origin.z+z)-origin.y-y if shadow else 0.
        slope_z=surface(field,origin.x+x,origin.z+z+1)-origin.y-y if shadow else 0.
        draw=AnimalDraw(first+frame*stride,first+((frame+1)%frames)*stride,
                               index,count,stride,blend,x,y,z,heading,shadow,slope_x,slope_z)
        draws.append((distance,draw,species,ENCOUNTERS[i][3]))
    draws.sort(key=lambda item:item[0])
    visible=[entry[1] for entry in draws[:48]]
    if subjects is not None:
        subjects.extend((key,d.x,d.y+.23*size,d.z,size) for _,d,key,size in draws[:48])
    return (AnimalDraw*len(visible))(*visible)


def build_world(high=True,plant_sites=None):
    field,segments=site()
    origin=Vec(0,surface(field,0,0),0)
    triangles=array('f')
    detail=array('f')
    target=triangles
    shadows=bytearray(512*512) if high else None

    def vertex(p,color,ground=0.):
        return (p.x-origin.x,p.y-origin.y,p.z-origin.z,*(max(0,min(255,c))/255 for c in color),ground)

    def face(a,b,c,color,material=0.):
        n=unit(cross(sub(b,a),sub(c,a)))
        light=.74+.26*(n.y*.78-n.x*.52-n.z*.35)
        rgb=tuple(v*light for v in color)
        for p in (a,b,c):target.extend(vertex(p,rgb,material))

    mesh=field.mesh()
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
            colors.append(vertex(mesh.vertices[k],tuple(c*light for c in rgb),material))
    for a,b,c,material,_ in mesh.triangles:
        if material=='terrain':
            for i in (a,b,c):triangles.extend(colors[i])
        else:face(mesh.vertices[a],mesh.vertices[b],mesh.vertices[c],(46,80,62))

    rng=random.Random(3918)
    def pine(x,z,h,near):
        nonlocal target
        y=surface(field,x,z)-.14
        def ring(height,radius,angle,count):
            return [Vec(x+math.cos(angle+i*math.tau/count)*radius,y+height,
                        z+math.sin(angle+i*math.tau/count)*radius) for i in range(count)]
        sides=(12 if high else 5) if near else 3
        bottom=ring(0,h*.023,0,sides);top=ring(h*.88,h*.009,0,sides)
        for i in range(sides):
            j=(i+1)%sides
            face(bottom[i],top[i],bottom[j],(106,85,66),.48)
            face(bottom[j],top[i],top[j],(106,85,66),.48)
        shade=rng.uniform(.82,1.13)
        layers=rng.choice((5,7)) if near else 3
        needles=rng.choice(((37,75,58),(52,91,66),(64,98,76),(48,82,76)))
        breadth=rng.uniform(.8,1.24)
        tips=(20 if high else 10) if near else 5
        for layer in range(layers):
            t=layer/layers;angle=rng.random()*math.tau
            apex=Vec(x,y+h*(.50+.50*t),z)
            crown=ring(h*(.16+.76*t),breadth*h*(.23-.18*t),angle,tips)
            for i,p in enumerate(crown):
                spread=rng.uniform(.60,.80) if i%2 else rng.uniform(1,1.18)
                crown[i]=Vec(x+(p.x-x)*spread,p.y+h*(.034 if i%2 else -.025),z+(p.z-z)*spread)
            if high and math.hypot(x,z)<55:
                target=detail
                spruce_sprays(x,y,z,h,t,angle,needles,face)
                target=triangles
            for i,p in enumerate(crown):
                face(apex,p,crown[(i+1)%tips],tuple(v*shade*(.78+.23*t) for v in needles))
    if plant_sites is not None:
        plant_sites.clear()
        plant_sites.extend(('blueberry',x,z) for x,z in BUSHES)
    for dx,dz,h,near in forest_sites(random.Random(3918)):
        if wet(dx,dz,segments,2):continue
        if plant_sites is not None and math.hypot(dx,dz)<70:plant_sites.append(("conifer",dx,dz))
        if high:shade_tree(shadows,dx,dz,h)
        pine(origin.x+dx,origin.z+dz,h,near)
    def height(x,z):return surface(field,x,z)
    river_mesh(segments,height,face)
    bank_sign(height,face)
    for key,x,z,_ in ENCOUNTERS:
        if key in REGIONAL and REGIONAL[key].form in PERCHES:snag(x,height(x,z),z,1.6,face)
    for i,(x,z) in enumerate(BUSHES):
        blueberry_patch(x,z,height,face,rng,.08+i*.05,high)

    target=detail
    for _ in range(38 if high else 0):
        dx,dz=rng.uniform(-15,15),rng.uniform(-15,35)
        if wet(dx,dz,segments,1) or abs(dx)<2:continue
        if plant_sites is not None:plant_sites.append(("fern",dx,dz))
        fern(dx,dz,height(dx,dz),rng.uniform(.45,.85),face,rng)

    target=triangles
    grass_rng=random.Random(8451)
    # Low plants and stones give the walker close-range parallax.
    for i in range(1100):
        angle=rng.random()*math.tau;radius=48*math.sqrt(rng.random())
        x=origin.x+radius*math.cos(angle);z=origin.z+radius*math.sin(angle)
        if wet(x,z,segments):continue
        y=surface(field,x,z)
        height=rng.uniform(.13,.48)
        if i%9==0:
            sides=11 if high else 6
            outline=[(height*math.cos(t*math.tau/sides),.7*height*math.sin(t*math.tau/sides)) for t in range(sides)]
            foot=[Vec(x+dx,y-.05,z+dz) for dx,dz in outline]
            ridge=[Vec(x+dx*.79,y+height*(.23+.07*math.sin(j*2.1)),z+dz*.79) for j,(dx,dz) in enumerate(outline)]
            top=Vec(x-.13*height,y+height*.42,z+.07*height)
            for j,p in enumerate(ridge):
                k=(j+1)%sides
                for tri in ((p,top,ridge[k]),(foot[j],p,foot[k]),(p,ridge[k],foot[k])):
                    face(*tri,(122,118,103))
        elif high and radius<19:
            target=detail
            for j in range(6):
                a=grass_rng.random()*math.tau
                blade(Vec(x,y,z),a,height*.56,height*.043,height*(.48+.45*grass_rng.random()),(99,123,65),face)
            target=triangles
        else:
            for j in range(4):
                t=angle+j*1.57;dx,dz=math.cos(t)*.07,math.sin(t)*.07
                face(Vec(x-dz,y,z+dx),Vec(x+dx*2,y+height*rng.uniform(.65,1),z+dz*2),
                     Vec(x+dz,y,z-dx),(90+i%21,106+i%18,62))
    base_count=len(triangles)//7
    triangles.extend(detail)
    del detail
    terrain_count=len(triangles)//7
    indices,spans=append_animals(triangles,high)
    return field,origin,triangles,terrain_count,indices,spans,base_count,shadows


class RainierView:
    name='Rainier walk'
    def __init__(self,host):
        self.host=host
        self.quality=RiverQuality()
        self.trail=BerryTrail()
        self.cruise=False
        self.sound=True
        self.notebook=None
        self.lens=False
        self.album=[]
        self.album_index=0
        self.album_loaded=None
        self.destination=None
        self.shutter=None
        self.subjects=[]
        self.frame_camera=None
        self.review_key=None
        self.photo_hint=''
        self.hint_until=0.
        self.party=None
        self.plant_sites=[]
        self.found_plants=set()
        self.solo=None
        self.hearts=self.cue=0
        self.last_tick=None
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
        if self.world is None:return ('Opening Ohanapecosh River…',)
        if self.notebook:return self.notebook.lines(self.host.window(self.name).w-2)
        if self.album:
            from wildlife_models import NAMES
            key=self.album[self.album_index].stem.rsplit('-',1)[0]
            footer=f'<  {NAMES.get(key,key)}   {self.album_index+1}/{len(self.album)}   Back  >'
            return ('',)*max(0,self.host.window(self.name).h-3)+(footer,)
        trail=self.trail
        if trail.fed:hint=f'Again ({self.hearts})'
        elif len(trail.picked)==3:hint='3/3 | Feed fox'
        else:hint=f'Berries {len(trail.picked)}/3'
        if self.lens:hint="Guidebook"
        family='Family'
        if self.party:family=f'{len(self.party.roster)} here' if self.party.roster else 'Finding'
        labels=('Stop' if self.cruise else 'Walk',hint,family,self.photo_hint if self.age<self.hint_until else ('Lens on' if self.lens else 'Camera'),'Mute' if self.sound else 'Sound')
        width=self.host.window(self.name).w-2
        bounds=[0,width//7,width*3//7,width*4//7,width*6//7,width]
        footer=''.join(label.center(b-a)[:b-a] for label,a,b in zip(labels,bounds,bounds[1:]))
        return ('',)*max(0,self.host.window(self.name).h-3)+(footer,)

    def footer(self,x,width):
        if self.album:
            if x<width*.22:self.album_index=(self.album_index-1)%len(self.album)
            elif x>width*.82:self.album_index=(self.album_index+1)%len(self.album)
            else:self.album=[]
            self.pixel_dirty=True
            return True
        if x<width//7:
            self.destination=None
            self.cruise=not self.cruise
            self.trail.guiding=False
        elif x>=width*6//7:self.sound=not self.sound
        elif x>=width*4//7:
            self.lens=not self.lens
            self.review_key=None
            self.destination=None
            self.hint_until=0.
            self.trail.guiding=self.cruise=False
        elif x>=width*3//7:
            self.destination=None
            self.notebook=PartyMenu(self)
            self.trail.guiding=self.cruise=False
        elif self.lens:
            self.cruise=self.trail.guiding=False
            self.destination=None
            from river_notebook import DiscoveryBook
            self.notebook=DiscoveryBook(self)
        else:return self.guide()
        return True

    def scene_tap(self,x,y,width,height):
        if self.album:
            self.album_index=(self.album_index+(-1 if x<width/2 else 1))%len(self.album)
            self.pixel_dirty=True
            return True
        if self.frame_camera is None:return False
        u,v=(x+.5)/width,(y+.5)/height
        camera,aspect=self.frame_camera
        field,origin=self.world[:2]
        def ground(px,pz):return surface(field,px+origin.x,pz+origin.z)-origin.y
        if self.lens:
            if self.review_key and self.age<self.hint_until:return True
            self.shutter=sighting(camera,u,v,aspect,self.subjects,ground)
            if not self.shutter:
                self.photo_hint='Look closer';self.hint_until=self.age+1.2
        else:
            # The compass still provides the child's one-tap berry route.
            radius=min(1.,aspect)*.044
            if math.hypot((1-u)*aspect-1.7*radius,1-v-1.8*radius)<1.65*radius:
                return self.guide()
            self.trail.free_look=False
            self.destination=ground_target(camera,u,v,aspect,ground,lambda a,b:wet(a,b,site()[1],-.7))
            self.cruise=self.trail.guiding=False
        self.pixel_dirty=True
        return True

    def enter_party(self,party):
        self.solo=(self.trail,self.hearts)
        self.party=party
        self.trail=BerryTrail()
        self.hearts=0

    def leave_party(self):
        if self.party:
            self.party.close()
            self.party=None
            self.trail,self.hearts=self.solo
            self.solo=None

    def guide(self):
        if self.world is None:return False
        self.destination=None
        self.lens=False
        if self.trail.fed:
            if self.party:self.party.restart=True;return True
            self.trail=BerryTrail()
        self.trail.free_look=False
        self.cruise=False
        self.trail.guiding=True
        return True

    def release(self):
        if self.context and self.context.handle:
            release=self.context.lib.pocket_scene_rainier_release
            release.argtypes=[C.c_void_p];release.restype=None
            release(self.context.handle)
        self.context=None
        self.album=[]
        self.album_loaded=None
        self.frame_camera=self.destination=self.shutter=None
        self.age=0.
        self.upload=True
        self.camera=None
        self.error=''
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
        self.world=self.job=self.pool=None

    def close(self):
        self.leave_party()
        self.release()
        self.closed=True

    def poll(self,owner):
        if self.error:return
        if self.world is None:
            if self.job is None:
                self.pool=ThreadPoolExecutor(max_workers=1)
                self.job=self.pool.submit(build_world,self.quality.high,self.plant_sites)
            if not self.job.done():return
            try:self.world=self.job.result()
            except MemoryError:
                if self.quality.auto and self.quality.high:self.quality.high=False
                else:self.error="Not enough memory for the river scene."
                return
            except Exception as error:self.error=str(error);return
            finally:self.pool.shutdown(wait=False);self.pool=self.job=None
        now=owner.clock()
        dt=min(.1,max(0.,now-(self.last_tick or now)))
        if self.destination is not None:self.destination=walk_to(owner,self.destination,dt,face_path=not self.trail.free_look)
        if self.cruise:owner._translate(1.,0.,dt*2.5)
        for plant,px,pz in self.plant_sites:
            if plant not in self.found_plants and (owner.x-px)**2+(owner.z-pz)**2<=2.5**2:
                from river_notebook import record_plant
                try:record_plant(plant)
                except OSError:continue
                self.found_plants.add(plant)
        before=len(self.trail.picked)
        fed=self.trail.fed
        self.trail.advance(owner,dt,local_pick=self.party is None)
        if self.party:
            self.party.step(owner.x,owner.z)
            shared=self.party.trail
            if self.trail.picked!=shared.picked or self.trail.fed!=shared.fed:self.trail.guiding=False
            self.trail.picked=set(shared.picked)
            self.trail.fed=shared.fed
            self.hearts=self.party.hearts
        if self.trail.fed and not fed:
            if not self.party:self.hearts+=1
            self.cue=4;self.cruise=False
        elif len(self.trail.picked)>before:self.cue=len(self.trail.picked)
        self.last_tick=now
        owner.x=max(-1000.,min(1000.,owner.x));owner.z=max(-1000.,min(1000.,owner.z))
        camera=(owner.x,owner.z,owner.yaw,owner.pitch)
        age=owner.clock()-owner.started-owner.paused_total
        if self.camera!=camera or age-self.age>=1/20:
            self.camera=camera;self.age=age;self.pixel_dirty=True

    def draw_rainier(self,ctx):
        self.pixel_dirty=False
        preview=getattr(self.notebook,'preview',None)
        if self.world is None or self.camera is None or (self.notebook and not preview):return ()
        field,origin,data,terrain_count,indices,spans,base_count,shadows=self.world
        self.quality.frame(self.age)
        high=self.quality.high
        x,z,yaw,pitch=self.camera
        eye=surface(field,x+origin.x,z+origin.z)-origin.y+1.25
        wx,wy,w,h=self.host.bounds(self.host.window(self.name))
        ox,oy=self.host.origin
        rect=((wx+ox+1)*8,(wy+oy+1)*16,(w-2)*8,(h-3)*16)
        if min(rect[2:])<1:return ()
        if self.album or preview:
            if preview:
                rows=self.notebook.picture_rows()
                if not rows:return ()
                rect=(rect[0],rect[1]+48,rect[2],rows*16)
            path=preview or self.album[self.album_index]
            w=h=0;rgb=None
            if path!=self.album_loaded:
                try:w,h,rgb=read_photo(path)
                except (OSError,ValueError,zlib.error,struct.error):
                    if preview:self.notebook.damaged.add(preview);return ()
                    self.album.pop(self.album_index)
                    if self.album:self.album_index%=len(self.album)
                    return ()
            display=ctx.lib.pocket_scene_river_photo
            display.argtypes=[C.c_void_p]+[C.c_int]*6+[C.c_void_p]
            ctx.check(display(ctx.handle,*rect,w,h,rgb))
            self.album_loaded=path
            return rect
        sound=ctx.lib.pocket_scene_river_sound
        sound.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_float]
        sound(ctx.handle,self.sound,self.cue,river_gain(x,z,site()[1]))
        self.cue=0
        draw=ctx.lib.pocket_scene_rainier
        self.subjects=[]
        self.frame_camera=((x,eye,z,yaw,pitch),rect[2]/rect[3])
        commands=encounters(field,origin,spans,self.age,self.trail.fed,(x,z),self.subjects)
        draw.argtypes=[C.c_void_p]+[C.c_int]*4+[C.c_void_p,C.c_uint,C.c_uint,C.c_void_p,
                       C.c_uint,C.POINTER(AnimalDraw),C.c_uint]+[C.c_float]*6+[C.c_int,C.c_float,C.c_int,C.c_int,C.c_void_p,C.POINTER(C.c_float),C.c_uint,C.POINTER(C.c_float),C.POINTER(C.c_float),C.c_int,C.c_void_p,C.c_int,C.c_float]
        target_x,target_z=self.trail.target(x,z)
        direction=math.atan2(target_x-x,target_z-z)-yaw
        mask=sum(1<<i for i,p in enumerate(BUSHES) if p in self.trail.picked)
        if self.upload:self.counts=len(data)//7,len(indices)
        hikers=[]
        if self.party:
            for uid,(px,pz) in self.party.roster.items():
                if uid!=self.party.ident:
                    hx,hz=px/10,pz/10
                    hikers.extend((hx,surface(field,hx+origin.x,hz+origin.z)-origin.y,hz))
        hikers_buffer=(C.c_float*len(hikers))(*hikers)
        marker=(C.c_float*3)() if self.destination is not None else None
        if marker is not None:
            mx,mz=self.destination
            marker[:]=mx,surface(field,mx+origin.x,mz+origin.z)-origin.y+.07,mz
        fish=next(((fx,fz) for key,fx,_,fz,_ in self.subjects if key=='trout'),None)
        ripple=None
        if fish:
            fx,fz=fish
            ripple=(C.c_float*3)(fx,surface(field,fx+origin.x,fz+origin.z)-origin.y+.19,fz)
        pixels=(C.c_ubyte*(3*rect[2]*rect[3]))() if self.shutter else None
        # Compose the keepsake from the player's real eye position. A short
        # telephoto view gives small birds and insects enough pixels to see.
        focal=1.
        focus=self.shutter or (self.review_key if self.lens and self.age<self.hint_until else None)
        for key,fx,fy,fz,size in self.subjects:
            if key!=focus:continue
            dx,dz=fx-x,fz-z
            horizontal=math.hypot(dx,dz)
            yaw=math.atan2(dx,dz)
            pitch=math.atan2(eye-fy,horizontal)
            focal=max(1.,min(12.,horizontal*min(1.,rect[2]/rect[3])/(size*2.8)))
            break
        photo_index=next((i for i,p in enumerate(self.subjects) if p[0]==self.shutter),-1)
        result=draw(ctx.handle,*rect,data.buffer_info()[0] if self.upload else None,self.counts[0],terrain_count if high else base_count,
                       indices.buffer_info()[0] if self.upload else None,self.counts[1],commands,len(commands),
                       x,eye,z,yaw,pitch,self.age,mask,direction,self.trail.fed,high,
                       C.addressof(C.c_ubyte.from_buffer(shadows)) if self.upload and shadows is not None else None,hikers_buffer,len(hikers)//3,marker,ripple,self.lens,pixels,photo_index,focal)
        self.context=ctx
        if result==-2 and high and self.quality.auto:
            self.release()
            self.quality.high=False
            return ()
        if result==1 and pixels is not None:
            pixels=self.shutter=None
            self.photo_hint="View blocked";self.hint_until=self.age+1.2
        else:ctx.check(result)
        if pixels is not None:
            from wildlife_models import NAMES
            try:
                save_photo(self.shutter,rect[2],rect[3],bytes(pixels))
                self.photo_hint=NAMES[self.shutter];self.review_key=self.shutter;self.cue=1
            except OSError:self.photo_hint='Save failed'
            self.hint_until=self.age+2.
            self.shutter=None
        if self.upload:self.world=field,origin,None,terrain_count,None,spans,base_count,None
        self.upload=False
        self.pixel_jobs+=1;self.pixel_frames+=1
        return rect
