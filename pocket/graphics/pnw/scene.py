"""Perspective terrain for the graphical Rainier walk. World coordinates are metres."""
from array import array
from concurrent.futures import Future, ThreadPoolExecutor
from functools import lru_cache
import ctypes as C
import math
import random
import struct
import zlib

from geometry import Vec, cross, sub, unit
from pnw import fremont_lookout as lookout
from pnw import paradise_meadow as paradise
from pnw.river_channel import TROUT_POOL
from pnw.river_camp import CAMP, OVERLOOK, SUPPLIES, camp_materials, campsite, river_stones
from pnw.river_detail import RiverQuality, shade_tree
from pnw.forest_floor import blade, broadleaf_clump, fern, nurse_log, snag, spruce_sprays, trail_cover
from pnw.rainier_habitat import forest_sites,regional_stand,ridge_grass,understory
from pnw import market_visit
from pnw import rail
from pnw.outings import AIRCRAFT,AIR_SPORTS,start_sport,HANGAR,BAYS,ExploreMenu,PauseMenu,regional_vehicle
from pnw.hiking import HikeMenu, ReliefMap, bounds, region_field, summit_start
from pnw.valley_map import ValleyMap
from pnw.river_fishing import Fishing,vibration,watch_rod
from pnw.river_party import PartyMenu
from pnw.river_overlay import Ink, album_tools, draw_book, hit, tools as river_tools
from pnw.river_notebook import DiscoveryBook
from pnw.river_explore import DIPPER_ROCK, OTTER_POOL, bank_sign, ground_target, project_subject, read_photo, save_photo, sighting, walk_to
from pnw.species import PERCH_FLIGHT, REGIONAL, group
from pnw.river_walk import BERRY_BLUFF, BUSHES, FOX, BerryTrail, blueberry_patch, centerline_distances_sq, channel, nearby_calls, river_gain, site, wet
from pnw.river_walk import hiking_paths, hiking_segments, trail_surface
from vegetation import ground_color, noise

def surface(field,x,z):
    """Height on the two actual rendered triangles in this DEM cell."""
    inset=getattr(field,'inset',None)
    if inset and (inset.origin.x<=x<=inset.origin.x+(inset.nx-1)*inset.dx and
                  inset.origin.z<=z<=inset.origin.z+(inset.nz-1)*inset.dz):
        return surface(inset,x,z)
    fx=max(0.,min(field.nx-1.,(x-field.origin.x)/field.dx))
    fz=max(0.,min(field.nz-1.,(z-field.origin.z)/field.dz))
    i,j=min(int(fx),field.nx-2),min(int(fz),field.nz-2)
    u,v=fx-i,fz-j
    k=j*field.nx+i
    a,b,c,d=(field.values[k+n] for n in (0,1,field.nx,field.nx+1))
    return a+(b-a)*u+(c-a)*v if u+v<=1 else d+(c-d)*(1-u)+(b-d)*(1-v)



@lru_cache(maxsize=1)
def valley_floor():
    from pnw.river_channel import RiverFloor
    river=channel()
    bed=river.bed_field(site()[0])
    return bed,RiverFloor(river,lambda x,z:surface(bed,x,z))


# Illustrative encounters around the starting meadow (east, north, model scale).
ENCOUNTERS=(('marmot',-95.,153.,.78),('eagle',1.,17.,1.),
            ('chipmunk',BUSHES[1][0]+1.,BUSHES[1][1]-.6,.30),('squirrel',BUSHES[0][0]+1.,BUSHES[0][1]-.7,.45),
            ('pika',-82.,126.,.38),('goat',-117.,187.,1.45),('fox',*FOX,.86),('bear',40.,28.,1.4),('trout',*TROUT_POOL,.65))


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
        if key=='american_crow':x,z=BUSHES[2][0]+1.4,BUSHES[2][1]-.3
        if key=='barred_owl':x,z=-4.,24.
        if key=='western_tiger_swallowtail':x,z=1.2,9.
        sites.append((key,x,z,spec.length))
    return tuple(sites)


ENCOUNTERS+=regional_encounters()
# Additional individuals share their species' mesh and animation buffers.
def populate(homes):
    rng=random.Random(881)
    extras=[]
    for key,x,z,size in homes:
        form=REGIONAL[key].form if key in REGIONAL else key
        if form=='trout':
            offsets=[(-2.,-1.),(-1.,2.5),(1.8,3.6),(.5,-3.)]
        elif form in ('finch','tit','crested','crow','elk','deer','butterfly','swallowtail','bee','chipmunk','squirrel'):
            offsets=[(rng.uniform(-13,13),rng.uniform(-13,13)) for _ in range(4)]
        else:continue
        if form in ('tit','finch','crested'):
            # Additional flocks along the mapped trails, away from the riverbank homes.
            path=rng.choice(hiking_paths())['xz']
            tx,tz=rng.choice(path)
            offsets.extend((tx-x+rng.uniform(-7,7),tz-z+rng.uniform(-7,7)) for _ in range(3))
        for j,(dx,dz) in enumerate(offsets,1):
            px,pz=x+dx,z+dz
            if (channel().water_height(px,pz) is not None)==(form=='trout'):
                extras.append((f'{key}#{j}',px,pz,size))
    return tuple(extras)

ENCOUNTERS+=populate(ENCOUNTERS)
ENCOUNTERS+=(('brook_trout#1',TROUT_POOL[0]+.65,TROUT_POOL[1]+.5,REGIONAL['brook_trout'].length),)
PERCHES={'owl','tufted owl','crested','climber','woodpecker','kingfisher','tit','wren','finch','songbird'}



class AnimalDraw(C.Structure):
    _fields_=[('first',C.c_uint),('second',C.c_uint),('index',C.c_uint),
              ('count',C.c_uint),('stride',C.c_uint),('blend',C.c_float),('x',C.c_float),
              ('y',C.c_float),('z',C.c_float),('heading',C.c_float),('shadow',C.c_float),('slope_x',C.c_float),('slope_z',C.c_float)]


SUMMIT_DANCERS=(('fox',0.,0.,1.),('marmot',0.,0.,.9))


def append_animals(vertices,high=False,animals=ENCOUNTERS):
    """Store each (vertex, material) once per pose, sharing indices across poses."""
    from pnw.wildlife_models import FOX_ASSETS, FOX_FRAMES, pose
    indices=array('I')
    spans=[]
    models={}
    for key,x,z,scale in animals:
        species=key.split('#')[0]
        if species in models:
            spans.append(models[species])
            continue
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
        models[species]=(first,len(palette),frames,offset,len(indices)-offset)
        spans.append(models[species])
    return indices,spans


def summit_dancers(climb,field,origin,spans):
    if not climb or not climb.dancing:return (AnimalDraw*0)()
    yaw=climb.heading+math.pi
    dx,dz=math.sin(yaw),math.cos(yaw)
    dancers=[]
    for i,(first,stride,frames,index,count) in enumerate(spans):
        beat=climb.wave*math.tau*.92+i*math.pi
        side=(i-.5)*1.36+.17*math.sin(beat)
        depth=3.8+.12*math.cos(beat)
        x,z=climb.x+dx*depth+dz*side,climb.z+dz*depth-dx*side
        hop=max(0.,math.sin(beat))**2*.22
        cycle=climb.wave*1.3*frames+i
        frame=int(cycle)%frames
        turn=math.degrees(yaw)+24*math.sin(beat)+(165 if i else 12)
        dancers.append(AnimalDraw(first+frame*stride,first+(frame+1)%frames*stride,
            index,count,stride,cycle%1,x,surface(field,x,z)-origin.y+hop,z,turn,0,0,0))
    return (AnimalDraw*len(dancers))(*dancers)


def trout_rise(age,hatch):
    # A short surface take once per feeding interval.
    phase=age%17.
    return math.sin(math.pi*phase/1.6)**2 if hatch and phase<1.6 else 0.


# Local offsets from each animal's home. Time along each leg is proportional
# to its length, so a long traverse has the same gait as a short one.
GAME_TRAIL=((0,0),(-5,8),(-11,12),(-16,5),(-10,-3),(-3,-5))
TRAIL_LEGS=tuple((x,z,ex-x,ez-z,math.hypot(ex-x,ez-z))
    for (x,z),(ex,ez) in zip(GAME_TRAIL,GAME_TRAIL[1:]+GAME_TRAIL[:1]))
TRAIL_LENGTH=sum(leg[-1] for leg in TRAIL_LEGS)
GRAZERS={'fox':(1.,1.8),'bear':(.9,1.),'goat':(.72,.95),'marmot':(.22,.52),
         'squirrel':(.18,1.2),'chipmunk':(.12,1.1),'pika':(.13,.8)}

def forage(age,scale,speed):
    pause=2.8
    t=age%(TRAIL_LENGTH*scale/speed+len(TRAIL_LEGS)*pause)
    for x,z,dx,dz,length in TRAIL_LEGS:
        duration=length*scale/speed
        if t<=pause+duration:
            along=max(0.,t-pause)/duration
            return (x+dx*along)*scale,(z+dz*along)*scale,-math.degrees(math.atan2(dz,dx)),t>pause
        t-=pause+duration
    return 0.,0.,0.,False

def bird_excursion(age,index):
    """Fly out from the home perch, bank around and settle back onto it."""
    flight=9.+index%7
    elapsed=(age+index*3.7)%(flight+5.+index%5)
    if elapsed>=flight:return 0.,0.,0.,0.,False
    angle=math.tau*elapsed/flight
    reach=6.+index%10
    side=1 if index%2 else -1
    dx=reach*math.sin(angle)
    dz=side*.65*reach*(1-math.cos(angle))
    heading=-math.degrees(math.atan2(side*.65*math.sin(angle),math.cos(angle)))
    return dx,dz,(3.+index%4)*math.sin(angle/2)**2,heading,True


def encounters(field,origin,spans,age,fed=False,observer=(0.,0.),subjects=None,optics=None,hatch=False,fly=None,fish_key='trout',kept_brook=False):
    draws=[]
    for i,((key,x,z,_),(first,stride,frames,index,count)) in enumerate(zip(ENCOUNTERS,spans)):
        if kept_brook and key=='brook_trout#1':continue
        species,_,individual=key.partition('#')
        local_age=age+2.9*int(individual or 0)
        heading=altitude=0.
        seconds=2.5
        moving=True
        flight=False
        if species in GRAZERS:
            dx,dz,heading,moving=forage(age+i*3.1,*GRAZERS[species])
            if species=='fox':
                # Come to meet the berry picker as they approach the den.
                approach=min(1.,math.hypot(x-observer[0],z-observer[1])/14.)
                dx*=approach
                dz*=approach
            x+=dx
            z+=dz
            seconds=(17/24)/frames if species=='fox' else .38
        elif species=='eagle':
            angle=age*.15
            x+=26*math.sin(angle)
            z+=15*(1-math.cos(angle))
            heading=-math.degrees(math.atan2(15*math.sin(angle),26*math.cos(angle)))
            altitude=9.+3.*math.sin(angle)
            seconds=1.8
        if species=='fox' and fed:
            x,z=FOX
            heading=30.
            altitude=.15*abs(math.sin(age*4))
        if species=='trout':
            z+=1.6*math.sin(local_age*.8)
            x+=.3*math.cos(local_age*.8)
            heading=-90 if math.cos(local_age*.8)>0 else 90
            altitude=0.
        if species in REGIONAL:
            spec=REGIONAL[species]
            heading=(i*137)%360
            if species=='american_dipper':altitude=.50+.025*math.sin(age*3.)
            if species=='north_american_river_otter':
                x+=1.8*math.sin(age*.38);z+=.6*math.cos(age*.38)
                heading=math.degrees(math.atan2(.6*math.sin(age*.38),1.8*math.cos(age*.38)))
                altitude=.04+.04*math.cos(age*2.)
            if spec.form in PERCHES:altitude=1.6
            if spec.form in PERCH_FLIGHT:
                dx,dz,lift,orientation,flight=bird_excursion(age,i)
                x+=dx
                z+=dz
                altitude+=lift
                moving=flight
                if flight:heading=orientation
            if spec.form in ('butterfly','swallowtail','bee','dragonfly','moth','bat','hummer'):
                altitude=.68+.18*math.sin(age*2+i)
                x+=.55*math.cos(age+i);z+=.35*math.sin(age+i)
        if fly and key==fish_key:
            fx,fz,t=fly
            approach=min(1.,t/2.)
            heading=-math.degrees(math.atan2(fz-z,fx-x))
            x+=(fx-x)*approach
            z+=(fz-z)*approach
        distance=math.hypot(x-observer[0],z-observer[1])
        if distance>230*(optics[2] if optics else 1.):continue
        phase=(age/seconds)%frames if moving else 0.
        frame=int(phase);blend=phase-frame
        if flight:
            frame=1
            blend=.5+.5*math.sin(age*(9+i%7))

        if species!='fox':blend=blend*blend*(3-2*blend)
        level=None
        if species=='trout' or (species in REGIONAL and group(REGIONAL[species].form)=='Fish'):
            level=channel().water_height(x,z)
            if level is None:continue
        bed=surface(field,origin.x+x,origin.z+z)
        if level is None:y=bed-origin.y+altitude
        else:
            hold=max(bed+.025,level-.53)
            rise=trout_rise(local_age,hatch) if species=='trout' else 0.
            if fly and key==fish_key:
                rise=0.
                hold+=(level-.16-hold)*min(1.,fly[2]/2.)
            y=hold+(level+.20-hold)*rise-origin.y
        shadow=0. if altitude>.05 or distance>38 else ENCOUNTERS[i][3]
        slope_x=surface(field,origin.x+x+1,origin.z+z)-origin.y-y if shadow else 0.
        slope_z=surface(field,origin.x+x,origin.z+z+1)-origin.y-y if shadow else 0.
        draw=AnimalDraw(first+frame*stride,first+((frame+1)%frames)*stride,
                               index,count,stride,blend,x,y,z,heading,shadow,slope_x,slope_z)
        priority=1
        if optics:
            camera,aspect,zoom=optics
            point=project_subject(camera,aspect,zoom,(species,x,y+.23*ENCOUNTERS[i][3],z,ENCOUNTERS[i][3]))
            if point and -.1<point[0]<1.1 and -.1<point[1]<1.1:priority=0
            elif distance>230:continue
        draws.append(((priority,distance),draw,key,ENCOUNTERS[i][3]))
    draws.sort(key=lambda item:item[0])
    visible=[entry[1] for entry in draws[:48]]
    if subjects is not None:
        subjects.extend((key,d.x,d.y+.23*size,d.z,size) for _,d,key,size in draws[:48])
    return (AnimalDraw*len(visible))(*visible)


def build_world(high=True,plant_sites=None,regional=False,*,field=None):
    field,segments=(field if field is not None else region_field(),()) if regional else (valley_floor()[0],site()[1])
    origin=Vec(0,surface(field,0,0),0)
    triangles=array('f')
    detail=array('f')
    target=triangles
    shadows=None if regional else bytearray(1024*1024)

    def vertex(p,color,ground=0.):
        return (p.x-origin.x,p.y-origin.y,p.z-origin.z,*(max(0,min(255,c))/255 for c in color),ground)

    def face(a,b,c,color,material=0.):
        n=unit(cross(sub(b,a),sub(c,a)))
        light=.74+.26*(n.y*.78-n.x*.52-n.z*.35)
        rgb=tuple(max(0,min(255,v*light))/255 for v in color)
        materials=material if isinstance(material,tuple) else (material,material,material)
        for p,m in zip((a,b,c),materials):target.extend((p.x-origin.x,p.y-origin.y,p.z-origin.z,*rgb,m))

    patch=getattr(getattr(field,'inset',None),'inset',None) if regional else None
    distant_patch=array('f')

    def terrain(field):
        child=getattr(field,'inset',None)
        if child:
            west=round((child.origin.x-field.origin.x)/field.dx)
            south=round((child.origin.z-field.origin.z)/field.dz)
            east=west+round((child.nx-1)*child.dx/field.dx)
            north=south+round((child.nz-1)*child.dz/field.dz)
        mesh=None if regional else field.mesh()
        colors=[]
        previous=[]
        for iz in range(field.nz):
            if regional:colors=[]
            for ix in range(field.nx):
                k=iz*field.nx+ix
                ax,bx=max(0,ix-1),min(field.nx-1,ix+1)
                az,bz=max(0,iz-1),min(field.nz-1,iz+1)
                sx=(field.values[iz*field.nx+bx]-field.values[iz*field.nx+ax])/((bx-ax)*field.dx)
                sz=(field.values[bz*field.nx+ix]-field.values[az*field.nx+ix])/((bz-az)*field.dz)
                n=unit(Vec(-sx,1,-sz))
                point=(Vec(field.origin.x+ix*field.dx,field.values[k],field.origin.z+iz*field.dz)
                       if regional else mesh.vertices[k])
                # Reserve .98–1.0 for regional ground. The shader interpolates
                # the DEM normal's vertical component across triangle edges.
                material=.98+.02*n.y if regional else 1.
                rgb=ground_color(point,n)
                if not regional and channel().water_height(point.x,point.z) is not None:
                    rgb=(95,108,101)
                    material=.94
                light=.55+.45*max(0,n.y*.75-n.x*.51-n.z*.42)
                colors.append(vertex(point,tuple(c*light for c in rgb),material))
            if regional:
                # The regional field is a regular grid. Only two shaded rows
                # are needed to emit its triangles, including the summit inset.
                if previous:
                    for ix in range(field.nx-1):
                        output=triangles
                        if child and west<=ix<east and south<=iz-1<north:
                            if child is not patch:continue
                            output=distant_patch
                        a,b=previous[ix],previous[ix+1]
                        c,d=colors[ix],colors[ix+1]
                        for v in (a,c,b,b,c,d):output.extend(v)
                previous=colors
        if regional:
            if child and child is not patch:terrain(child)
            return
        for a,b,c,material,_ in mesh.triangles:
            if material=='terrain':
                for i in (a,b,c):triangles.extend(colors[i])
            else:face(mesh.vertices[a],mesh.vertices[b],mesh.vertices[c],(46,80,62))
    terrain(field)

    if regional:
        position=lookout.location(field)
        if position:
            def ridge_height(x,z):return surface(field,x,z)
            lookout.build(ridge_height,face,*position)
            ridge_grass(ridge_height,face,random.Random(1934),*position)
        clearing=lookout.location(field,paradise.LATITUDE,paradise.LONGITUDE)
        if clearing:
            def meadow_height(x,z):return surface(field,x,z)
            paradise.meadow(meadow_height,face,*clearing)
            paradise.groundcover(meadow_height,face,*clearing)
            if getattr(field,'inset',None):
                from pnw.hiking import BikeLoop
                BikeLoop(clearing).build_track(meadow_height,face)
        if getattr(field,'inset',None):
            import subprocess
            from dataclasses import replace
            from pnw import summit_horizon
            try:horizon=summit_horizon.samples()
            except (OSError,ValueError,ImportError,zlib.error,subprocess.SubprocessError) as error:
                print(f'Using local Rainier horizon: {error}')
            else:
                summit_horizon.append_mesh(triangles,field,origin.y,*horizon)
                field=replace(field,panorama=True)
            from pnw.summit_ski import COURSES,RAMP_LENGTH,LIP_HEIGHT,HALF_WIDTH
            for course in COURSES[1:]:
                for gate,lane in (*course.gates,(course.length,0.)):
                    for offset in (-2.7,2.7):
                        x,z=course.location(gate,lane+offset)
                        y=surface(field,x,z)
                        face(Vec(x-.11,y-.1,z),Vec(x+.11,y-.1,z),Vec(x,y+2.,z),(200,112,35))
                        face(Vec(x,y+2.,z),Vec(x,y+1.3,z),Vec(x+.85,y+1.7,z-.65),
                             (236,116,51) if gate<course.length else (65,172,135))
                for lip,lane in course.jumps:
                    previous=None
                    for j in range(9):
                        edge=[]
                        for offset in (-HALF_WIDTH,HALF_WIDTH):
                            x,z=course.location(lip-RAMP_LENGTH+j,lane+offset)
                            edge.append(Vec(x,surface(field,x,z)+.025+j*LIP_HEIGHT/RAMP_LENGTH,z))
                        if previous:
                            color=(101,188,206) if j==8 else (201,224,232)
                            face(previous[0],previous[1],edge[0],color)
                            face(edge[0],previous[1],edge[1],color)
                        previous=edge
                    feet=[Vec(v.x,surface(field,v.x,v.z),v.z) for v in edge]
                    face(edge[0],edge[1],feet[0],(124,174,191))
                    face(feet[0],edge[1],feet[1],(124,174,191))
        triangles.extend(distant_patch)
        base_count=len(triangles)//7
        if patch:
            terrain(patch)
            from pnw.summit_ski import GATES,location
            for gate,lane in (*GATES,(150.,0.)):
                for offset in (-2.7,2.7):
                    x,z=location(gate,lane+offset)
                    y=surface(patch,x,z)
                    for dx,dz in ((.08,0),(0,.08)):
                        face(Vec(x-dx,y-.1,z-dz),Vec(x+dx,y-.1,z+dz),Vec(x,y+1.8,z),(238,170,65))
                    face(Vec(x,y+1.8,z),Vec(x,y+1.23,z),Vec(x+.65,y+1.57,z-.65),
                         (228,119,54) if gate<150 else (63,176,144))
            # Blue ice outcrops mark the game's uphill traverse.
            for step in range(1,16):
                d=150.-step*10.
                x,z=location(d,9.*math.sin(d*math.pi/150))
                for side in (-1,1):
                    px=x+side*1.25
                    pz=z-side*.48
                    ring=[]
                    for i in range(6):
                        a=i*math.tau/6
                        sx,sz=px+2.1*math.cos(a),pz+1.2*math.sin(a)
                        ring.append(Vec(sx,surface(patch,sx,sz)-.06,sz))
                    tip=Vec(px,surface(patch,px,pz)+.26,pz)
                    for i,v in enumerate(ring):
                        face(v,tip,ring[i-1],(149,202,219))
            # Low fragments lie along the slope, with open snow between outcrops.
            rng=random.Random(3299)
            for _ in range(1300):
                x=patch.origin.x+rng.uniform(1,(patch.nx-1)*patch.dx-1)
                z=patch.origin.z+rng.uniform(1,(patch.nz-1)*patch.dz-1)
                y=surface(patch,x,z)
                if noise(x,z,24)<.50 or math.hypot(surface(patch,x+1,z)-y,surface(patch,x,z+1)-y)<.48:continue
                r=rng.uniform(.13,.66)
                tip=Vec(x+.16*r,y+.43*r,z-.12*r)
                ring=[]
                for j in range(5):
                    a=(j+rng.uniform(-.19,.19))*math.tau/5
                    px,pz=x+r*math.cos(a),z+.73*r*math.sin(a)
                    ring.append(Vec(px,surface(patch,px,pz)-.04,pz))
                for j,v in enumerate(ring):face(v,tip,ring[j-1],(107,101,102))
        count=len(triangles)//7
        indices,spans=append_animals(triangles,animals=SUMMIT_DANCERS) if getattr(field,'inset',None) else (array('I',[0]),())
        return field,origin,triangles,count,indices,spans,base_count,None

    rng=random.Random(3918)
    branch_rng=random.Random(911)
    def pine(x,z,h,near,hemlock):
        nonlocal target
        y=surface(field,x,z)-.14
        def ring(height,radius,angle,count):
            return [Vec(x+math.cos(angle+i*math.tau/count)*radius,y+height,
                        z+math.sin(angle+i*math.tau/count)*radius) for i in range(count)]
        sides=(12 if high else 5) if near else 3
        radius=h*(.017 if h>=25 else .022)
        bark=(93,80,66) if hemlock else (125,86,61)
        if not hemlock:radius*=1.22
        bottom=ring(0,radius*1.4,0,sides)
        shoulder=ring(min(2.,h*.13),radius,0,sides) if near else None
        top=ring(h*.88,radius*.30,0,sides)
        trunk=((bottom,shoulder),(shoulder,top)) if shoulder else ((bottom,top),)
        for i in range(sides):
            j=(i+1)%sides
            for lo,hi in trunk:
                face(lo[i],hi[i],lo[j],bark,.48)
                face(lo[j],hi[i],hi[j],bark,.48)
        shade=rng.uniform(.82,1.13)
        layers=rng.choice((5,7)) if near else 0
        needles=rng.choice(((37,75,58),(52,91,66),(64,98,76),(48,82,76)))
        breadth=rng.uniform(.8,1.24)*(.70 if h>=25 else 1.)
        crown_base=.33 if h>=25 else .16
        if hemlock:
            needles=(46,81,65)
            breadth*=.91
            crown_base*=.78
        else:
            crown_base+=.12
            needles=(67,96,74)
        tips=20 if high else 10
        lean_x,lean_z=(rng.uniform(-.085,.085)*h for _ in range(2))
        if not near:
            # Crossed crowns keep an irregular silhouette even when each
            # individual branch would be smaller than a screen pixel.
            angle=rng.random()*math.pi
            for heading in (angle,angle+math.pi/2):
                dx=breadth*h*.245*math.cos(heading)
                dz=breadth*h*.245*math.sin(heading)
                for side,level in ((-1,0),(1,0),(-1,1),(-1,1),(1,0),(1,1)):
                    cy=crown_base+level*(1-crown_base)
                    target.extend((x+side*dx+lean_x*cy-origin.x,y+h*cy-origin.y,
                                   z+side*dz+lean_z*cy-origin.z,(side+1)*.5,
                                   needles[1]*shade/255,needles[2]*shade/255,.640+.009*level))
            return
        if hemlock:
            # The last shoot bends out past the crown and hangs below its elbow.
            ax,az=x+lean_x,z+lean_z
            direction=rng.uniform(0,math.tau)
            ux,uz=math.cos(direction),math.sin(direction)
            root=Vec(ax,y+.89*h,az)
            elbow=Vec(ax+ux*.054*h,y+1.025*h,az+uz*.054*h)
            end=Vec(ax+ux*.117*h,y+.952*h,az+uz*.117*h)
            for side in (-1,1):
                tuft=Vec(elbow.x-side*uz*.012*h,elbow.y-.026*h,elbow.z+side*ux*.012*h)
                face(root,tuft,elbow,needles)
                face(elbow,tuft,end,needles)
        for layer in range(layers):
            t=layer/layers;angle=rng.random()*math.tau
            apex=Vec(x+lean_x*(.5+.5*t),y+h*(.58+.42*layer/(layers-1)),z+lean_z*(.5+.5*t))
            crown=ring(h*(crown_base+(.92-crown_base)*t),breadth*h*(.23-.18*t),angle,tips)
            for i,p in enumerate(crown):
                spread=rng.uniform(.60,.80) if i%2 else rng.uniform(1,1.18)
                crown[i]=Vec(x+lean_x*t+(p.x-x)*spread,p.y+h*rng.uniform(-.048,.04),z+lean_z*t+(p.z-z)*spread)
            if high and math.hypot(x,z)<55:
                target=detail
                spruce_sprays(x,y,z,h,t,angle,needles,face,branch_rng,crown_base,breadth)
                target=triangles
            tone=tuple(v*shade*(.78+.23*t) for v in needles)
            # Fold each bough along its own ridge and leave sky between tips.
            for i in range(0,tips,2):
                if not hemlock and layer<layers//2 and (i//2+layer)%4==0:continue
                tip=crown[i]
                left,right=crown[i-1],crown[(i+1)%tips]
                # Separate flanking boughs toward their outer ends.
                left=Vec(.56*left.x+.44*tip.x,left.y,.56*left.z+.44*tip.z)
                right=Vec(.56*right.x+.44*tip.x,right.y,.56*right.z+.44*tip.z)
                ridge=Vec(.38*apex.x+.62*tip.x,.52*apex.y+.48*tip.y,.38*apex.z+.62*tip.z)
                face(apex,ridge,left,tone,.506)
                face(ridge,tip,left,tone,.514)
                face(apex,right,ridge,tone,.506)
                face(ridge,right,tip,tone,.514)
    if plant_sites is not None:
        plant_sites.clear()
        plant_sites.extend(('blueberry',x,z) for x,z in BUSHES)
    route=((0.,0.),*BUSHES,FOX)
    corridors=[]
    for (x,z),(ex,ez) in zip(route,route[1:]):
        length=math.hypot(ex-x,ez-z)
        corridors.append((x,z,(ex-x)/length,(ez-z)/length,length))
    for key,x,z,_ in ENCOUNTERS:
        if key in ('fox','bear','goat'):
            scale=GRAZERS[key][0]
            for ox,oz,dx,dz,length in TRAIL_LEGS:
                corridors.append((x+ox*scale,z+oz*scale,dx/length,dz/length,length*scale))
    corridors.extend(hiking_segments())
    # Leave narrow gaps in the illustrative canopy where the bluff sees the trail.
    bx,bz=BERRY_BLUFF
    eye=surface(field,bx,bz)+1.25
    sightlines=[]
    for tx,tz in (*BUSHES,FOX):
        length=math.hypot(tx-bx,tz-bz)
        sightlines.append(((tx-bx)/length,(tz-bz)/length,length,(surface(field,tx,tz)+.5-eye)/length))
    floor_rng=random.Random(3152)
    for dx,dz,h,near in forest_sites(random.Random(3918)):
        if wet(dx,dz,segments,2) or min(centerline_distances_sq(dx,dz,corridors))<(1.5+.09*h)**2:continue
        if math.hypot(dx-bx,dz-bz)<130:
            ground=surface(field,dx,dz)
            blocked=False
            for ux,uz,length,grade in sightlines:
                along=(dx-bx)*ux+(dz-bz)*uz
                across=abs((dx-bx)*uz-(dz-bz)*ux)
                if -3<along<length+3 and across<2.4+.30*h and ground+h>eye+along*grade-.8:
                    blocked=True
                    break
            if blocked:continue
        hemlock=math.sin(dx*7.13+dz*17.61)>.05
        if plant_sites is not None and math.hypot(dx,dz)<70:
            plant_sites.append(('western_hemlock' if hemlock else 'douglas_fir',dx,dz))
        shade_tree(shadows,dx,dz,h,texel=2)
        pine(origin.x+dx,origin.z+dz,h,near,hemlock)
        if near and h>30 and floor_rng.random()<(.50 if high else .16):
            # Fern colonies under older trees leave open ground between clumps.
            angle=floor_rng.uniform(0,math.tau)
            for _ in range(3):
                angle+=floor_rng.uniform(.24,.91)
                reach=floor_rng.uniform(2.,4.5)
                px,pz=dx+reach*math.cos(angle),dz+reach*math.sin(angle)
                if wet(px,pz,segments) or min(centerline_distances_sq(px,pz,corridors))<1.8**2:continue
                fern(px,pz,surface(field,px,pz),floor_rng.uniform(.95,1.55),face,floor_rng,compact=True)
                if plant_sites is not None:plant_sites.append(('fern',px,pz))
    def height(x,z):return surface(field,x,z)
    # Place deadfall on the dry shoulder, parallel to the path.
    logs=[]
    log_rng=random.Random(217)
    for x,z,u,v,length in hiking_segments():
        px=x+.5*length*u+3.4*v
        pz=z+.5*length*v-3.4*u
        if any(math.hypot(px-lx,pz-lz)<37 for lx,lz in logs):continue
        if any(wet(px+d*u,pz+d*v,segments,1) or
               min(centerline_distances_sq(px+d*u,pz+d*v,corridors))<1.6 for d in (-3,0,3)):continue
        nurse_log(px,pz,u,v,height,face,log_rng)
        logs.append((px,pz))
        if plant_sites is not None:plant_sites.append(('nurse_log',px,pz))
    water=array('f')
    def water_vertex(p,side,station):
        # The water shader takes cross-stream and downstream metres from RG.
        water.extend((p.x-origin.x,p.y-origin.y,p.z-origin.z,(side+6)/12,station/4096,0.,.35))
    channel().mesh(height,face,water_vertex)
    trail_surface(height,face)
    camp_materials(height,face)
    trail_rng=random.Random(840)
    for i,(x,z,u,v,length) in enumerate(hiking_segments()):
        if i%3:continue
        offset=trail_rng.choice((-1,1))*trail_rng.uniform(1.6,3.3)
        px,pz=x+.5*length*u+offset*v,z+.5*length*v-offset*u
        if not wet(px,pz,segments):
            fern(px,pz,height(px,pz),trail_rng.uniform(.95,1.6),face,trail_rng,compact=True)
            if plant_sites is not None:plant_sites.append(('fern',px,pz))
    campsite(height,face)
    river_stones(channel(),face,height)
    bank_sign(height,face)
    for key,x,z,_ in ENCOUNTERS:
        key=key.split('#')[0]
        if key in REGIONAL and REGIONAL[key].form in PERCHES:snag(x,height(x,z),z,1.6,face)
    for i,(x,z) in enumerate(BUSHES):
        blueberry_patch(x,z,height,face,rng,.08+i*.05,high)

    trail_cover(route,height,lambda x,z:wet(x,z,segments,.5),face)
    grass_rng=random.Random(8451)
    fern_count=0
    for i,(x,z,size,color) in enumerate(understory(random.Random(927),route)):
        if wet(x,z,segments,.5):continue
        y=surface(field,x,z)
        radius=math.hypot(x,z)
        if i%29==0 and fern_count<32:
            fern(x,z,y,.8+size*2.0,face,grass_rng,compact=not high or radius>24)
            if plant_sites is not None:plant_sites.append(("fern",x,z))
            fern_count+=1
            target=triangles
            continue
        if i%12==1:
            broadleaf_clump(x,y,z,.45+size*2.3,color,face,grass_rng)
        elif i%9==0:
            sides=11 if high else 6
            outline=[(size*math.cos(t*math.tau/sides),.7*size*math.sin(t*math.tau/sides)) for t in range(sides)]
            foot=[Vec(x+dx,y-.05,z+dz) for dx,dz in outline]
            ridge=[Vec(x+dx*.79,y+size*(.23+.07*math.sin(j*2.1)),z+dz*.79) for j,(dx,dz) in enumerate(outline)]
            top=Vec(x-.13*size,y+size*.42,z+.07*size)
            for j,p in enumerate(ridge):
                k=(j+1)%sides
                for tri in ((p,top,ridge[k]),(foot[j],p,foot[k]),(p,ridge[k],foot[k])):
                    face(*tri,(122,118,103))
        elif high and radius<19:
            target=detail
            for j in range(6):
                a=grass_rng.random()*math.tau
                blade(Vec(x,y,z),a,size*.56,size*.043,size*(.48+.45*grass_rng.random()),color,face)
            target=triangles
        else:
            for j in range(grass_rng.randint(3,7)):
                t=grass_rng.uniform(0,math.tau);dx,dz=math.cos(t)*size*.28,math.sin(t)*size*.28
                face(Vec(x-dz,y,z+dx),Vec(x+dx*2,y+size*rng.uniform(.65,1),z+dz*2),
                     Vec(x+dz,y,z-dx),color)
    triangles[:0]=water
    base_count=len(triangles)//7
    triangles.extend(detail)
    del detail
    terrain_count=len(triangles)//7
    indices,spans=append_animals(triangles,high)
    return field,origin,triangles,terrain_count,indices,spans,base_count,shadows


class RainierView:
    outing=pending_outing=stair_goal=None
    ride_time=0.
    needle_deck=False
    road=bike=glider=climb=None
    pad_sticks=(0.,0.,0.,0.)
    ground_source='Aerial'
    horizon_range='Auto'
    flight_surfaces={}
    look_gain=1.
    name='Rainier walk'
    paces=(('Walk',.52),('Brisk',.75),('Explore',8.))

    @property
    def pace_name(self):return self.paces[self.pace_index][0]

    @property
    def pace(self):return max(self.paces[self.pace_index][1],1.45 if self.run_toggle or self.shift_keys else 0.)

    def __init__(self,host):
        self.host=host
        self.ski=self.climb=None
        self.quality=RiverQuality()
        self.run_toggle=False
        self.shift_keys=set()
        self.pace_index=0
        self.regional=False
        self.valley_pose=self.map_position=None
        self.flight_surfaces={}
        self.flight_imagery=None
        self.flight_horizon=None
        self.travel_job=self.travel_pool=None
        self.meadow_site=None
        self.flower_sites=[]
        self.meadow_arrival=False
        self.lookout_arrival=False
        self.lookout_site=None
        self.travel_error=''
        self.debug_overlay=False
        self.supplies=0
        self.camp_built=False
        self.gathering=False
        self.fishing=Fishing()
        self.trail=BerryTrail()
        self.cruise=False
        self.cruise_heading=None
        self.sound=True
        self.landing_sound=False
        from pnw.traffic import Traffic
        self.traffic=Traffic()
        self.parked_cars=[]
        self.garage_taken=set()
        self.street_walls=self.nearby_walls=None
        self.traffic_bridges=None
        self.walk_bridges=None
        self.vehicle_damage=True
        self.patrol_owner=None
        self.gait_phase=0.
        self.avatar_pose=12.5
        self.parked_bike=None
        self.third_person=False
        self.neighborhood=None
        self.notebook=None
        self.lens=self.binoculars=False
        self.zoom=1.
        self.focus_key=None
        self.bluff_target=None
        self.tent=self.story=False
        self.weather=0
        self.time_mode=0
        self.season=0
        self.trip_pose=None
        self.album=[]
        self.album_book=None
        self.album_index=0
        self.album_loaded=None
        self.destination=None
        self.shutter=None
        self.subjects=[]
        self.last_caller=''
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
        self.next_call=0.
        self.stand_center=None
        self.stand_count=0
        self.person_slots=set()
        self.cockpit_kind=None
        self.upload=True
        self.context=None
        self.error=''

    def lines(self):
        if self.error:return ('Rainier terrain could not open.',self.error)
        if self.world is None and self.pending_outing:return ('Preparing '+self.pending_outing.replace('-',' ')+'…',)
        if self.world is None:return ('Opening Ohanapecosh River…',)
        if isinstance(self.notebook,HikeMenu):return self.notebook.menu_lines(self.host.window(self.name).w-2)
        if self.notebook:return self.notebook.lines(self.host.window(self.name).w-2)
        if self.album:
            from pnw.wildlife_models import NAMES
            key=self.album[self.album_index].stem.rsplit('-',1)[0]
            footer=f'{NAMES.get(key,key)}   {self.album_index+1}/{len(self.album)}'
            return ('',)*max(0,self.host.window(self.name).h-3)+(footer,)
        trail=self.trail
        if trail.fed:hint=f'Again ({self.hearts})'
        elif len(trail.picked)==3:hint='3/3 | Feed fox'
        else:hint=f'Berries {len(trail.picked)}/3'
        family='Family'
        if self.party:family=f'{len(self.party.roster)} here' if self.party.roster else 'Finding'
        labels=('Stop' if self.cruise else 'Walk',hint,'Explore',family,'Mute' if self.sound else 'Sound')
        if self.regional:
            field=self.world[0]
            elevation=round(self.walk_height(*self.camera[:2])) if self.camera else 0
            labels=(labels[0],f'{elevation} m','Explore','Mute' if self.sound else 'Sound','Map')
            if self.outing in ('ferry','wheel',*rail.RIDES.values()):
                from pnw.outings import ferry_stop
                exit_label='Ashore' if self.outing=='ferry' and ferry_stop(self.ride_time) else 'Exit'
                labels=(exit_label,'Restart','Explore',labels[3],'Map')
            if self.glider:labels=('Stop' if self.outing else 'Land','Restart','Explore',labels[3],'Map')
        if self.glider and self.outing in ('jet','hangar-jet'):labels=('Stop','Flight','Explore','Pause','Map')
        if self.outing=='scuba':labels=('Surface','Restart','Explore','Mute' if self.sound else 'Sound','Pause')
        if self.outing in rail.RIDES.values():labels=('Exit','Next stop','Explore','Mute' if self.sound else 'Sound','Pause')
        if self.road:labels=('Exit','Stop' if self.road.cruise else 'Go','Explore','Pause','View (0)' if self.road.has_car_camera else 'Restart')
        if self.on_city_foot():
            labels=('Enter car',*labels[1:])
        width=self.host.window(self.name).w-2
        bounds=[0,width//6,width*3//7,width*4//7,width*3//4,width]
        footer=''.join(label.center(b-a)[:b-a] for label,a,b in zip(labels,bounds,bounds[1:]))
        return ('',)*max(0,self.host.window(self.name).h-3)+(footer,)

    def toggle_ground_view(self):
        if self.glider or self.outing in ('ferry','wheel',*rail.RIDES.values()):return False
        if self.road:self.road.overhead=not self.road.overhead
        else:self.third_person=not self.third_person
        self.pixel_dirty=True
        return True

    def dismount_bike(self):
        if not self.bike:return
        bike=self.bike
        bike.pedaling=False
        bike.speed=0.
        self.parked_bike=bike
        x,z,heading,_=bike.advance(0.,self.walk_height)
        self.trip_pose=(x+1.1*math.cos(heading),z-1.1*math.sin(heading),heading,.08)
        self.bike=None
        self.cruise=False

    def near_bike(self):
        return (self.parked_bike is not None and self.regional and self.outing is None and self.camera
                and math.dist(self.camera[:2],self.parked_bike.position(self.parked_bike.angle))<3.)

    def remount_bike(self):
        if not self.near_bike():return False
        self.bike=self.parked_bike
        self.parked_bike=None
        self.bike.pedaling=True
        self.destination=None
        self.cruise=False
        return True

    def on_city_foot(self):
        return (getattr(self,"regional",False) and self.outing and not (self.road or self.glider or self.ski or self.bike or self.climb)
                and self.outing not in ('hoh','wheel','ferry','scuba',*rail.RIDES.values(),*market_visit.FLOORS))

    def vehicle_signal(self,key):
        road=self.road
        if not road or not road.has_car_camera:return False
        if key=='h':
            self.traffic.horn=True
        elif road.actor_kind!=9:return False
        elif key=='j':
            road.siren=not road.siren
            if not road.siren:road.stop_target=None
        elif key=='k':
            if road.stop_target is not None:road.stop_target=None
            else:
                road.stop_target=self.traffic.car_ahead(road,self.walk_height(road.x,road.z))
                if road.stop_target is not None:road.siren=True
        else:return False
        self.pixel_dirty=True
        return True

    def change_car(self):
        if self.road:
            road=self.road
            if road.has_car_camera:
                road.cancel_input()
                road.cruise=road.siren=False
                road.stop_target=None
                road.speed=road.spin=road.slip=0.
                from copy import copy
                self.walk_bridges=copy(road.bridge_roads)
                self.parked_cars.append(road)
                self.patrol_owner=road if road.patrol else None
                self.third_person=True
                sn,cs=math.sin(road.heading),math.cos(road.heading)
                length={11:5.8,12:7.8}.get(road.actor_kind,2.2)
                for side,along in ((1.7,0),(-1.7,0),(0,-length-.8),(0,length+.8),(0,0)):
                    u,v=road.x+cs*side+sn*along,road.z-sn*side+cs*along
                    if self.walk_bridges and self.walk_bridges.deck is not None:
                        probe=copy(self.walk_bridges)
                        probe.sample(u,v,surface(self.world[0],u,v),True)
                        if probe.deck is None:continue
                    self.trip_pose=(u,v,math.atan2(road.x-u,road.z-v),.08)
                    break
            self.road=None
        elif self.camera and self.on_city_foot():
            from pnw.outings import StreetRide
            from pnw.traffic import vehicle_type
            x,z=self.camera[:2]
            parked=min(self.parked_cars,key=lambda r:math.hypot(x-r.x,z-r.z),default=None)
            distance,key,body=self.traffic.nearest_car(x,z)
            parked_dist=math.inf if parked is None else math.hypot(x-parked.x,z-parked.z)
            patrol=self.patrol_owner
            patrol_dist=math.dist((x,z),patrol.patrol) if patrol and patrol.patrol else math.inf
            if patrol_dist<=min(5.,parked_dist,distance):
                road=StreetRide('sports-car')
                road.x,road.z=patrol.patrol
                road.heading=road.chase_heading=patrol.patrol_heading
                road.actor_kind=9
                road.patrol=patrol.patrol=None
                self.patrol_owner=None
                road.overhead=True
                self.road=road
            elif min(distance,parked_dist)>5.:
                self.photo_hint='Move closer to a vehicle'
                self.hint_until=self.age+2.
            elif parked_dist<=distance:
                slot=getattr(parked,'garage_slot',None)
                if slot is not None:
                    self.garage_taken.add(slot)
                    parked.garage_slot=None
                self.road=parked
                self.parked_cars.remove(parked)
            else:
                road=StreetRide('sports-car')
                self.traffic.take(key,body)
                road.x,road.z,road.heading=body.x,body.z,body.heading
                road.chase_heading=body.heading
                road.speed=body.vx*math.sin(body.heading)+body.vz*math.cos(body.heading)
                road.spin,road.damage=body.spin,body.damage
                road.actor_kind=vehicle_type(key[0]+key[2])
                road.paint=1+(key[0]+key[2])%4
                road.overhead=True
                self.road=road
                road.alert_patrol(self.traffic.bodies.values())
            if self.road and patrol and patrol is not self.road and patrol.patrol:
                self.road.patrol,self.road.patrol_heading=patrol.patrol,patrol.patrol_heading
                self.road.pursuit=patrol.pursuit
                patrol.patrol=None
            self.destination=None
            self.cruise=False
        else:return False
        self.pixel_dirty=True
        return True

    def footer(self,x,width):
        if self.outing in rail.RIDES.values():
            if x<width//6:self.outing='station'
            elif x<width*3//7:self.ride_time=rail.sample(self.outing,self.ride_time)[2]
            elif x<width*4//7:self.notebook=ExploreMenu(self)
            elif x<width*3//4:self.sound=not self.sound
            else:self.pause_game()
            self.pixel_dirty=True
            return True
        if self.outing=='scuba':
            if x<width//6:self.start_outing('boat')
            elif x<width*3//7:self.start_outing('scuba')
            elif x<width*4//7:self.notebook=ExploreMenu(self)
            elif x<width*3//4:self.sound=not self.sound
            else:self.pause_game()
            self.pixel_dirty=True
            return True
        if self.on_city_foot() and x<width//6:
            return self.change_car()
        if self.road:
            if x<width//6:self.change_car()
            elif x<width*3//7:self.road.cruise=not self.road.cruise
            elif x<width*4//7:self.notebook=ExploreMenu(self)
            elif x<width*3//4:self.pause_game()
            elif self.road.has_car_camera:self.road.overhead=not self.road.overhead
            else:self.start_outing(self.pending_outing)
            self.pixel_dirty=True
            return True
        if self.glider and self.outing in ('jet','hangar-jet'):
            if width//6<=x<width*3//7:
                self.glider.menu=not self.glider.menu
                self.pixel_dirty=True
                return True
            if width*4//7<=x<width*3//4:
                self.pause_game()
                return True
        if x>=width*3//4 and not self.album and self.outing in (
                'market','fishshop','needle','wheel','ferry',*market_visit.DESTINATIONS.values()):
            self.cruise=False;self.destination=None
            self.notebook=market_visit.DistrictMap(self)
            self.pixel_dirty=True
            return True
        if self.regional and not self.album and width*4//7<=x<width*3//4:
            self.sound=not self.sound
            self.landing_sound=False
            self.pixel_dirty=True
            return True
        if self.outing in ('ferry','wheel',*rail.RIDES.values()):
            from pnw.outings import CROSSING,DOCK_TIME,ferry_stop
            stop=ferry_stop(self.ride_time) if self.outing=='ferry' else None
            if self.outing=='ferry' and x<width//6:
                inbound=self.ride_time%(2*(CROSSING+DOCK_TIME))>=CROSSING+DOCK_TIME
                self.start_outing(stop or ('bainbridge' if inbound else 'colman'))
            elif width//6<=x<width*3//7:self.ride_time=0.
            elif x<width*4//7:
                if self.outing=='wheel' and x<width//6:self.outing='waterfront'
                self.cruise=False
                self.destination=None
                self.notebook=ExploreMenu(self)
            return True
        if self.glider:
            if x<width//6:self.end_flight()
            elif x<width*3//7:
                powered=self.glider.powered
                self.end_flight()
                if self.outing in AIR_SPORTS:self.glider=start_sport(self.outing,self.world[0])
                elif self.outing:self.glider=regional_vehicle(self.outing,self.world[0])
                else:self.start_glide(powered)
            else:
                self.end_flight()
                if x>=width*3//4:
                    self.notebook=ReliefMap(self)
                    self.album_loaded=None
                else:self.notebook=ExploreMenu(self)
            return True
        if self.bike and width*3//7<=x<width*4//7:
            self.notebook=ExploreMenu(self)
            return True
        if self.ski:self.stop_ski()
        if self.album:
            if x<width*.22:self.album_index=(self.album_index-1)%len(self.album)
            elif x>width*.82:self.album_index=(self.album_index+1)%len(self.album)
            else:
                self.album=[]
                self.notebook=self.album_book
                self.album_book=None
            self.pixel_dirty=True
            return True
        if x<width//6:
            self.destination=None
            self.cruise=not self.cruise
            self.cruise_heading=None
            self.trail.guiding=False
        elif self.regional and x>=width*3//4:
            self.cruise=False
            self.destination=None
            self.notebook=ReliefMap(self)
            self.album_loaded=None
        elif width*3//7<=x<width*4//7 or self.regional:
            self.destination=None
            self.cruise=self.trail.guiding=False
            self.notebook=ExploreMenu(self)
        elif x>=width*3//4:self.sound=not self.sound
        elif x>=width*4//7:
            self.destination=None
            self.notebook=PartyMenu(self)
            self.trail.guiding=self.cruise=False
        else:return self.guide()
        return True

    def field_action(self,action):
        if action=='book':
            self.destination=None
            self.cruise=self.trail.guiding=False
            self.notebook=DiscoveryBook(self)
        elif action=='fish':self.fish()
        elif action=='keep':
            self.fishing.keep()
            self.photo_hint=self.fishing.note
            self.hint_until=self.age+2.
        elif action=='zoom':
            self.zoom=next((level for level in (2.,4.,8.) if level>self.zoom+.01),1.)
        elif action in ('camera','binoculars'):
            self.lens=action=='camera' and not self.lens
            self.binoculars=action=='binoculars' and not self.binoculars
            self.zoom=4. if self.binoculars else 1.
            self.focus_key=None
            self.review_key=self.destination=None
            self.hint_until=0.
            self.trail.guiding=self.cruise=False
        elif action=='shutter' and self.frame_camera:
            self.shutter=self.focus_key
            if not self.shutter:self.photo_hint='Aim at wildlife';self.hint_until=self.age+2.
        self.pixel_dirty=True

    def scene_tap(self,x,y,width,height):
        if self.album:
            action=next((a for a,_,box in album_tools(width,height) if hit(box,x,y)),None)
            if action=='back':
                self.album=[]
                self.notebook=self.album_book or DiscoveryBook(self)
                self.album_book=None
                self.pixel_dirty=True
                return True
            step=-1 if action=='prev' or (action is None and x<width/2) else 1
            self.album_index=(self.album_index+step)%len(self.album)
            self.pixel_dirty=True
            return True
        for action,_,box in self.walk_tools(width,height):
            if self.glider and self.glider.menu:
                if self.glider.wheel_choice(x,y,width,height)!=action:continue
            elif not hit(box,x,y):continue
            if action in ('stairs-up','stairs-down','stairs-market'):
                if action=='stairs-market':
                    from pnw.seattle_places import arcade_origin
                    from pnw.pike_market import offset
                    self.destination=offset(arcade_origin(),-8,5.5)
                else:
                    lane=-1. if action=='stairs-up' else 1.
                    self.destination=(lane,-4.6)
                    self.stair_goal=(lane,-12.)
                self.trail.guiding=self.trail.free_look=self.cruise=False
            elif action in ('rent-bike','rent-scooter'):
                self.start_outing('bicycle' if action=='rent-bike' else 'scooter')
            elif action=='needle_lift':
                from pnw.seattle_places import places
                nx,nz=places()['Space Needle']
                self.outing='needle'
                self.needle_deck=not self.needle_deck
                self.destination=None
                self.cruise=False
                self.trip_pose=(nx+12,nz-16,2.50,.13) if self.needle_deck else (nx,nz-215,0.,-.38)
            elif action in ('horn','siren','stop-car'):
                self.vehicle_signal({'horn':'h','siren':'j','stop-car':'k'}[action])
            elif action in ('shop','repair','paint','tune','leave-shop'):
                self.photo_hint=self.road.shop_action(action)
                self.hint_until=self.age+2
            elif action=='pedal':self.bike.pedaling=not self.bike.pedaling
            elif action=='dismount':self.dismount_bike()
            elif action=='remount':self.remount_bike()
            elif action=='run':self.run_toggle=not self.run_toggle
            elif action=='ground-view':self.toggle_ground_view()
            elif self.ski:
                if action=='leave':self.stop_ski()
                elif action=='family':self.notebook=PartyMenu(self,ski=True)
                else:self.ski.action(action)
            elif action=='launch':self.start_glide()
            elif action in BAYS:self.start_outing(action,self.camera)
            elif action=='surface':self.start_outing('boat')
            elif action=='air-action':self.glider.action()
            elif action=='pause':self.pause_game()
            elif self.glider:
                flight=self.glider
                if action=='motor':flight.toggle_motor()
                elif action=='fast':flight.toggle_speed()
                elif action=='descend':flight.descending=not flight.descending
                flight.menu=action=='wheel' and not flight.menu
            elif action=='encore':self.climb.wave=0.
            elif action=='vista':self.climb.next_vista()
            elif action=='exit_climb':self.climb=None
            elif action=='reach' and self.climb:self.climb.reach()
            elif action=='berry_view':
                bx,bz=BERRY_BLUFF
                stops=[p for p in BUSHES if p not in self.trail.picked]+[FOX]
                at_bluff=self.camera and math.hypot(self.camera[0]-bx,self.camera[1]-bz)<1
                index=(stops.index(self.bluff_target)+1)%len(stops) if at_bluff and self.bluff_target in stops else 0
                self.bluff_target=tx,tz=stops[index]
                self.focus_key=None
                field=self.world[0]
                yaw=math.atan2(tx-bx,tz-bz)
                pitch=math.atan2(surface(field,bx,bz)+1.25-surface(field,tx,tz)-.48,math.hypot(tx-bx,tz-bz))
                self.trip_pose=(bx,bz,yaw,pitch)
                self.cruise=self.trail.guiding=False
                self.destination=None
                self.zoom=8.
            elif action in ('camera','binoculars','zoom','shutter','fish','keep','book'):self.field_action(action)
            elif action.startswith('gather'):
                self.supplies|=1<<int(action[-1])
                self.photo_hint='Camp supplies '+str(self.supplies.bit_count())+'/3'
                self.hint_until=self.age+2.
            elif action=='build':
                self.gathering=False
                self.camp_built=self.tent=True
                self.photo_hint='Camp is ready'
                self.hint_until=self.age+2.
            elif action in ('deck','ground'):self.visit_lookout(deck=action=='deck')
            elif action=='map':
                self.notebook=ValleyMap(self)
                self.destination=None
                self.cruise=self.trail.guiding=False
                self.album_loaded=None
            self.pixel_dirty=True
            return True
        if self.ski:
            self.ski.tap_slope((x+.5)/width,(y+.5)/height)
            self.pixel_dirty=True
            return True
        if self.glider:
            self.glider.menu=False
            return True
        if self.climb or self.bike or self.road:return True
        if self.frame_camera is None:return False
        self.stair_goal=None
        u,v=(x+.5)/width,(y+.5)/height
        camera,aspect=self.frame_camera
        field,origin=self.world[:2]
        def ground(px,pz):return self.walk_height(px+origin.x,pz+origin.z)-origin.y
        if self.binoculars:return True
        if self.lens:
            if self.review_key and self.age<self.hint_until:return True
            self.shutter=sighting(camera,u,v,aspect,self.subjects,
                lambda px,pz:surface(field,px+origin.x,pz+origin.z)-origin.y,zoom=self.zoom)
            if not self.shutter:
                self.photo_hint='Look closer';self.hint_until=self.age+1.2
        else:
            held=getattr(self,'market_snack',None)
            if held and u>.61 and v>.66:
                self.photo_hint={'coffee':'Took a sip','piroshky':'Ate the piroshky',
                                 'flowers':'Put away the bouquet','honey':'Put away the honey'}[held]
                self.market_snack=None
                self.hint_until=self.age+2;self.pixel_dirty=True
                return True
            if self.outing in market_visit.STREETS:
                from pnw.seattle_places import MarketDirectory,arcade_origin
                from pnw.pike_market import offset
                center=arcade_origin()
                # Dimensions in metres keep touch areas attached to the fixtures.
                fixtures=(('directory',*offset(center,-3,-1.95),1.50,.82,.61),
                          ('fish',*offset(center,2.78,4.42),1.,1.9,.75),
                          ('flowers',*offset(center,-4,4.85),1.35,1.55,.60),
                          ('honey',*offset(center,8,4.85),1.15,1.55,.54),
                          ('piroshky',*market_visit.storefront_point(4,-1.95),1.,2.1,.70),
                          ('coffee',*market_visit.storefront_point(-6.6,-1.95),1.,2.1,.70))
                hits=[]
                for item,px,pz,dy,half_w,half_h in fixtures:
                    if math.hypot(px-camera[0],pz-camera[2])>7.:continue
                    base=ground(px,pz) if item in ('coffee','piroshky') else surface(field,*center)-origin.y
                    projected=project_subject(camera,aspect,1.,(item,px,base+dy,pz,1.))
                    if projected:
                        sx,sy,depth=projected
                        if abs(u-sx)*aspect*depth<half_w and abs(v-sy)*depth<half_h:
                            hits.append((depth,item))
                if hits:
                    _,item=min(hits)
                    if item=='directory':
                        self.notebook=MarketDirectory(self)
                    elif item=='fish':
                        if self.age>=self.fish_counter.player_ready:
                            self.fish_counter.order(self.age)
                            self.photo_hint='Fish on its way!'
                    else:
                        self.market_snack=item
                        self.photo_hint={'coffee':'Fresh coffee','piroshky':'Warm piroshky',
                                         'flowers':'Fresh bouquet','honey':'Jar of honey'}[item]
                    self.hint_until=self.age+2
                    self.destination=None;self.cruise=False
                    self.pixel_dirty=True
                    return True
            # The compass still provides the child's one-tap berry route.
            radius=min(1.,aspect)*.044
            if not self.regional and math.hypot((1-u)*aspect-1.7*radius,1-v-1.8*radius)<1.65*radius:
                return self.guide()
            self.trail.free_look=False
            self.destination=ground_target(camera,u,v,aspect,ground,
                                           bounds=bounds(field),regional=self.regional)
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
        if self.world is None or self.regional:return False
        self.destination=None
        self.lens=self.binoculars=False
        self.zoom=1.
        if self.trail.fed:
            if self.party:self.party.restart=True;return True
            self.trail=BerryTrail()
        self.trail.free_look=False
        self.cruise=False
        self.trail.guiding=True
        return True

    def pause_game(self):
        self.pause_previous=self.notebook
        if self.glider:self.glider.menu=False
        self.notebook=PauseMenu(self)
        self.pause_owner.cancel_keys()
        self.pause_started=self.pause_owner.clock()-self.pause_owner.paused_total
        self.pixel_dirty=True

    def resume_game(self):
        owner=self.pause_owner
        owner.paused_total+=max(0.,owner.clock()-owner.paused_total-self.pause_started)
        self.last_tick=owner.clock()
        self.notebook=self.pause_previous
        self.pixel_dirty=True

    def controller_button(self,button):
        if isinstance(self.notebook,PauseMenu):
            self.notebook.button(button)
            self.pixel_dirty=True
            return
        if button==6 and self.world and not self.travel_job:
            self.pause_game()
            return
        if self.notebook:
            if isinstance(self.notebook,HikeMenu):
                self.notebook.menu_button(button)
                self.pixel_dirty=True
            elif isinstance(self.notebook,DiscoveryBook):
                if button==1:self.notebook=None
                elif button in (13,14):self.notebook.turn_page(-1 if button==13 else 1)
                self.pixel_dirty=True
            return
        if self.road:
            if button in (7,2,3):self.vehicle_signal({7:'h',2:'j',3:'k'}[button])
            if button==0:self.road.cruise=not self.road.cruise
            if button==8 and self.road.has_car_camera:self.road.overhead=not self.road.overhead
            if button==1:self.change_car()
            self.pixel_dirty=True
            return
        if self.bike:
            if button==0:self.bike.pedaling=not self.bike.pedaling
            if button==1:self.dismount_bike()
            if button==8:self.toggle_ground_view()
            return
        if self.glider:
            if self.outing in AIR_SPORTS:
                if button==0:self.glider.action()
                elif button==1:
                    if self.outing=='scuba':self.start_outing('boat')
                    else:self.end_flight()
                return
            if self.outing in AIRCRAFT and button==8:self.glider.toggle_gear()
            elif self.outing in AIRCRAFT and button==4:
                self.glider.menu=not self.glider.menu
                self.glider.cancel_input()
            elif self.outing in AIRCRAFT and self.glider.menu:
                if button==11:self.glider.toggle_speed()
                elif button==13:self.glider.toggle_motor()
                elif button==14:self.glider.descending=not self.glider.descending
                self.glider.menu=False
            elif self.outing in AIRCRAFT and button in (11,12):
                self.glider.flaps=max(0,min(2,self.glider.flaps+(1 if button==12 else -1)))
            elif button==1:self.end_flight()
            elif button==3:self.glider.toggle_speed()
            elif button==2 and self.glider.powered:self.glider.toggle_motor()
            elif button==0:self.glider.descending=not self.glider.descending
        elif self.climb:
            if button==0:
                if self.climb.raised:self.start_glide()
                else:self.climb.reach()
            elif button==14 and self.climb.raised and self.climb.panorama:self.climb.next_vista()
            elif button==1 and self.climb.raised:self.climb.wave=0.

        elif self.world and not self.ski and not self.album and not self.notebook:
            if button==7:
                self.run_toggle=not self.run_toggle
                self.pixel_dirty=True
                return
            if button==8:
                self.toggle_ground_view()
                return
            if self.outing=='hangar' and button==0:
                bay=self.hangar_bay()
                if bay:self.start_outing(bay,self.camera)
                return
            if button==0:action='shutter' if self.lens else 'fish'
            elif button==1:action='book'
            else:action={2:'camera',3:'binoculars',10:'zoom'}.get(button)
            if not action:return
            window=self.host.window(self.name)
            available={tool for tool,_,_ in self.walk_tools(window.w-2,window.h-3)}
            if button==1 and 'keep' in available:action='keep'
            if action in available:
                self.field_action(action)

    def walk_with_controller(self,owner,dt):
        sideways,back,turn,look=self.pad_sticks
        if turn or look:
            self.trail.free_look=True
            owner.yaw+=turn*dt*1.6*self.look_gain/self.zoom
            owner.pitch=max(-1.,min(1.,owner.pitch+look*dt*self.look_gain/self.zoom))
        if sideways or back:
            self.destination=None
            self.cruise=self.trail.guiding=False
            scale=3.2*dt/max(1.,math.hypot(sideways,back))
            owner._translate(-back,sideways,scale)

    def start_mountain_sport(self,label):
        if not getattr(self.world[0],'inset',None):
            self.travel_error='This activity needs the Rainier summit terrain.'
            return False
        if label=='Mountain bike loop':
            if not self.meadow_site:
                self.travel_error='Meadow terrain unavailable.'
                return False
            self.start_bike()
        elif label=='Put on skis':self.start_ski()
        elif label=='Climb summit ice':self.start_climb()
        else:self.start_glide(powered=label=='Paramotor')
        return True

    def start_bike(self):
        from pnw.hiking import BikeLoop
        self.parked_bike=None
        self.bike=BikeLoop(self.meadow_site)
        self.destination=self.trip_pose=self.map_position=None
        self.lens=self.binoculars=self.cruise=self.trail.guiding=False
        self.zoom=1.

    def end_flight(self):
        flight=self.glider
        flight.cancel_input()
        self.trip_pose=(flight.x,flight.z,flight.heading,-.12)
        self.glider=None
        self.photo_hint='Back on the trail'
        self.hint_until=self.age+3.
        self.pixel_dirty=True

    def start_glide(self,powered=False):
        from pnw.hiking import HangGlider
        if not self.climb:self.start_climb()
        self.glider=HangGlider(self.climb,self.walk_height,powered)
        self.photo_hint='Drag to turn • Up to dive • Flight for speed'
        self.hint_until=self.age+7.
        self.climb=None
        self.cruise=False
        self.destination=None

    def start_climb(self):
        from pnw.hiking import SummitClimb
        self.stop_ski()
        self.climb=SummitClimb(self.world[0].inset,panorama=self.world[0].panorama)
        self.destination=self.trip_pose=self.map_position=None
        self.cruise=self.binoculars=self.lens=False
        self.zoom=1.

    def start_ski(self):
        from pnw.summit_ski import COURSES,SkiRun,start_tilt
        self.ski=SkiRun(COURSES if getattr(self.world[0].inset,"inset",None) else COURSES[1:])
        self.ski.tilt=start_tilt()
        self.cruise=self.binoculars=self.lens=False
        self.destination=self.trip_pose=None
        self.zoom=1.

    def stop_ski(self):
        self.landing_sound=False
        if self.ski and self.ski.room:self.ski.leave_room()
        if self.ski and self.ski.tilt:self.ski.tilt.stop.set()
        self.ski=None

    def release(self):
        if self.neighborhood:self.neighborhood.close();self.neighborhood=None
        self.flight_surfaces={}
        if self.flight_imagery:self.flight_imagery.close();self.flight_imagery=None
        if self.flight_horizon:self.flight_horizon.close();self.flight_horizon=None
        self.road=self.bike=self.glider=self.climb=None
        self.stop_ski()
        if self.context and self.context.handle:
            release=self.context.lib.pocket_scene_rainier_release
            release.argtypes=[C.c_void_p];release.restype=None
            release(self.context.handle)
        self.context=None
        self.album=[]
        self.album_book=None
        self.album_loaded=None
        self.frame_camera=self.destination=self.shutter=None
        self.fishing=Fishing()
        self.age=0.
        self.next_call=0.
        self.stand_center=None
        self.stand_count=0
        self.person_slots=set()
        self.cockpit_kind=None
        self.upload=True
        self.camera=None
        self.error=''
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
        self.world=self.job=self.pool=None

    def move_to_view(self,camp=False,pool=False):
        field=self.world[0]
        x,z,tx,tz=(CAMP[0]+3.,CAMP[1]-7.,*CAMP) if camp else OVERLOOK
        if pool:x,z,tx,tz=9.,7.,*TROUT_POOL
        aim_y=channel().water_height(tx,tz)-.3 if pool else surface(field,tx,tz)
        yaw=math.atan2(tx-x,tz-z)
        pitch=math.atan2(self.walk_height(x,z)+1.25-aim_y,math.hypot(tx-x,tz-z))
        self.trip_pose=(x,z,yaw,pitch)
        self.destination=self.review_key=None
        self.lens=self.binoculars=self.cruise=self.trail.guiding=False
        self.zoom=1.

    def visit_trail(self,name):
        path=next(p['xz'] for p in hiking_paths() if p['name']==name)
        x,z=min(path[:-1],key=lambda p:math.hypot(*p))
        tx,tz=path[path.index([x,z])+1]
        self.trip_pose=(x,z,math.atan2(tx-x,tz-z),.13)
        self.destination=self.review_key=None
        self.lens=self.binoculars=self.cruise=self.trail.guiding=False

    def update_fishing(self,age):
        previous=self.fishing.state
        pulse=self.fishing.update(age)
        if self.fishing.state=='bite':
            if previous!='bite':self.fishing.lift=watch_rod()
            elif self.fishing.lift and self.fishing.lift.is_set():
                pulse=self.fishing.tap(age,self.camera[:2])
        if pulse:vibration(pulse)
        if previous!=self.fishing.state:
            self.photo_hint=self.fishing.note
            self.hint_until=age+2.
            if self.fishing.state=='landed':
                from pnw.river_notebook import record_catch
                try:record_catch(self.fishing.target)
                except OSError:self.photo_hint+=' - guidebook save failed'
                else:self.photo_hint+=' - in guidebook'
                self.hint_until=age+4.

    def fish(self):
        pulse=self.fishing.tap(self.age,self.camera[:2])
        if pulse:vibration(pulse)
        self.photo_hint=self.fishing.note
        self.hint_until=self.age+2.

    def hangar_bay(self):
        if self.camera:
            x,z=self.camera[:2]
            for kind,(dx,_) in BAYS.items():
                if math.hypot(x-HANGAR[0]-dx,z-HANGAR[1])<8:return kind
        return None

    def walk_tools(self,width,height):
        if self.road:
            options=(('repair','Repair'),('paint','Paint'),('tune','Factory tune' if self.road.tuned else 'Street tune'),
                     ('leave-shop','Done')) if self.road.at_shop() else (('leave-shop','Cancel shop'),) if self.road.shop_target else (('shop','Auto shop'),)
            buttons=[(action,label,(width-15,3*i,15,3)) for i,(action,label) in enumerate(options)]
            if self.road.has_car_camera:
                buttons.append(('horn','Horn',(width-15,height-4,15,3)))
            if self.road.actor_kind==9:
                buttons.extend((('siren','Siren',(width-15,height-10,15,3)),
                                ('stop-car','Stop / release',(width-15,height-7,15,3))))
            return buttons
        if self.outing=='hangar':
            kind=self.hangar_bay()
            return [(kind,'Board '+BAYS[kind][1],(1,height-4,19,3))] if kind else []
        if self.outing in ('ferry','wheel',*rail.RIDES.values()):return []
        if self.glider:return self.glider.controls(width,height)
        if self.bike:return [('dismount','Dismount',(0,0,11,3)),
                            ('ground-view','View (0)',(width-12,height-4,12,3)),
                            ('pedal','Brake' if self.bike.pedaling else 'Pedal',(width//2-6,height-4,12,4))]
        if self.ski:return self.ski.controls(width,height)
        if self.climb:return self.climb.controls(width,height)
        buttons=river_tools(width,height,self.lens,self.binoculars,self.zoom,self.regional)
        buttons.append(('run','Walk' if self.run_toggle else 'Run',(width-12,height-10,12,3)))
        buttons.append(('ground-view','View (0)',(width-12,height-7,12,3)))
        if self.near_bike():buttons.append(('remount','Mount bike',(1,height-4,14,3)))
        if self.outing in market_visit.FLOORS:
            level=int(self.outing[-1])
            if self.camera and self.camera[1]<2:
                label='Up to Market' if level==5 else f'Up to level {level+1}'
                buttons.append(('stairs-up',label,(1,height-4,15,3)))
                if level>3:buttons.append(('stairs-down',f'Down to level {level-1}',(width-18,height-4,17,3)))
            return buttons
        if self.outing in market_visit.STREETS and self.camera:
            from pnw.seattle_places import places
            if not (self.lens or self.binoculars):
                from pnw.pike_market import rental_site,offset
                from pnw.seattle_places import arcade_origin
                if math.dist(self.camera[:2],offset(arcade_origin(),-8,5.5))<7:
                    buttons.append(('stairs-market','DownUnder stairs',(1,height-4,18,3)))
                if math.dist(self.camera[:2],rental_site(arcade_origin()))<9:
                    buttons.extend((('rent-bike','Rent bike',(1,height-4,12,3)),
                                    ('rent-scooter','Rent scooter',(width-16,height-4,15,3))))
            nx,nz=places()['Space Needle']
            near_needle=math.hypot(self.camera[0]-nx,self.camera[1]-nz)<35
        else:near_needle=False
        if self.outing=='needle' or near_needle:buttons.append(('needle_lift','Ground' if self.needle_deck else 'Visit deck',(1,height-6,13,4)))
        if not self.regional and self.camera and not (self.lens or self.binoculars):
            position=self.camera[:2]
            if math.dist(position,TROUT_POOL)<=12:
                buttons.append(('fish',self.fishing.label(self.age),(width-15,height-4,14,3)))
            nearby=[(math.dist(position,(x,z)),i,name) for i,(name,x,z) in enumerate(SUPPLIES)
                    if not self.supplies & (1<<i) and math.dist(position,(x,z))<=4.5]
            if self.fishing.state=='landed' and self.fishing.target=='brook_trout#1':
                buttons.append(('keep','Keep brook',(1,height-4,14,3)))
            elif nearby:
                _,i,name=min(nearby)
                buttons.append((f'gather{i}','Gather '+name,(1,height-4,15,3)))
            elif self.supplies==7 and not self.camp_built and math.dist(position,CAMP)<6:
                buttons.append(('build','Build camp',(1,height-4,15,3)))
        if self.binoculars and not self.regional:
            buttons.append(('berry_view','Berry view',(1,height-3,11,2)))
        if self.regional and self.lookout_site and self.camera:
            x,z=self.camera[:2]
            cx,cz,_=self.lookout_site
            if math.hypot(x-cx,z-cz)<35:
                on_deck=max(abs(x-cx),abs(z-cz))<=3.2
                buttons.append(('ground' if on_deck else 'deck','Step down' if on_deck else 'Up to deck',(1,3,12,2)))
        return buttons

    def visit_lookout(self,deck=False):
        if not self.lookout_site:return
        x,z,_=self.lookout_site
        if deck:
            px,pz=x,z-2.7
            peak=max(range(len(self.world[0].values)),key=self.world[0].values.__getitem__)
            field=self.world[0]
            tx=field.origin.x+(peak%field.nx)*field.dx
            tz=field.origin.z+(peak//field.nx)*field.dz
            yaw,pitch=math.atan2(tx-px,tz-pz),-.12
        else:
            px,pz=x+9,z-16
            yaw=math.atan2(x-px,z-pz)
            pitch=math.atan2(surface(self.world[0],px,pz)+1.25-self.lookout_site[2]-3.,math.hypot(x-px,z-pz))
        self.trip_pose=(px,pz,yaw,pitch)
        self.destination=None
        self.cruise=self.binoculars=False
        self.zoom=1.

    def visit_meadow(self):
        if self.meadow_site:
            x,z=self.meadow_site
            self.trip_pose=(x,z,-.30,-.035)
            self.destination=None
            self.cruise=self.binoculars=self.lens=False
            self.zoom=1.

    def start_outing(self,outing,landing=None):
        self.stair_goal=None
        self.stair_landing=landing
        from pnw.outings import build_world as build_outing
        self.pending_outing=outing
        self.travel_error=''
        if self.outing and self.outing not in ('hoh','scuba') and outing not in ('hoh','scuba') and self.world and not (
                self.outing in market_visit.FLOORS or outing in market_visit.FLOORS):
            self.travel_job=Future()
            self.travel_job.set_result(self.world)
            return
        self.travel_pool=ThreadPoolExecutor(max_workers=1)
        self.travel_job=self.travel_pool.submit(build_outing,outing)

    def start_region(self,lookout_arrival=False,meadow_arrival=False):
        self.pending_outing=self.pending_sport=None
        self.meadow_arrival=meadow_arrival
        self.lookout_arrival=lookout_arrival
        self.travel_error=''
        self.travel_pool=ThreadPoolExecutor(max_workers=1)
        from pnw.river_scene_cache import summit_world
        self.travel_job=self.travel_pool.submit(summit_world)

    def return_to_valley(self):
        self.release()
        self.regional=False
        self.outing=None
        self.lookout_site=self.trip_pose=None
        self.notebook=None
        self.pixel_dirty=True

    def reset_hike(self):
        if self.travel_pool:self.travel_pool.shutdown(wait=False,cancel_futures=True)
        self.travel_pool=self.travel_job=None
        self.regional=False
        self.outing=self.pending_outing=None
        self.map_position=self.valley_pose=self.notebook=None

    def close(self):
        self.reset_hike()
        self.leave_party()
        self.release()
        self.closed=True

    def poll(self,owner):
        if self.travel_job and self.travel_job.done():
            try:world=self.travel_job.result()
            except Exception as error:
                self.travel_error=str(error)
                if self.world is None:self.error=self.travel_error
            else:
                if not self.regional:self.valley_pose=(owner.x,owner.z,owner.yaw,owner.pitch)
                if self.world is world:
                    self.bike=self.glider=self.climb=self.destination=None
                    self.stop_ski()
                else:self.release()
                self.photo_hint=''
                self.world=world
                self.regional=True
                self.lens=self.binoculars=False
                self.zoom=1.
                self.review_key=self.notebook=None
                owner.cancel_keys()
                self.needle_deck=False
                from pnw.outings import ROAD_RIDES,StreetRide
                self.road=StreetRide(self.pending_outing) if self.pending_outing in ROAD_RIDES.values() else None
                self.outing=('tacoma' if self.pending_outing.startswith('tacoma-') else 'market') if self.road else self.pending_outing
                self.lookout_site=self.meadow_site=None
                self.flower_sites=[]
                self.trip_pose=self.map_position=None
                self.cruise=self.trail.guiding=self.lens=self.binoculars=False
                if self.outing:
                    from pnw.outings import ride_pose
                    owner.x=owner.z=owner.yaw=0.
                    owner.pitch=-.08
                    self.ride_time=getattr(self,'boarding_time',0.) if self.outing=='ferry' else 0.
                    self.boarding_time=0.
                    if self.outing in market_visit.STREETS:
                        from pnw.market_life import Delivery,FishCounter
                        self.shop_target=None
                        self.delivery=Delivery()
                        self.fish_counter=FishCounter()
                    if self.outing in AIRCRAFT or self.outing in ('canoe','kayak','boat','helicopter'):
                        self.glider=regional_vehicle(self.outing,world[0])
                    elif self.outing=='hangar':
                        owner.x,owner.z=HANGAR[0],HANGAR[1]-45
                        owner.pitch=-.055
                        self.photo_hint="Walk up to a plane to board"
                        self.hint_until=self.age+6.
                    elif self.outing in AIR_SPORTS:self.glider=start_sport(self.outing,world[0])
                    elif self.outing in ('market','fishshop'):
                        from pnw.seattle_places import arcade_origin
                        from pnw.pike_market import arrival,offset,HEADING
                        owner.x,owner.z,owner.yaw,owner.pitch=arrival(arcade_origin())
                        if self.outing=='fishshop':
                            owner.x,owner.z=offset(arcade_origin(),1.,-4.)
                            owner.yaw,owner.pitch=HEADING+.16,0.
                    elif self.outing in market_visit.DESTINATIONS.values():
                        owner.x,owner.z,owner.yaw,owner.pitch=market_visit.arrival(self.outing)
                    elif self.outing=='needle':
                        from pnw.seattle_places import places
                        nx,nz=places()['Space Needle']
                        owner.x,owner.z=nx,nz-215.
                        owner.yaw,owner.pitch=0.,-.38
                    elif self.outing in ('ferry','wheel',*rail.RIDES.values()):
                        owner.x,owner.z,owner.yaw,owner.pitch,_=ride_pose(self.outing,self.ride_time)
                    if self.outing in BAYS and self.stair_landing:
                        self.glider.board(self.stair_landing)
                        self.stair_landing=None
                    if getattr(self,'stair_landing',None):
                        owner.x,owner.z,owner.yaw,owner.pitch=self.stair_landing
                        self.stair_landing=None
                else:
                    owner.x,owner.z=summit_start(world[0])
                    owner.yaw,owner.pitch=0.,-.38
                    self.meadow_site=lookout.location(world[0],paradise.LATITUDE,paradise.LONGITUDE)
                    self.flower_sites=[]
                    if self.meadow_site:
                        mx,mz=self.meadow_site
                        self.flower_sites=[(key,mx+dx,mz+dz) for key,dx,dz in paradise.patches()]
                        if self.meadow_arrival:self.visit_meadow()
                    site_xz=lookout.location(world[0])
                    if site_xz:
                        self.lookout_site=(*site_xz,lookout.base_level(lambda x,z:surface(world[0],x,z),*site_xz))
                        if self.lookout_arrival:self.visit_lookout()
                    if self.pending_sport and not self.start_mountain_sport(self.pending_sport):
                        self.notebook=ExploreMenu(self)
                    self.pending_sport=None
            finally:
                if self.travel_pool:self.travel_pool.shutdown(wait=False)
                self.travel_pool=self.travel_job=None
        if self.error:return
        if self.world is None:
            if self.travel_job:return
            if self.job is None:
                self.pool=ThreadPoolExecutor(max_workers=1)
                from pnw.river_scene_cache import valley_world
                self.job=self.pool.submit(valley_world,self.quality.high,self.plant_sites)
            if not self.job.done():return
            try:self.world=self.job.result()
            except MemoryError:
                if self.quality.auto and self.quality.high:self.quality.high=False
                else:self.error="Not enough memory for the river scene."
                return
            except Exception as error:self.error=str(error);return
            finally:self.pool.shutdown(wait=False);self.pool=self.job=None
        arriving=self.trip_pose is not None
        if self.trip_pose:
            owner.x,owner.z,owner.yaw,owner.pitch=self.trip_pose
            self.trip_pose=None
            owner.cancel_keys()
        if self.regional and self.map_position:
            self.needle_deck=False
            owner.x,owner.z=self.map_position
            owner.pitch=-.12
            self.map_position=None
        if not self.regional and self.valley_pose:
            owner.x,owner.z,owner.yaw,owner.pitch=self.valley_pose
            self.valley_pose=None
        now=owner.clock()
        dt=min(.1,max(0.,now-(self.last_tick or now)))
        if self.outing in ('ferry','wheel',*rail.RIDES.values()) and not self.notebook:
            from pnw.outings import ride_pose
            old_yaw=ride_pose(self.outing,self.ride_time)[2]
            self.ride_time+=dt
            owner.x,owner.z,heading,_,_=ride_pose(self.outing,self.ride_time)
            owner.yaw+=heading-old_yaw
        if self.road and not self.notebook:
            road=self.road
            old=(road.x,road.z)
            previous_damage=road.damage
            owner.x,owner.z,owner.yaw,owner.pitch=road.advance(dt,self.pad_sticks)
            if not road.assist:
                self.traffic.strike(road,old,self.walk_height(*old),self.vehicle_damage)
                if self.traffic.impact>.65:road.alert_patrol(self.traffic.bodies.values())
                owner.x,owner.z=road.x,road.z
            if road.patrol:
                from pnw.vehicle_impact import Body,collide
                px,pz=road.patrol
                if math.hypot(px-road.x,pz-road.z)<12:
                    sn,cs=math.sin(road.heading),math.cos(road.heading)
                    player=Body(road.x,road.z,road.heading,sn*road.speed+cs*road.slip,
                                cs*road.speed-sn*road.slip,road.spin,1500.,2.2,.95,road.damage)
                    unit=Body(px,pz,road.patrol_heading,0.,0.,0.,1800.,2.3,.98)
                    collide(player,unit)
                    road.patrol=(unit.x,unit.z)
                    road.x,road.z=owner.x,owner.z=player.x,player.z
                    road.speed,road.slip=sn*player.vx+cs*player.vz,cs*player.vx-sn*player.vz
                    road.spin,road.damage=player.spin,player.damage
            from pnw.vehicle_impact import strike_scenery
            walls=[wall for wall in (self.street_walls,self.nearby_walls) if wall]
            if walls and not road.assist:
                strike_scenery(road,old,self.walk_height,walls)
                owner.x,owner.z=road.x,road.z
            if not self.vehicle_damage:road.damage=previous_damage
            field=self.world[0]
            if self.road.bridge_roads is None:
                from pnw.seattle_places import BridgeRoads
                self.road.bridge_roads=BridgeRoads(lambda x,z:surface(field,x,z))
            self.road.bridge_roads.sample(owner.x,owner.z,surface(field,owner.x,owner.z),update=True)
        if self.bike:owner.x,owner.z,owner.yaw,owner.pitch=self.bike.advance(dt,self.walk_height)
        if any(self.pad_sticks) and not (self.road or self.bike or self.ski or self.climb or self.glider or self.notebook or self.album):
            self.walk_with_controller(owner,dt)
        if self.glider:
            owner.x,owner.z,owner.yaw,owner.pitch=self.glider.advance(dt,self.walk_height,bounds(self.world[0]))
            if self.glider.landed:
                self.glider=None
                owner.cancel_keys()
                self.photo_hint='Back on the trail'
                self.hint_until=self.age+3
        if self.climb:
            owner.x,owner.z,owner.yaw,owner.pitch=self.climb.advance(dt,self.walk_height)
        if self.ski:
            before_landing=self.ski.landings
            owner.x,owner.z,owner.yaw,owner.pitch=self.ski.advance(dt,self.walk_height)
            if self.sound and self.ski.landings>before_landing:self.landing_sound=True
        if self.destination is not None:
            self.destination=walk_to(owner,self.destination,dt,face_path=not self.trail.free_look,speed=3.2*self.pace)
            if self.destination is None and self.stair_goal:
                self.destination,self.stair_goal=self.stair_goal,None
        else:self.stair_goal=None
        if self.cruise:owner._translate(1.,0.,dt*2.5,self.cruise_heading)
        for plant,px,pz in (self.flower_sites if self.regional else self.plant_sites):
            if self.regional and not paradise.blooming(plant,self.season):continue
            if plant not in self.found_plants and (owner.x-px)**2+(owner.z-pz)**2<=2.5**2:
                from pnw.river_notebook import PLANTS,record_plant
                try:record_plant(plant)
                except OSError:continue
                self.found_plants.add(plant)
                if self.regional:
                    self.photo_hint=PLANTS[plant][0]+' in guidebook'
                    self.hint_until=self.age+2.5
        before=len(self.trail.picked)
        fed=self.trail.fed
        if not self.regional:self.trail.advance(owner,dt,local_pick=self.party is None)
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
        if not (self.glider and self.outing in AIRCRAFT):
            west,east,south,north=bounds(self.world[0])
            owner.x=max(west,min(east,owner.x));owner.z=max(south,min(north,owner.z))
        if self.outing=='needle' and self.needle_deck:
            from pnw.seattle_places import places
            nx,nz=places()['Space Needle']
            dx,dz=owner.x-nx,owner.z-nz
            radius=math.hypot(dx,dz)
            if radius<.01:dx,dz,radius=0.,1.,1.
            reach=max(18.65,min(20.9,radius))/radius
            owner.x,owner.z=nx+dx*reach,nz+dz*reach
        if self.outing in market_visit.FLOORS:
            owner.x,owner.z=market_visit.walk_inside(self.outing,owner.x,owner.z)
            target=market_visit.stair_exit(self.outing,owner.x,owner.z)
            if target and not self.travel_job:
                landing=(1. if owner.x<0 else -1.,-4.6,0.,-.03)
                if target=='market':
                    from pnw.pike_market import offset,HEADING
                    from pnw.seattle_places import arcade_origin
                    landing=(*offset(arcade_origin(),-8,1.8),HEADING+math.pi,0.)
                self.cruise=False;self.destination=None
                self.start_outing(target,landing)
        elif self.outing in market_visit.STREETS and not self.travel_job and not self.road:
            from pnw.pike_market import offset
            from pnw.seattle_places import arcade_origin
            from pnw.outings import CROSSING,DOCK_TIME
            for terminal,side in (('colman',1),('bainbridge',-1)):
                cx,cz=market_visit.site(terminal)
                if abs(owner.x-(cx+side*3))<2.5 and abs(owner.z-cz)<3.:
                    self.boarding_time=0. if side==1 else CROSSING+DOCK_TIME
                    self.cruise=False;self.destination=None
                    self.start_outing('ferry')
                    break
            stair=offset(arcade_origin(),-8,5.5)
            if math.hypot(owner.x-stair[0],owner.z-stair[1])<1.05:
                self.cruise=False;self.destination=None
                self.start_outing('down5',(-1.,-4.6,0.,0.))
        if self.outing in market_visit.STREETS:
            cx,cz=market_visit.site('gum')
            if abs(owner.x-cx)<2.55 and cz-16<=owner.z<=cz+15:owner.x=max(cx-2.1,min(cx+2.1,owner.x))
        if self.on_city_foot():
            if self.walk_bridges is None:
                from pnw.seattle_places import BridgeRoads
                self.walk_bridges=BridgeRoads(lambda u,v:surface(self.world[0],u,v))
            if self.camera and not arriving and math.dist(self.camera[:2],(owner.x,owner.z))<8:
                from pnw.vehicle_impact import walk_past_obstacles
                layers=[w for w in (self.street_walls,self.nearby_walls) if w]
                owner.x,owner.z=walk_past_obstacles(self.camera[:2],(owner.x,owner.z),self.walk_height,layers)
            self.walk_bridges.sample(owner.x,owner.z,surface(self.world[0],owner.x,owner.z),update=True)
            owner.x,owner.z=self.traffic.separate_walker(owner.x,owner.z,self.walk_height(owner.x,owner.z))
        camera=(owner.x,owner.z,owner.yaw,owner.pitch)
        age=owner.clock()-owner.started-owner.paused_total
        if self.fishing.state!='idle':
            if self.regional or math.dist(camera[:2],TROUT_POOL)>12:self.fishing.state='idle'
            else:
                self.update_fishing(age)
        if self.camera!=camera or age-self.age>=1/20:
            step=math.dist(camera[:2],self.camera[:2]) if self.camera else 0.
            elapsed=age-self.age
            self.avatar_pose=12.5
            if not self.road and 0.<step<4. and elapsed>0.:
                running=step/elapsed>2.5
                self.gait_phase=(self.gait_phase+12*step/(2.3 if running else 1.10))%12
                self.avatar_pose=self.gait_phase+(20 if running else 0)
            self.camera=camera;self.age=age;self.pixel_dirty=True

    def walk_height(self,x,z):
        if self.outing in market_visit.FLOORS:return market_visit.stairs(self.outing,x,z)
        if self.outing=='needle' and self.needle_deck:
            from pnw.seattle_places import DECK_HEIGHT,places
            return surface(self.world[0],*places()['Space Needle'])+DECK_HEIGHT
        if self.road:
            ground=surface(self.world[0],x,z)
            if self.road.bridge_roads and self.road.bridge_roads.deck is not None:
                return self.road.bridge_roads.sample(x,z,ground)
        if self.on_city_foot() and self.walk_bridges and self.walk_bridges.deck is not None:
            bed=surface(self.world[0],x,z)
            return self.walk_bridges.sample(x,z,bed)
        if self.outing in market_visit.STREETS:
            from pnw.pike_market import floor_height
            from pnw.seattle_places import arcade_origin
            terrain=lambda px,pz:surface(self.world[0],px,pz)
            cx,cz=market_visit.site('overlook')
            if abs(x-cx)<=6 and -38<=z-cz<=20:return market_visit.deck_height(terrain,x,z)
            return floor_height(arcade_origin(),terrain,x,z)
        for slot in sorted(self.flight_surfaces):
            patch=self.flight_surfaces[slot]
            west,east,south,north=bounds(patch)
            if west<=x<=east and south<=z<=north:return surface(patch,x,z)
        if self.outing in AIRCRAFT:
            west,east,south,north=bounds(self.world[0])
            if not (west<=x<=east and south<=z<=north):return 0.
        terrain=surface(self.world[0],x,z)
        return terrain if self.regional else valley_floor()[1].height(x,z,terrain)

    def eye_position(self,x,z):
        field,origin=self.world[:2]
        ground=self.walk_height(x+origin.x,z+origin.z)
        if self.regional and self.lookout_site:
            cx,cz,base=self.lookout_site
            if max(abs(x-cx),abs(z-cz))<=3.2:ground=base+lookout.DECK
            elif abs(x-cx)<=.7 and -7.4<=z-cz<-3.2:
                bottom=surface(field,cx,cz-7.4)
                step=min(14,int((z-cz+7.4)/.3)+1)
                ground=bottom+(base+lookout.DECK-bottom)*step/14
        if self.outing in ('ferry','wheel',*rail.RIDES.values()):
            from pnw.outings import ride_pose
            ground+=ride_pose(self.outing,self.ride_time)[4]
        if self.glider:ground=self.glider.altitude
        if getattr(self,"ski",None):ground+=self.ski.lift
        return x,ground-origin.y+1.25,z

    def draw_rainier(self,ctx):
        self.pixel_dirty=False
        paused=isinstance(self.notebook,PauseMenu)
        book=isinstance(self.notebook,DiscoveryBook)
        if self.world is None or self.camera is None or (self.notebook and not paused and not book and not isinstance(self.notebook,(ReliefMap,market_visit.DistrictMap))):return ()
        field,origin,data,terrain_count,indices,spans,base_count,shadows=self.world
        self.quality.frame(self.age)
        high=self.quality.high and not self.regional
        x,z,yaw,pitch=self.camera
        _,eye,_=self.eye_position(x,z)
        wx,wy,w,h=self.host.bounds(self.host.window(self.name))
        ox,oy=self.host.origin
        rect=((wx+ox+1)*8,(wy+oy+1)*16,(w-2)*8,(h-3)*16)
        if min(rect[2:])<1:return ()
        if isinstance(self.notebook,(ReliefMap,market_visit.DistrictMap)):
            self.notebook.draw(ctx,rect)
            return rect
        def print_photo(path,frame):
            w=h=0;rgb=None
            if path!=self.album_loaded:
                try:w,h,rgb=read_photo(path)
                except (OSError,ValueError,zlib.error,struct.error):
                    if book:self.notebook.damaged.add(path)
                    elif self.album:
                        self.album.pop(self.album_index)
                        if self.album:self.album_index%=len(self.album)
                    return
            display=ctx.lib.pocket_scene_river_photo
            display.argtypes=[C.c_void_p]+[C.c_int]*6+[C.c_void_p]
            ctx.check(display(ctx.handle,*frame,w,h,rgb))
            self.album_loaded=path
        if self.album:
            print_photo(self.album[self.album_index],rect)
            ink=Ink(ctx,rect)
            for _,label,box in album_tools(w-2,h-3):ink.button(box,label)
            return rect
        draw=ctx.lib.pocket_scene_rainier
        self.subjects=[]
        self.frame_camera=((x,eye,z,yaw,pitch),rect[2]/rect[3])
        optics=(*self.frame_camera,self.zoom) if self.binoculars or self.lens else None
        daylight=(1.,.43,.04,.52+.48*math.cos(self.age*math.tau/720))[self.time_mode]
        hatch=self.weather==0 and self.season in (0,3) and daylight>.35
        fly=self.fishing.position(self.age)
        chasing=(*fly[:2],self.age-self.fishing.bite) if self.fishing.state in ('bite','fight','landed') else None
        if self.regional:commands=summit_dancers(self.climb,field,origin,spans)
        else:commands=encounters(field,origin,spans,self.age,self.trail.fed,(x,z),self.subjects,optics,hatch,chasing,self.fishing.target,self.fishing.kept_brook)
        if self.road:
            sound=ctx.lib.pocket_scene_road_sound
            sound.argtypes=[C.c_void_p,C.c_int,C.c_float,C.c_int,C.c_float,C.c_int]
            sound(ctx.handle,self.sound and not paused,self.road.speed,
                  (4 if self.road.actor_kind==18 else int(self.road.kind in ('sports-car','car','motorcycle')))+2*int(self.road.siren),getattr(self,'traffic_gain',0.),(-round(100*self.traffic.impact) if self.traffic.impact else self.traffic.horn))
            self.traffic.impact=0.
            self.traffic.horn=False
        elif self.regional:
            speed=self.ski.speed/28. if self.ski else 0.
            wind=.46+.15*self.weather+.30*speed
            if self.glider:wind+=.21+.06*abs(self.glider.bank)
            skis=0.
            if self.ski and self.ski.mode=='ski' and self.ski.air_y is None:
                skis=math.sqrt(speed)*(.65+.45*abs(math.sin(self.ski.angle)))
            sound=ctx.lib.pocket_scene_summit_sound
            sound.argtypes=[C.c_void_p,C.c_int,C.c_float,C.c_float,C.c_int]
            sound(ctx.handle,self.sound and not paused,wind,skis,self.landing_sound)
            self.landing_sound=False
        else:
            voices=nearby_calls(self.subjects,x,eye,z)
            voice=0
            if self.sound and self.age>=self.next_call and voices:
                key,voice,_=next((v for v in voices if v[0]>self.last_caller),voices[0])
                self.last_caller=key
                self.next_call=self.age+4.5+.3*voice
            gain=next((gain for key,_,gain in voices if key==self.last_caller),0.)
            sound=ctx.lib.pocket_scene_river_sound
            sound.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_float,C.c_int,C.c_float]
            sound(ctx.handle,self.sound and not paused,self.cue,river_gain(x,z,site()[1]),voice,gain)
        self.cue=0
        draw.argtypes=[C.c_void_p]+[C.c_int]*4+[C.c_void_p,C.c_uint,C.c_uint,C.c_void_p,
                       C.c_uint,C.POINTER(AnimalDraw),C.c_uint]+[C.c_float]*6+[C.c_int,C.c_float,C.c_int,C.c_int,C.c_void_p,C.POINTER(C.c_float),C.c_uint,C.POINTER(C.c_float),C.POINTER(C.c_float),C.c_int,C.c_void_p,C.c_int,C.c_float,C.c_int,C.c_int,C.c_int,C.c_float,C.c_float,C.c_float,C.c_float,C.c_float,C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_uint,C.POINTER(C.c_float),C.POINTER(C.c_float),C.c_uint]
        target_x,target_z=self.trail.target(x,z)
        direction=math.atan2(target_x-x,target_z-z)-yaw
        mask=sum(1<<i for i,p in enumerate(BUSHES) if p in self.trail.picked)
        if self.upload:self.counts=len(data)//7,len(indices)
        hikers=[]
        if self.party:
            for uid,(px,pz) in self.party.roster.items():
                if uid!=self.party.ident:
                    hx,hz=px/10,pz/10
                    hikers.extend((hx,self.walk_height(hx+origin.x,hz+origin.z)-origin.y,hz))
        if self.ski and self.ski.room:
            for hx,hz in self.ski.family_positions():
                hikers.extend((hx,self.walk_height(hx,hz)-origin.y,hz))
        hikers_buffer=(C.c_float*len(hikers))(*hikers)
        marker=(C.c_float*3)() if self.destination is not None else None
        if marker is not None:
            mx,mz=self.destination
            marker[:]=mx,self.walk_height(mx+origin.x,mz+origin.z)-origin.y+.07,mz
        fish=next(((fx,fz) for key,fx,_,fz,_ in self.subjects if key=='trout'),None)
        ripple=None
        if fish:
            fx,fz=fish
            level=channel().water_height(fx,fz)
            if level is not None:ripple=(C.c_float*3)(fx,level-origin.y+.035,fz)
        pixels=(C.c_ubyte*(3*rect[2]*rect[3]))() if self.shutter else None
        # Compose the keepsake from the player's real eye position. A short
        # telephoto view gives small birds and insects enough pixels to see.
        focal=self.zoom if self.lens or self.binoculars else 1.
        if self.climb and self.climb.raised and self.climb.panorama and not self.climb.dancing:focal=2.5
        spotting=self.subjects
        if self.binoculars and not self.regional:
            spotting=self.subjects+[(f'Berries {i+1}',bx,surface(field,bx,bz)-origin.y+.48,bz,1.2)
                for i,(bx,bz) in enumerate(BUSHES) if (bx,bz) not in self.trail.picked]
        if self.lens or self.binoculars:
            self.focus_key=sighting(self.frame_camera[0],.5,.5,self.frame_camera[1],spotting,
                lambda px,pz:surface(field,px+origin.x,pz+origin.z)-origin.y,zoom=focal,tracked=self.focus_key)
        focus=self.shutter
        for key,fx,fy,fz,size in self.subjects:
            if key!=focus:continue
            dx,dz=fx-x,fz-z
            horizontal=math.hypot(dx,dz)
            yaw=math.atan2(dx,dz)
            pitch=math.atan2(eye-fy,horizontal)
            focal=max(focal,min(12.,horizontal*min(1.,rect[2]/rect[3])/(size*2.8)))
            break
        photo_index=next((i for i,p in enumerate(self.subjects) if p[0]==self.shutter),-1)
        sun_angle=(.64,-.82,.64,.64-self.age*math.tau/720)[self.time_mode]
        center=(0,0)
        stand_ptr=None
        upload_shade=self.upload
        sound_region=self.outing is not None and self.outing!='hoh'
        if self.upload:
            lamps=None
            if sound_region and self.outing not in (*market_visit.FLOORS,'scuba'):
                from pnw.seattle_places import arcade_origin
                from pnw.pike_market import offset
                from pathlib import Path
                upload=ctx.lib.pocket_scene_vehicle_mesh
                upload.argtypes=[C.c_void_p,C.c_uint,C.POINTER(C.c_uint),C.c_char_p,C.c_uint]
                for slot,model in enumerate(('coupe','delivery-van','transit-bus','tractor-trailer','sedan','crossover','patrol','pickup','electric','motorbike')):
                    mesh=zlib.decompress((Path(__file__).resolve().parents[1]/'assets/seattle'/(model+'.zlib')).read_bytes())
                    groups=(C.c_uint*29).from_buffer_copy(mesh)
                    ctx.check(upload(ctx.handle,slot,groups,mesh[116:],(len(mesh)-116)//24))
                materials=zlib.decompress((Path(__file__).resolve().parents[1]/'assets/seattle/materials.rgba.zlib').read_bytes())
                upload=ctx.lib.pocket_scene_market_materials
                upload.argtypes=[C.c_void_p,C.c_char_p,C.c_uint]
                if upload(ctx.handle,materials,len(materials)):raise RuntimeError('Market surface texture upload failed')
                sx,sz=offset(arcade_origin(),0,-1.45)
                spots=[(sx,surface(field,*arcade_origin())+4.25,sz),*market_visit.alley_lamps(lambda x,z:surface(field,x,z))]
                lamps=(C.c_float*12)(*(v for px,py,pz in spots for v in (px-origin.x,py-origin.y,pz-origin.z)))
            lights=ctx.lib.pocket_scene_market_lights
            lights.argtypes=[C.c_void_p,C.POINTER(C.c_float),C.c_int]
            lights.restype=None
            lights(ctx.handle,lamps,int(bool(lamps) and self.quality.high))
        if sound_region and self.outing!='scuba' and self.outing not in market_visit.FLOORS:
            from pnw.terrain import FlightHorizon,FlightImagery,PATCH_STEP
            if self.flight_imagery is None:self.flight_imagery=FlightImagery()
            patch=self.flight_imagery.update(x,z,field,self.ground_source)
            if self.flight_horizon is None:self.flight_horizon=FlightHorizon()
            setting=self.horizon_range if self.outing in AIRCRAFT and self.ground_source=='Aerial' else 'Local'
            if self.road and self.ground_source=='Aerial':setting='Street'
            low_flight=(self.outing in AIRCRAFT and self.ground_source=='Aerial' and
                        eye+origin.y-self.walk_height(x,z)<600)
            removed,distant=self.flight_horizon.update(x,z,field,setting,low_flight)
            if removed:
                drop=ctx.lib.pocket_scene_drop_flight_photo
                drop.argtypes=[C.c_void_p,C.c_uint]
                for slot in removed:
                    ctx.check(drop(ctx.handle,slot))
                    self.flight_surfaces.pop(slot,None)
            for tile in (patch,distant):
                if tile is None:continue
                slot,(ix,iz),rgb,(heights,mesh)=tile
                upload=ctx.lib.pocket_scene_flight_photo
                upload.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_char_p,C.c_float,C.c_float,C.c_float,C.c_void_p,C.c_uint]
                width=self.flight_horizon.resident[slot][1] if tile is distant else 2*PATCH_STEP
                ctx.check(upload(ctx.handle,slot,math.isqrt(len(rgb)//3),rgb,ix*PATCH_STEP,iz*PATCH_STEP,width,mesh.buffer_info()[0],len(mesh)//7))
                self.flight_surfaces[slot]=heights
                if self.neighborhood and slot==0:self.neighborhood.cell=None
        if sound_region and self.outing not in (*market_visit.FLOORS,'scuba'):
            from pnw.regional_scenery import Neighborhood
            if self.neighborhood is None:self.neighborhood=Neighborhood()
            from pnw.vehicle_impact import StreetObstacles
            if self.upload:self.street_walls=StreetObstacles(data,terrain_count)
            stand=self.neighborhood.update(x,z,lambda px,pz:surface(field,px,pz))
            if stand is not None:
                from pnw.outings import StreetRide
                slots=self.neighborhood.parking
                self.parked_cars[:]=[car for car in self.parked_cars if getattr(car,'garage_slot',None) is None
                                     or car.garage_slot in slots]
                occupied={getattr(car,'garage_slot',None) for car in self.parked_cars}
                for slot,(u,v) in slots.items():
                    if slot in occupied or slot in self.garage_taken:continue
                    car=StreetRide('car')
                    car.x,car.z,car.heading,car.chase_heading=u,v,0.,0.
                    car.actor_kind=14 if slot[2]%3 else 15
                    car.paint=(slot[0]+slot[2])%5
                    car.garage_slot=slot
                    self.parked_cars.append(car)
                self.nearby_walls=StreetObstacles(stand,len(stand)//7)
                stand_ptr=stand.buffer_info()[0];self.stand_count=len(stand)//7
        if sound_region:center=((field.nx-1)*field.dx,(field.nz-1)*field.dz)
        if self.regional and self.outing in (None,'hoh'):
            center=self.stand_center
            if center is None or max(abs(x-center[0]),abs(z-center[1]))>64:
                center=(96*round(x/96),96*round(z/96))
            if center!=self.stand_center or self.upload:
                stand,shadows=regional_stand(field,origin.y,*center,surface,self.lookout_site,self.meadow_site)
                stand_ptr=stand.buffer_info()[0]
                self.stand_count=len(stand)//7
                self.stand_center=center
                upload_shade=True
        omit_first=omit_end=0
        if self.regional and base_count<terrain_count:
            from pnw import summit_approach
            patch=field.inset.inset
            west,east,south,north=bounds(patch)
            near=math.hypot(max(west-x,0.,x-east),max(south-z,0.,z-north))<600.
            if near:omit_first,omit_end=base_count-6*summit_approach.COLUMNS*summit_approach.ROWS,base_count
            else:omit_first,omit_end=base_count,terrain_count
        equipment=None
        if self.glider:
            mode={'kayak':19,'canoe':18,'helicopter':17,'scuba':15,'boat':3,'jet':9,'hangar-jet':9,'skydive':int(getattr(self.glider,'open',False))*10,'balloon':11}.get(self.outing,2 if self.outing in AIRCRAFT else self.glider.powered)
            equipment_pitch=-self.glider.elevation/.40 if self.outing in AIRCRAFT else self.glider.pitch
            if mode in (18,19):equipment_pitch=self.glider.stroke
            if self.outing!='skydive' or mode:equipment=(C.c_float*3)(mode,self.glider.bank,equipment_pitch)
        if self.glider and self.outing in AIRCRAFT:
            from pnw.cockpit import panel
            jet=self.outing in ('jet','hangar-jet')
            setup=ctx.lib.pocket_scene_cockpit
            setup.argtypes=[C.c_void_p,C.c_void_p,C.c_float,C.c_float]
            pixels=panel(jet) if self.cockpit_kind!=jet else None
            ctx.check(setup(ctx.handle,pixels,self.glider.speed,self.glider.altitude))
            self.cockpit_kind=jet
            if jet:equipment=(C.c_float*5)(mode,self.glider.bank,equipment_pitch,self.glider.heading,self.glider.throttle)
            look=ctx.lib.pocket_scene_cockpit_look
            look.argtypes=[C.c_void_p,C.c_float,C.c_float]
            look.restype=None
            look(ctx.handle,self.glider.look_yaw,self.glider.look_pitch)
        if self.outing and getattr(self,'market_snack',None) and not equipment and not (self.lens or self.binoculars):
            if self.market_snack in ('coffee','piroshky'):
                mesh=market_visit.held_item(self.market_snack)
                setup=ctx.lib.pocket_scene_snack
                setup.argtypes=[C.c_void_p,C.c_uint,C.c_void_p,C.c_uint]
                ctx.check(setup(ctx.handle,int(self.market_snack=='piroshky'),mesh.buffer_info()[0],len(mesh)//6))
            equipment=(C.c_float*3)({'coffee':5,'piroshky':6,'flowers':7,'honey':8}[self.market_snack],0.,0.)
        if self.road:equipment=(C.c_float*3)({'car':12,'motorcycle':13,'bicycle':14,'sports-car':12,'scooter':16}[self.road.kind] if self.road.actor_kind!=19 else 13,self.road.steer,self.road.speed)
        if self.outing=='ferry':equipment=(C.c_float*3)(4,0.,0.)
        market=None
        actor_count=0
        poses=[]
        ground=self.walk_height
        if self.outing in market_visit.STREETS and not self.needle_deck:
            from pnw.market_life import plaza_walkers,street_walkers
            from pnw.seattle_places import places
            if math.dist((x,z),places()['Pike Place Fish Market'])<120:
                from pnw.market_life import actors
                poses=actors(self.age,self.walk_height,self.fish_counter.advance(self.age))
                van=self.delivery.advance(self.age,(x,z),poses,self.walk_height)
                if van and not self.road:poses.append(van)
            for terminal,side in (('colman',1),('bainbridge',-1)):
                cx,cz=market_visit.site(terminal)
                if math.hypot(x-cx,z-cz)<520:
                    px=cx-side*43
                    poses.append((8,px,ground(px,cz),cz,90.,0.,0.))
            poses.extend(street_walkers(self.age,ground,x,z))
            nx,nz=places()['Space Needle']
            if math.hypot(x-nx,z-(nz-183))<140:
                poses.extend(plaza_walkers(self.age,ground))
        elif self.outing in market_visit.FLOORS:
            from pnw.market_life import stroll
            for i,lane in enumerate((-4.4,-1.55,1.55,4.4)):
                dx,dz,heading,gait,identity=stroll(self.outing,i,self.age,8.)
                poses.append((0,lane+dx,0.,dz,math.degrees(heading),gait,identity))
        actor_limit=96
        self.traffic_gain=0.
        if sound_region and self.outing not in (*market_visit.FLOORS,'scuba'):
            altitude=max(0.,eye+origin.y-ground(x,z))
            radius=400. if self.outing not in AIRCRAFT else min(2400.,650.+altitude)
            if altitude<4000.:
                from pnw.seattle_places import BridgeRoads
                from pnw.vehicle_impact import Body
                terrain=lambda u,v:surface(field,u,v)
                if self.traffic_bridges is None:self.traffic_bridges=BridgeRoads(terrain)
                def lane_height(u,v,heading):
                    return self.traffic_bridges.lane_height(u,v,heading,terrain(u,v))
                stationary=[]
                for parked in self.parked_cars:
                    if math.hypot(parked.x-x,parked.z-z)>radius:continue
                    py=terrain(parked.x,parked.z)
                    if parked.bridge_roads:py=parked.bridge_roads.sample(parked.x,parked.z,py)
                    stationary.append(Body(parked.x,parked.z,parked.heading,0,0,0,1500,
                                           {11:5.8,12:7.8}.get(parked.actor_kind,2.2),1.,elevation=py))
                pedestrian=Body(x,z,yaw,0,0,0,75,.32,.32,elevation=ground(x,z)) if self.on_city_foot() else None
                signals=[]
                from pnw.seattle_places import service_frontage
                if self.neighborhood:
                    for lx,lz in sorted(self.neighborhood.signals,key=lambda p:math.dist((x,z),p))[:16]:
                        if math.hypot(lx-x,lz-z)>230:break
                        (u,v),(nx,nz)=service_frontage((lx,lz))
                        bearing=math.atan2(nz,-nx)
                        red=(int(self.age+int(lx/90)+int(lz/90))%32)>=16
                        signals.append((lx,lz,bearing,red,terrain(lx,lz)))
                        poses.append((16,u+nx*.7,terrain(u,v),v+nz*.7,math.degrees(bearing),float(red),0))
                cars=self.traffic.update(x,z,self.age,radius,self.road,lane_height,stationary,pedestrian,signals)
                for distance,px,pz,angle,index,braking,turn in cars[:max(0,actor_limit-2-len(poses))]:
                    self.traffic_gain=max(self.traffic_gain,1./(1.+distance/12.)**2)
                    lamps=int(braking)+2*int(daylight<.65 or bool(self.weather))
                    if turn==2:lamps+=16
                    if (self.age+index*.17)% .78<.39:lamps+=12 if turn==2 else 4 if turn<0 else 8 if turn>0 else 0
                    from pnw.traffic import vehicle_type
                    kind=vehicle_type(index)
                    poses.append((kind,px,lane_height(px,pz,angle)+.06,pz,
                                  math.degrees(angle),-1. if kind==9 else float(lamps+32*(kind==19)),1+index%4+32*int(distance>100)))
        if sound_region and self.outing not in market_visit.FLOORS:
            reserved=[]
            for car in sorted(self.parked_cars,key=lambda car:math.hypot(car.x-x,car.z-z))[:8]:
                if math.hypot(car.x-x,car.z-z)<350:
                    y=ground(car.x,car.z)
                    if car.bridge_roads:y=car.bridge_roads.sample(car.x,car.z,y)
                    reserved.append((car.actor_kind,car.x,y+.05,car.z,math.degrees(car.heading),
                                  -1. if car.actor_kind==9 else 16*int(car.damage>.35),car.paint))
            poses=poses[:actor_limit-2-len(reserved)]+reserved
        patrol=self.road or self.patrol_owner
        if sound_region and patrol and patrol.patrol and math.dist((x,z),patrol.patrol)<240:
            px,pz=patrol.patrol
            flash=self.age%1 if patrol.pursuit=='following' else -1.
            poses.append((9,px,ground(px,pz),pz,math.degrees(patrol.patrol_heading),flash,0))
        if self.road and self.road.kind!='sports-car' and len(poses)<actor_limit:
            from pnw.market_life import shopper,BOUQUET
            rx,rz=self.road.route[-1]
            if math.hypot(x-rx,z-rz)<120:
                identity=shopper('flower delivery',0)|(BOUQUET if self.road.delivered else 0)
                poses.append((0,rx+1.8,ground(rx+1.8,rz),rz,225.,12.5,identity))
        camera_x,camera_z=x,z
        if self.road and self.road.overhead:
            equipment=None
            player=(self.road.actor_kind,x,ground(x,z)+.05,z,math.degrees(yaw),2.*int(daylight<.65 or bool(self.weather))+16*int(self.road.damage>.35)+32*int(self.road.actor_kind==19),self.road.paint)
            if self.road.actor_kind==9:player=(*player[:5],self.age%1 if self.road.siren else -1.,player[6])
            poses=poses[:actor_limit-1]+[player]
            yaw=self.road.chase_heading
            length,height={12:(15.6,4.1),11:(11.6,3.4),5:(4.5,2.35)}.get(self.road.actor_kind,(4.4,1.45))
            pullback=length*.85+3.7+min(abs(self.road.speed)*.065,3.6)
            camera_x=x-pullback*math.sin(yaw)
            camera_z=z-pullback*math.cos(yaw)
            target=ground(x,z)-origin.y
            eye=max(ground(camera_x,camera_z)-origin.y+1.2,target+height+1.65+pullback*.12)
            pitch=math.atan2(eye-target-height*.48,pullback+length*.65)
        if self.regional and self.outing is None and self.parked_bike:
            bx,bz,bh,_=self.parked_bike.advance(0.,ground)
            if math.hypot(x-bx,z-bz)<140:
                poses=poses[:actor_limit-1]+[(13,bx,ground(bx,bz)-origin.y,bz,math.degrees(bh),0.,0.)]
        if self.third_person and not (self.road or self.glider or self.lens or self.binoculars or self.shutter
                                      or self.outing in ('ferry','wheel',*rail.RIDES.values())):
            foot=ground(x,z)-origin.y
            if self.bike:poses=poses[:actor_limit-2]+[(13,x,foot,z,math.degrees(yaw),0.,0.)]
            poses=poses[:actor_limit-1]+[(0,x,foot+(.25 if self.bike else 0),z,math.degrees(yaw),
                               self.avatar_pose,2)]
            camera_x=x-4.2*math.sin(yaw)
            camera_z=z-4.2*math.cos(yaw)
            eye=max(foot+2.35,ground(camera_x,camera_z)-origin.y+1.1)
            pitch=math.atan2(eye-foot-1.,5.2)
        if poses:
            actor_count=len(poses)
            packed=[]
            for pose in poses:
                slopes=(0.,0.)
                if pose[0] in (5,9,10,11,12,14,17,18,19,15):
                    px,py,pz=pose[1:4]
                    angle=math.radians(pose[4])
                    sn,cs=math.sin(angle),math.cos(angle)
                    heights=[]
                    for d in (-1.,1.):
                        u,v=px+d*sn,pz+d*cs
                        bed=surface(field,u,v)
                        # Continue the surface under this axle only when it is
                        # close to the vehicle's actual elevation.
                        deck=self.traffic_bridges.lane_height(u,v,angle,bed) if self.traffic_bridges else bed
                        heights.append(min((bed,deck),key=lambda h:abs(h-py)))
                    grade=(heights[1]-heights[0])*.5
                    slopes=(grade*sn,grade*cs)
                packed.extend((*pose,*slopes))
            market=(C.c_float*len(packed))(*packed)
        needed=set(range(min(2,len(hikers)//3)))
        if actor_count:needed.update(int(p[6])%2 if p[0]==0 else 0 for p in poses if p[0]<=1)
        if needed-self.person_slots:
            from pathlib import Path
            upload=ctx.lib.pocket_scene_market_person
            upload.argtypes=[C.c_void_p,C.c_uint,C.c_void_p,C.c_uint]
            for slot in sorted(needed-self.person_slots):
                name=('sam','maya')[slot]
                mesh=zlib.decompress((Path(__file__).resolve().parents[1]/f'assets/people/{name}.zlib').read_bytes())
                ctx.check(upload(ctx.handle,slot,mesh,len(mesh)))
                del mesh
                self.person_slots.add(slot)
        result=draw(ctx.handle,*rect,data.buffer_info()[0] if self.upload else None,self.counts[0],terrain_count if high or self.regional else base_count,
                       indices.buffer_info()[0] if self.upload else None,self.counts[1],commands,len(commands),
                       camera_x,eye,camera_z,yaw,pitch,self.age,mask,direction,self.trail.fed,high,
                       C.addressof(C.c_ubyte.from_buffer(shadows)) if upload_shade and shadows is not None else None,hikers_buffer,len(hikers)//3,marker,ripple,-2 if sound_region else -1 if self.regional else int(self.lens or self.binoculars),pixels,photo_index,focal, ((1+int(self.story) if self.tent else 0)+4*self.supplies+32*int(self.camp_built)) if not self.regional else 0,self.season,self.weather,origin.y,daylight,sun_angle,*center,stand_ptr,self.stand_count if self.regional else 0,0 if self.regional else 6*(len(channel().rows)-1),omit_first,omit_end,equipment,market,actor_count)
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
            from pnw.wildlife_models import NAMES
            try:
                species=self.shutter.split('#')[0]
                save_photo(species,rect[2],rect[3],bytes(pixels))
                self.photo_hint=NAMES[species];self.review_key=self.shutter;self.cue=1
            except OSError:self.photo_hint='Save failed'
            self.hint_until=self.age+2.
            self.shutter=None
        if self.upload:self.world=field,origin,None,terrain_count,None,spans,base_count,None
        self.upload=False
        ink=Ink(ctx,rect)
        if paused:self.notebook.draw(ink,w-2,h-3)
        elif book:
            def picture(path,box):
                bx,by,bw,bh=box
                print_photo(path,(rect[0]+bx*8,rect[1]+by*16,bw*8,bh*16))
            draw_book(ink,self.notebook,w-2,h-3,picture)
        else:
            if fly and not self.regional and not (self.binoculars or self.lens):
                fx,fz,_=fly
                fy=channel().water_height(fx,fz)
                point=project_subject(self.frame_camera[0],self.frame_camera[1],1.,('',fx,fy-origin.y+.03,fz,.3))
                if point:
                    u,v,_=point
                    rod=ctx.lib.pocket_scene_fishing_rod
                    rod.argtypes=[C.c_void_p]+[C.c_int]*4+[C.c_float]*3
                    bend=min(1.,self.fishing.tension+(.32 if self.fishing.pulling(self.age) else 0.))
                    ctx.check(rod(ctx.handle,*rect,u,v,bend))
                if self.fishing.state=='fight':
                    ink.label(1,6,'Fish running - ease line' if self.fishing.pulling(self.age) else 'Fish resting - reel',0xFFF6DA)
                    ink.label(1,7,f'Reeled {round(100*(1-self.fishing.remaining))}%   Tension',0xFFF6DA)
                    ink.fill((1,8.1,18,.36),0x283832FF)
                    ink.fill((1,8.1,18*self.fishing.tension,.36),0xFD996EFF)
            if self.outing in market_visit.DESTINATIONS.values():
                label=next(k for k,v in market_visit.DESTINATIONS.items() if v==self.outing)
                if self.outing in market_visit.FLOORS and z>3:
                    label=market_visit.FLOORS[self.outing][int(x>0)]
                if self.outing in market_visit.STREETS and self.shop_target:
                    from pnw.seattle_places import bearing_label
                    label=bearing_label(self.shop_target,x,z)
                ink.label(1,h-5,label,0xFFF6DD)
            if self.outing in rail.RIDES.values():
                ink.label(1,1,rail.sample(self.outing,self.ride_time)[1],0xFFEDBF)
            if self.outing=='ferry':
                from pnw.outings import ferry_stop
                dock=ferry_stop(self.ride_time)
                if dock:ink.label(1,4,'Colman Dock' if dock=='colman' else 'Bainbridge Island',0xFFF6DD)
            if not self.road and self.outing in ('ferry','wheel','market','fishshop','needle','hoh'):
                place={'ferry':'Seattle – Bainbridge ferry','wheel':'Pier 57 · Great Wheel','market':'Pike Place Market','fishshop':'Pike Place Fish Market','needle':'Space Needle','hoh':'Hoh Rain Forest'}
                label=place[self.outing]
                if self.outing=='market':
                    from pnw.street_map import neighborhood
                    label=neighborhood(math.floor(x/32),math.floor(z/32))
                if self.outing in ('market','fishshop'):
                    from pnw.seattle_places import market_shops
                    distance,name=min((math.dist((x,z),point),name) for name,point in market_shops().items())
                    if distance<=18:label=name
                    if self.shop_target:
                        from pnw.seattle_places import bearing_label
                        label=bearing_label(self.shop_target,x,z)
                ink.label(1,h-7 if self.outing in ('market','fishshop') else h-5,label,0xFFF6DD)
            if self.on_city_foot() or self.road:
                from pnw.street_map import coordinates,neighborhood
                area=neighborhood(math.floor(x/32),math.floor(z/32))
                lat,lon=coordinates(x,z)
                ink.label(1,4,f'{area}  {lat:.4f}, {lon:.4f}'[:w-4],0xEEE8CC)
            if sound_region and patrol and patrol.patrol and patrol.pursuit in ('following','Traffic stop'):
                label='* WANTED - POLICE PURSUIT' if patrol.pursuit=='following' else '* WANTED - TRAFFIC STOP'
                ink.label(1,3,label[:w-4],0xFFD15A)
            if self.road:
                ink.label(1,1,self.road.hint(),0xFFEDBF)
                if self.road.actor_kind==9:
                    label='Traffic stop active' if self.road.stop_target is not None else 'Siren on' if self.road.siren else 'J: siren   K: stop car ahead'
                    ink.label(1,4,label,0xFFEDBF)
                self.road.draw_minimap(ink,w-2,h-3)
                if self.neighborhood and abs(self.road.speed)<12:
                    place=self.neighborhood.nearby(x,z)
                    if place:ink.label(1,2,place[:w-4],0xEEE8CC)
            if self.glider:self.glider.draw(ink,w-2,h-3)
            if self.climb:self.climb.draw(ink,w-2,h-3)
            if self.ski:self.ski.draw(ink,w-2,h-3,*self.frame_camera,lambda px,pz:self.walk_height(px,pz)-origin.y)
            for action,label,box in self.walk_tools(w-2,h-3):
                if self.glider and self.glider.menu:
                    bx,by,bw,bh=box
                    ink.label(bx+(bw-len(label))/2,by+(bh-1)/2,label,0xFFF6DA)
                else:ink.button(box,label)
                if self.ski and action=='brake':
                    bx,by,bw,bh=box
                    if self.ski.mode=='ski':
                        for offset in (.7,1.6):ink.fill((bx+offset,by+bh/2-.6,.55,1.2),0xFFE3AAFF)
                    else:
                        for i in range(4):ink.fill((bx+.7+i*.3,by+bh/2-.6+i*.12,.32,1.2-i*.24),0xD3EDD5FF)
            if self.age<self.hint_until and self.photo_hint:
                ink.label(1,5,self.photo_hint[:w-2],0xFFF6DA)
            elif (self.lens or self.binoculars) and self.focus_key:
                from pnw.wildlife_models import NAMES
                subject=next(s for s in spotting if s[0]==self.focus_key)
                u,v,_=project_subject(self.frame_camera[0],self.frame_camera[1],self.zoom,subject)
                cx=max(1.2,min(w-3.2,u*(w-2)))
                cy=max(.8,min(h-3.8,v*(h-3)))
                for offset in (-1.,1.):
                    ink.fill((cx+offset,cy-.36,.16,.72),0xFFE6A4FF)
                label=NAMES.get(self.focus_key.split('#')[0],self.focus_key)[:w-4]
                ink.fill((1,5,len(label)+1,1.2),0x1E352CDB)
                ink.label(1.5,5,label,0xFFF6DA)
            if self.gathering and not self.regional and not self.camp_built:
                remaining=[(name,px,pz) for i,(name,px,pz) in enumerate(SUPPLIES) if not self.supplies & (1<<i)]
                name,px,pz=min(remaining,key=lambda item:math.hypot(item[1]-x,item[2]-z)) if remaining else ('Camp',*CAMP)
                dist=math.hypot(px-x,pz-z)
                angle=math.atan2(px-x,pz-z)-self.camera[2]
                bearing=('ahead','right','behind','left')[round(angle/(math.pi/2))%4]
                tip=f'{name.capitalize()}  {dist:.0f} m {bearing}'
                ink.fill((1,7,len(tip)+1,1.3),0x254137EE)
                ink.label(1.5,7,tip,0xFFF6DA)
            if self.debug_overlay:
                place='Summit' if self.regional else 'Ohanapecosh'
                lines=(f'{place}  t={self.age:.1f}s',f'E {x:+.1f}  N {z:+.1f} m',
                       f'Elev {eye+origin.y-1.25:.1f} m',f'Heading {round(math.degrees(self.camera[2]))%360:03d}  Pitch {math.degrees(self.camera[3]):+.0f}')
                top=max(1,h-11)
                ink.fill((.5,top-.15,min(w-3,max(map(len,lines))+1),4.3),0x10251EF0)
                for row,line in enumerate(lines):ink.label(1,top+row,line[:w-4],0xFFF6DA)
        self.pixel_jobs+=1;self.pixel_frames+=1
        return rect
