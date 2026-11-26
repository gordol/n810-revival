"""Perspective terrain for the graphical Rainier walk. World coordinates are metres."""
from array import array
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import ctypes as C
import math
import random
import struct
import zlib

from geometry import Vec, cross, sub, unit
import fremont_lookout as lookout
import paradise_meadow as paradise
from river_channel import TROUT_POOL
from river_camp import CAMP, OVERLOOK, SUPPLIES, camp_materials, campsite, river_stones
from river_detail import RiverQuality, shade_tree
from forest_floor import blade, broadleaf_clump, fern, snag, spruce_sprays, trail_cover
from rainier_habitat import forest_sites,regional_stand,ridge_grass,understory
from rainier_hike import HikeMenu, ReliefMap, bounds, region_field, summit_start
from valley_map import ValleyMap
from river_fishing import Fishing,vibration,watch_rod
from river_party import PartyMenu
from river_overlay import Ink, album_tools, draw_book, hit, tools as river_tools
from river_notebook import DiscoveryBook
from river_explore import DIPPER_ROCK, OTTER_POOL, bank_sign, ground_target, project_subject, read_photo, save_photo, sighting, walk_to
from pnw_species import PERCH_FLIGHT, REGIONAL, group
from river_walk import BERRY_BLUFF, BUSHES, FOX, BerryTrail, blueberry_patch, centerline_distances_sq, channel, nearby_calls, river_gain, site, wet
from river_walk import hiking_paths, hiking_segments, trail_surface
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
    from river_channel import RiverFloor
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


def append_animals(vertices,high=False):
    """Store each (vertex, material) once per pose, sharing indices across poses."""
    from wildlife_models import FOX_ASSETS, FOX_FRAMES, pose
    indices=array('I')
    spans=[]
    models={}
    for key,x,z,scale in ENCOUNTERS:
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


def build_world(high=True,plant_sites=None,regional=False):
    field,segments=(region_field(),()) if regional else (valley_floor()[0],site()[1])
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
        for p in (a,b,c):target.extend((p.x-origin.x,p.y-origin.y,p.z-origin.z,*rgb,material))

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
            from summit_ski import COURSES,RAMP_LENGTH,LIP_HEIGHT,HALF_WIDTH
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
            from summit_ski import GATES,location
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
        return field,origin,triangles,count,array('I',[0]),(),base_count,None

    rng=random.Random(3918)
    branch_rng=random.Random(911)
    def pine(x,z,h,near):
        nonlocal target
        y=surface(field,x,z)-.14
        def ring(height,radius,angle,count):
            return [Vec(x+math.cos(angle+i*math.tau/count)*radius,y+height,
                        z+math.sin(angle+i*math.tau/count)*radius) for i in range(count)]
        sides=(12 if high else 5) if near else 3
        radius=h*(.017 if h>=25 else .022)
        bottom=ring(0,radius*1.4,0,sides)
        shoulder=ring(min(2.,h*.13),radius,0,sides) if near else None
        top=ring(h*.88,radius*.30,0,sides)
        trunk=((bottom,shoulder),(shoulder,top)) if shoulder else ((bottom,top),)
        for i in range(sides):
            j=(i+1)%sides
            for lo,hi in trunk:
                face(lo[i],hi[i],lo[j],(106,85,66),.48)
                face(lo[j],hi[i],hi[j],(106,85,66),.48)
        shade=rng.uniform(.82,1.13)
        layers=rng.choice((5,7)) if near else 3
        needles=rng.choice(((37,75,58),(52,91,66),(64,98,76),(48,82,76)))
        breadth=rng.uniform(.8,1.24)*(.70 if h>=25 else 1.)
        crown_base=.33 if h>=25 else .16
        tips=(20 if high else 10) if near else 5
        lean_x,lean_z=(rng.uniform(-.085,.085)*h for _ in range(2))
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
            for i,p in enumerate(crown):
                face(apex,p,crown[(i+1)%tips],tuple(v*shade*(.78+.23*t) for v in needles))
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
        if plant_sites is not None and math.hypot(dx,dz)<70:plant_sites.append(("conifer",dx,dz))
        shade_tree(shadows,dx,dz,h,texel=2)
        pine(origin.x+dx,origin.z+dz,h,near)
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
    name='Rainier walk'
    paces=(('Walk',1.),('Brisk',2.),('Explore',8.))

    @property
    def pace_name(self):return self.paces[self.pace_index][0]

    @property
    def pace(self):return self.paces[self.pace_index][1]

    def __init__(self,host):
        self.host=host
        self.ski=None
        self.quality=RiverQuality()
        self.pace_index=0
        self.regional=False
        self.valley_pose=self.map_position=None
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
            footer=f'{NAMES.get(key,key)}   {self.album_index+1}/{len(self.album)}'
            return ('',)*max(0,self.host.window(self.name).h-3)+(footer,)
        trail=self.trail
        if trail.fed:hint=f'Again ({self.hearts})'
        elif len(trail.picked)==3:hint='3/3 | Feed fox'
        else:hint=f'Berries {len(trail.picked)}/3'
        family='Family'
        if self.party:family=f'{len(self.party.roster)} here' if self.party.roster else 'Finding'
        labels=('Stop' if self.cruise else 'Walk',hint,'Hike',family,'Mute' if self.sound else 'Sound')
        if self.regional:
            field=self.world[0]
            elevation=round(surface(field,*self.camera[:2])) if self.camera else 0
            labels=(labels[0],f'{elevation} m','Hike',self.pace_name,'Map')
        width=self.host.window(self.name).w-2
        bounds=[0,width//6,width*3//7,width*4//7,width*3//4,width]
        footer=''.join(label.center(b-a)[:b-a] for label,a,b in zip(labels,bounds,bounds[1:]))
        return ('',)*max(0,self.host.window(self.name).h-3)+(footer,)

    def footer(self,x,width):
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
            self.notebook=HikeMenu(self)
        elif x>=width*3//4:self.sound=not self.sound
        elif x>=width*4//7:
            self.destination=None
            self.notebook=PartyMenu(self)
            self.trail.guiding=self.cruise=False
        else:return self.guide()
        return True

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
            if not hit(box,x,y):continue
            if self.ski:
                if action=='leave':self.stop_ski()
                else:self.ski.action(action)
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
            elif action=='fish':self.fish()
            elif action=='keep':
                self.fishing.keep()
                self.photo_hint=self.fishing.note
                self.hint_until=self.age+2.
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
            elif action=='book':
                self.destination=None
                self.cruise=self.trail.guiding=False
                self.notebook=DiscoveryBook(self)
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
            elif self.frame_camera:
                self.shutter=self.focus_key
                if not self.shutter:self.photo_hint='Aim at wildlife';self.hint_until=self.age+2.
            self.pixel_dirty=True
            return True
        if self.ski:return True
        if self.frame_camera is None:return False
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

    def start_ski(self):
        from summit_ski import COURSES,SkiRun,start_tilt
        self.ski=SkiRun(COURSES if getattr(self.world[0].inset,"inset",None) else COURSES[1:])
        self.ski.tilt=start_tilt()
        self.cruise=self.binoculars=self.lens=False
        self.destination=self.trip_pose=None
        self.zoom=1.

    def stop_ski(self):
        if self.ski and self.ski.tilt:self.ski.tilt.stop.set()
        self.ski=None

    def release(self):
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
                from river_notebook import record_catch
                try:record_catch(self.fishing.target)
                except OSError:self.photo_hint+=' - guidebook save failed'
                else:self.photo_hint+=' - in guidebook'
                self.hint_until=age+4.

    def fish(self):
        pulse=self.fishing.tap(self.age,self.camera[:2])
        if pulse:vibration(pulse)
        self.photo_hint=self.fishing.note
        self.hint_until=self.age+2.

    def walk_tools(self,width,height):
        if self.ski:return self.ski.controls(width,height)
        buttons=river_tools(width,height,self.lens,self.binoculars,self.zoom,self.regional)
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

    def start_region(self,lookout_arrival=False,meadow_arrival=False):
        self.meadow_arrival=meadow_arrival
        self.lookout_arrival=lookout_arrival
        self.travel_error=''
        self.travel_pool=ThreadPoolExecutor(max_workers=1)
        self.travel_job=self.travel_pool.submit(build_world,False,None,True)

    def return_to_valley(self):
        self.release()
        self.regional=False
        self.lookout_site=self.trip_pose=None
        self.notebook=None
        self.pixel_dirty=True

    def reset_hike(self):
        if self.travel_pool:self.travel_pool.shutdown(wait=False,cancel_futures=True)
        self.travel_pool=self.travel_job=None
        self.regional=False
        self.map_position=self.valley_pose=self.notebook=None

    def close(self):
        self.reset_hike()
        self.leave_party()
        self.release()
        self.closed=True

    def poll(self,owner):
        if self.travel_job and self.travel_job.done():
            try:world=self.travel_job.result()
            except Exception as error:self.travel_error=str(error)
            else:
                self.valley_pose=(owner.x,owner.z,owner.yaw,owner.pitch)
                self.release()
                self.world=world
                self.regional=True
                self.lens=self.binoculars=False
                self.zoom=1.
                self.review_key=self.notebook=None
                owner.cancel_keys()
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
            finally:
                self.travel_pool.shutdown(wait=False)
                self.travel_pool=self.travel_job=None
        if self.error:return
        if self.world is None:
            if self.job is None:
                self.pool=ThreadPoolExecutor(max_workers=1)
                from river_scene_cache import valley_world
                self.job=self.pool.submit(valley_world,self.quality.high,self.plant_sites)
            if not self.job.done():return
            try:self.world=self.job.result()
            except MemoryError:
                if self.quality.auto and self.quality.high:self.quality.high=False
                else:self.error="Not enough memory for the river scene."
                return
            except Exception as error:self.error=str(error);return
            finally:self.pool.shutdown(wait=False);self.pool=self.job=None
        if self.trip_pose:
            owner.x,owner.z,owner.yaw,owner.pitch=self.trip_pose
            self.trip_pose=None
            owner.cancel_keys()
        if self.regional and self.map_position:
            owner.x,owner.z=self.map_position
            owner.pitch=-.12
            self.map_position=None
        if not self.regional and self.valley_pose:
            owner.x,owner.z,owner.yaw,owner.pitch=self.valley_pose
            self.valley_pose=None
        now=owner.clock()
        dt=min(.1,max(0.,now-(self.last_tick or now)))
        if self.ski:owner.x,owner.z,owner.yaw,owner.pitch=self.ski.advance(dt,self.walk_height)
        if self.destination is not None:self.destination=walk_to(owner,self.destination,dt,face_path=not self.trail.free_look,speed=3.2*self.pace)
        if self.cruise:owner._translate(1.,0.,dt*2.5,self.cruise_heading)
        for plant,px,pz in (self.flower_sites if self.regional else self.plant_sites):
            if self.regional and not paradise.blooming(plant,self.season):continue
            if plant not in self.found_plants and (owner.x-px)**2+(owner.z-pz)**2<=2.5**2:
                from river_notebook import PLANTS,record_plant
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
        west,east,south,north=bounds(self.world[0])
        owner.x=max(west,min(east,owner.x));owner.z=max(south,min(north,owner.z))
        camera=(owner.x,owner.z,owner.yaw,owner.pitch)
        age=owner.clock()-owner.started-owner.paused_total
        if self.fishing.state!='idle':
            if self.regional or math.dist(camera[:2],TROUT_POOL)>12:self.fishing.state='idle'
            else:
                self.update_fishing(age)
        if self.camera!=camera or age-self.age>=1/20:
            self.camera=camera;self.age=age;self.pixel_dirty=True

    def walk_height(self,x,z):
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
        if getattr(self,"ski",None):ground+=self.ski.lift
        return x,ground-origin.y+1.25,z

    def draw_rainier(self,ctx):
        self.pixel_dirty=False
        book=isinstance(self.notebook,DiscoveryBook)
        if self.world is None or self.camera is None or (self.notebook and not book and not isinstance(self.notebook,ReliefMap)):return ()
        field,origin,data,terrain_count,indices,spans,base_count,shadows=self.world
        self.quality.frame(self.age)
        high=self.quality.high and not self.regional
        x,z,yaw,pitch=self.camera
        _,eye,_=self.eye_position(x,z)
        wx,wy,w,h=self.host.bounds(self.host.window(self.name))
        ox,oy=self.host.origin
        rect=((wx+ox+1)*8,(wy+oy+1)*16,(w-2)*8,(h-3)*16)
        if min(rect[2:])<1:return ()
        if isinstance(self.notebook,ReliefMap):
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
        commands=encounters(field,origin,spans,self.age,self.trail.fed,(x,z),self.subjects,optics,hatch,chasing,self.fishing.target,self.fishing.kept_brook)
        voices=nearby_calls(self.subjects,x,eye,z)
        voice=0
        if self.sound and self.age>=self.next_call and voices:
            key,voice,_=next((v for v in voices if v[0]>self.last_caller),voices[0])
            self.last_caller=key
            self.next_call=self.age+4.5+.3*voice
        gain=next((gain for key,_,gain in voices if key==self.last_caller),0.)
        sound=ctx.lib.pocket_scene_river_sound
        sound.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_float,C.c_int,C.c_float]
        sound(ctx.handle,self.sound and not self.regional,self.cue,river_gain(x,z,site()[1]),voice,gain)
        self.cue=0
        draw.argtypes=[C.c_void_p]+[C.c_int]*4+[C.c_void_p,C.c_uint,C.c_uint,C.c_void_p,
                       C.c_uint,C.POINTER(AnimalDraw),C.c_uint]+[C.c_float]*6+[C.c_int,C.c_float,C.c_int,C.c_int,C.c_void_p,C.POINTER(C.c_float),C.c_uint,C.POINTER(C.c_float),C.POINTER(C.c_float),C.c_int,C.c_void_p,C.c_int,C.c_float,C.c_int,C.c_int,C.c_int,C.c_float,C.c_float,C.c_float,C.c_float,C.c_float,C.c_void_p,C.c_uint,C.c_uint,C.c_uint,C.c_uint]
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
        if self.regional:
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
            import summit_approach
            patch=field.inset.inset
            west,east,south,north=bounds(patch)
            near=math.hypot(max(west-x,0.,x-east),max(south-z,0.,z-north))<600.
            if near:omit_first,omit_end=base_count-6*summit_approach.COLUMNS*summit_approach.ROWS,base_count
            else:omit_first,omit_end=base_count,terrain_count
        result=draw(ctx.handle,*rect,data.buffer_info()[0] if self.upload else None,self.counts[0],terrain_count if high or self.regional else base_count,
                       indices.buffer_info()[0] if self.upload else None,self.counts[1],commands,len(commands),
                       x,eye,z,yaw,pitch,self.age,mask,direction,self.trail.fed,high,
                       C.addressof(C.c_ubyte.from_buffer(shadows)) if upload_shade and shadows is not None else None,hikers_buffer,len(hikers)//3,marker,ripple,-1 if self.regional else int(self.lens or self.binoculars),pixels,photo_index,focal, ((1+int(self.story) if self.tent else 0)+4*self.supplies+32*int(self.camp_built)) if not self.regional else 0,self.season,self.weather,origin.y,daylight,sun_angle,*center,stand_ptr,self.stand_count if self.regional else 0,0 if self.regional else 6*(len(channel().rows)-1),omit_first,omit_end)
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
                species=self.shutter.split('#')[0]
                save_photo(species,rect[2],rect[3],bytes(pixels))
                self.photo_hint=NAMES[species];self.review_key=self.shutter;self.cue=1
            except OSError:self.photo_hint='Save failed'
            self.hint_until=self.age+2.
            self.shutter=None
        if self.upload:self.world=field,origin,None,terrain_count,None,spans,base_count,None
        self.upload=False
        ink=Ink(ctx,rect)
        if book:
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
            if self.ski:self.ski.draw(ink,w-2,h-3,*self.frame_camera,lambda px,pz:self.walk_height(px,pz)-origin.y)
            for _,label,box in self.walk_tools(w-2,h-3):ink.button(box,label)
            if self.age<self.hint_until and self.photo_hint:
                ink.label(1,5,self.photo_hint[:w-2],0xFFF6DA)
            elif (self.lens or self.binoculars) and self.focus_key:
                from wildlife_models import NAMES
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
