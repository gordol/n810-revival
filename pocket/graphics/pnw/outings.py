"""Regional travel, aircraft, and scenes for Pacific Northwest outings."""
from array import array
from dataclasses import dataclass
from functools import lru_cache
from pnw.units import mph, feet, road_distance
import math
from collections import deque
import random
from struct import Struct

from pnw import market_visit, rail
from pnw.terrain import GRIDS,elevations,layout,location,sound_aerial
from pnw.hiking import HangGlider,HikeMenu

_VERTEX = Struct('=7f')

PLACES=(('Thun Field',47.104,-122.287),('Tacoma waterfront',47.266,-122.449),
        ('Tacoma Narrows Airport',47.268,-122.578),('Seattle waterfront',47.604,-122.339),
        ('Rainier',46.852,-121.760),('Sea-Tac Airport',47.4502,-122.3093),
        ('Tacoma Dome',47.2367,-122.4267))
BAY=(47.295,-122.435)
@dataclass(frozen=True)
class Aircraft:
    approach: float  # m/s
    maximum: float
    stall: float
    cruise_power: float
    roll_rate: float  # degrees/second
    pitch_rate: float  # degrees/second
    spool_time: float  # seconds
    brakes: float  # m/s²


TRAINER=Aircraft(32.,150.,25.,48./118.,95.,32.,1.,4.)
RESEARCH_JET=Aircraft(65.,420.,50.,.60,135.,46.,4.,8.)
AIRCRAFT={'plane':TRAINER,'thun':TRAINER,'jet':RESEARCH_JET,'hangar-jet':RESEARCH_JET}

HANGAR=location('sound',PLACES[0][1],PLACES[0][2])
HANGAR=(HANGAR[0]+70.,HANGAR[1])
BAYS={'thun':(-8.,'Trainer'),'hangar-jet':(8.,'Research jet')}
AIR_SPORTS=('skydive','balloon','scuba')
OUTINGS={'Thun Field hangar':'hangar','Skydive over Rainier':'skydive','Balloon over the Sound':'balloon','Plane from Rainier':'plane','Plane from Thun Field':'thun','Research jet from Rainier':'jet',
         'Boat on Commencement Bay':'boat','Puget Sound kelp dive':'scuba','Hoh Rain Forest walk':'hoh','Bainbridge ferry':'ferry','Seattle Great Wheel':'wheel',
         'Pike Place Market':'market','Fish counter':'fishshop','Space Needle':'needle'}

ROAD_RIDES={'Market delivery car':'car','Market motorcycle':'motorcycle','Market bicycle':'bicycle'}
ROAD_RIDES.update({f'Tacoma {kind}':f'tacoma-{kind}' for kind in ('car','motorcycle','bicycle')})
ROAD_RIDES.update({'Market rental scooter':'scooter','Sports car to Tacoma':'sports-car'})
OUTINGS.update(ROAD_RIDES)
OUTINGS.update(rail.RIDES)
OUTINGS.update(market_visit.DESTINATIONS)

WHEEL=(47.6062,-122.3425)
# Seattle and Bainbridge landings and Eagle Harbor bends, OSM way 332476322.
FERRY=tuple(location('sound',*p) for p in (
    (47.6028952, -122.3398411),(47.6028572, -122.3408157),(47.6028536, -122.3411992),
    (47.6028717, -122.3417062),(47.6027487, -122.3567748),(47.6024883, -122.3667527),
    (47.6033274, -122.3921586),(47.6049478, -122.438078),(47.6068719, -122.4718523),
    (47.6073349, -122.4835253),(47.6076821, -122.4864006),(47.608391, -122.4891043),
    (47.609447, -122.4908209),(47.6106622, -122.4920011),(47.6131647, -122.4933958),
    (47.6160867, -122.4949622),(47.6176488, -122.4959064),(47.6194423, -122.4973655),
    (47.620339, -122.4990392),(47.6208887, -122.5012279),(47.6217448, -122.5069982),
    (47.6219853, -122.508332),(47.6221412, -122.5095054),
))
FERRY_LEGS=tuple((a,b,math.dist(a,b)) for a,b in zip(FERRY,FERRY[1:]))
CROSSING=sum(length for _,_,length in FERRY_LEGS)/45.
DOCK_TIME=15.

def ferry_stop(elapsed):
    t=elapsed%(2*(CROSSING+DOCK_TIME))
    if t<DOCK_TIME:return 'colman'
    if CROSSING+DOCK_TIME<=t<CROSSING+2*DOCK_TIME:return 'bainbridge'
    return None

def runway_geometry():
    # Threshold coordinates and widths from OurAirports runways.csv.
    for a,b,width in (((47.108898,-122.287003),(47.098918,-122.287278),18.29),
                      ((47.2747,-122.577004),(47.261135,-122.579335),30.48),
                      ((47.463799,-122.310997),(47.438,-122.310997),45.72),
                      ((47.463799,-122.307999),(47.431198,-122.307999),45.72),
                      ((47.463799,-122.318001),(47.440498,-122.318001),45.72)):
        x,z=location('sound',*a)
        ex,ez=location('sound',*b)
        yield x,z,math.atan2(ex-x,ez-z),math.hypot(ex-x,ez-z),width

@lru_cache(maxsize=1)
def taxi_path():
    hx,hz=HANGAR
    rx,rz,yaw,_,width=next(runway_geometry())
    tx,tz=rx+45*math.sin(yaw),rz+45*math.cos(yaw)
    return ((hx,hz-12),(hx,hz-34),(hx+25,hz-55),(hx+25,tz-28),
            (hx+13,tz),(tx+width,tz),(tx,tz))

def ride_pose(outing,elapsed):
    if outing in rail.RIDES.values():return rail.sample(outing,elapsed)[0]
    if outing=='wheel':
        x,z=location('sound',*WHEEL)
        phase=elapsed*math.tau/100.
        return x,z+23*math.sin(phase),1.45,-.04,4+23*(1-math.cos(phase))
    phase=elapsed%(2*(CROSSING+DOCK_TIME))
    returning=phase>=CROSSING+DOCK_TIME
    t=phase-(CROSSING+DOCK_TIME) if returning else phase
    distance=max(0.,min(CROSSING,t-DOCK_TIME))
    along=45*(CROSSING-distance if returning else distance)
    for (x,z),(ex,ez),d in FERRY_LEGS:
        if along<=d:
            t=along/d
            return x+(ex-x)*t,z+(ez-z)*t,math.atan2(ex-x,ez-z)+math.pi*returning,.015,5.
        along-=d
    return *FERRY[-1],0.,0.,5.

def dive_world():
    """A small illustrative kelp bed, in local metres below the waterline."""
    from geometry import Vec,HeightField
    origin=Vec(-48,0,-48)
    heights=tuple(-11+1.4*math.sin(i*.42)+2*math.cos(j*.24+i*.13)
                  for j in range(33) for i in range(33))
    field=HeightField(33,33,origin,3.,3.,heights,'meters')
    mesh=array('f')
    def quad(a,b,c,d,color):
        for p in (a,b,c,a,c,d):mesh.extend((*p,*color,0.))
    def ground(i,j):return (-48+3*i,heights[j*33+i],-48+3*j)
    rng=random.Random(403)
    for j in range(32):
        for i in range(32):
            shade=rng.uniform(.85,1.)
            quad(ground(i,j),ground(i,j+1),ground(i+1,j+1),ground(i+1,j),
                 (.31*shade,.33*shade,.25*shade))
    for _ in range(220):
        x,z=rng.uniform(-46,46),rng.uniform(-46,46)
        y=field.height(x,z)
        length=rng.uniform(2,min(8,-y-.5));phase=rng.uniform(0,math.tau)
        for k in range(8):
            bottom=y+length*k/8;top=bottom+length/8
            a=x+.23*math.sin(phase+k*.5);b=x+.23*math.sin(phase+(k+1)*.5)
            quad((a-.035,bottom,z),(a+.035,bottom,z),(b+.035,top,z),(b-.035,top,z),(.29,.33,.12))
            dx=math.cos(phase+k)*.95;dz=math.sin(phase+k)*.95
            quad((b,top,z),(b+dx*.5,top+.23,z+dz*.5),(b+dx,top+.36,z+dz),
                 (b+dx*.5,top-.03,z+dz*.5),(.20,.32+.012*k,.10))
    count=len(mesh)//7
    return field,Vec(0,0,0),mesh,count,array('I',[0]),(),count,None

def build_world(outing,*,require_cache=False,prepare=False):
    from geometry import Vec
    from pnw.summit_detail import RegionalTerrain
    if outing=='scuba':return dive_world()
    region='hoh' if outing=='hoh' else 'sound'
    if outing in market_visit.FLOORS:return market_visit.indoor(outing,prepare=prepare)
    raw=elevations(region)
    _,_,_,_,nx,nz=GRIDS[region]
    _,_,d=layout(region)
    field=RegionalTerrain(nx,nz,Vec(-(nx//2)*d,0,-(nz//2)*d),d,d,tuple(max(0,v) for v in raw),'meters')
    aerial=sound_aerial() if region=='sound' else None
    from pnw.river_scene_cache import regional_mesh
    mesh=regional_mesh(region,raw,aerial is not None,lambda:build_mesh(region,field,raw,aerial),require_cache=require_cache,prepare=prepare)
    if prepare:return aerial is not None
    count=len(mesh)//7
    return field,Vec(0,0,0),mesh,count,array('I',[0]),(),count,aerial

def build_mesh(region,field,raw,aerial):
    mesh = terrain_grid_mesh(field, raw, aerial, region)
    if region=='sound':
        from pnw.scene import surface
        def quad(points,color,material=0.):
            a,b,c,d = (_VERTEX.pack(*point,*color,material) for point in points)
            mesh.frombytes(a+b+c if c==d else a+b+c+a+c+d)
        def box(x,z,y,width,depth,height,color,material=0.,rotation=None):
            base=[(x+sx*width/2,y,z+sz*depth/2) for sx,sz in ((-1,-1),(1,-1),(1,1),(-1,1))]
            if rotation:
                c,s=rotation
                base=[(x+c*(px-x)-s*(pz-z),y,z+s*(px-x)+c*(pz-z)) for px,_,pz in base]
            top=[(px,y+height,pz) for px,_,pz in base]
            quad(top,color)
            for i in range(4):
                j=(i+1)%4
                shade=(.78,.91,.84,.69)[i]
                quad((base[i],base[j],top[j],top[i]),tuple(c*shade for c in color),material)
        hx,hz=HANGAR
        grey=(.54,.58,.58)
        for dx in (-17.,17.):box(hx+dx,hz,surface(field,hx+dx,hz)-1,.3,23,9,grey)
        box(hx,hz+11,surface(field,hx,hz+11)-1,34,.3,9,grey)
        floor=surface(field,hx,hz)
        # An open portal, pitched metal roof and exposed transverse frames.
        for side in (-1,1):
            edge=hx+side*17.5
            quad(((edge,floor+7.8,hz-12),(edge,floor+7.8,hz+12),
                  (hx,floor+10.5,hz+12),(hx,floor+10.5,hz-12)),(.38,.44,.46))
        for dz in (-11.,-4.,4.,11.):
            box(hx,hz+dz,floor+7.5,34,.20,.24,(.38,.27,.18))
            for dx in (-14.,-7.,0.,7.,14.):
                roof=10.4-abs(dx)*.155
                box(hx+dx,hz+dz,floor+7.7,.11,.14,roof-7.7,(.44,.32,.21))
            box(hx,hz+dz,floor+7.4,2.8,.34,.10,(.99,.92,.70))
        for dx in range(-14,16,4):
            box(hx+dx,hz+10.76,floor+3.8,2.9,.1,1.35,(.53,.66,.68))
        quad(tuple((hx+dx,surface(field,hx+dx,hz+dz)+.05,hz+dz)
                   for dx,dz in ((-17,-16),(17,-16),(17,11),(-17,11))),(.43,.44,.43))
        for kind,(dx,_) in BAYS.items():
            parked_start=len(mesh)
            # Parked silhouettes: a swept jet and a straight high-wing trainer.
            x=hx+dx
            y=surface(field,x,hz)+1.3
            jet=kind=='hangar-jet'
            color=(.65,.69,.72) if jet else (.85,.80,.65)
            rings=[]
            for zz,r in ((-5.4,.035),(-2,.67),(0,.8),(2.3,.58),(5.2,.14)):
                rings.append([(x+r*math.cos(k*math.tau/12),y+r*math.sin(k*math.tau/12),hz+zz) for k in range(12)])
            for a,b in zip(rings,rings[1:]):
                for k in range(12):
                    shade=.76+.24*math.sin((k-.5)*math.tau/12)
                    quad((a[k-1],a[k],b[k],b[k-1]),tuple(c*shade for c in color))
            for side in (-1,1):
                tip=side*(5.5 if jet else 6.)
                yy=y+(.1 if jet else .68)
                sweep=2.2 if jet else -.65
                quad(((x,yy,hz-1.6),(x+tip,yy,hz+sweep),(x+tip,yy,hz+sweep+.68),(x,yy,hz+1.6)),color)
                quad(((x,y,hz+3.),(x+side*2.4,y,hz+4.),(x+side*2.2,y,hz+4.65),(x,y,hz+4.6)),color)
                box(x+side,hz+.6,y-1.4,.25,.65,.62,(.09,.10,.11))
            quad(((x,y,hz+2.5),(x,y+2.1,hz+4.3),(x,y+2.0,hz+4.8),(x,y,hz+4.8)),(.21,.37,.47))
            box(x,hz-1.1,y+.45,.97,1.65,.43,(.19,.31,.36))
            if not jet:
                box(x,hz-5.4,y-.95,.13,.12,1.9,(.16,.18,.19))
                box(x,hz-5.42,y-.11,.14,.14,.22,(.91,.59,.21))
            # Tag the parked airframe so the cockpit camera can occupy its bay.
            for vertex in range(parked_start+6,len(mesh),7):mesh[vertex]=.311 if jet else .310
        # Vertical metal siding, sliding door tracks and maintenance benches.
        for side in (-1,1):
            for dz in range(-11,12):
                box(hx+side*16.76,hz+dz,floor,.12,.10,7.7,(.42,.47,.48))
            box(hx+side*13,hz-11.8,floor+7.75,8,.25,.28,(.21,.23,.23))
            box(hx+side*13,hz+8.4,floor,4.,1.1,.93,(.20,.28,.29))
            box(hx+side*13,hz+8.4,floor+.93,4.2,1.25,.09,(.50,.48,.42))
        # Reconstructed apron and taxiway; the runway threshold is georeferenced.
        for (x,z),(ex,ez) in zip(taxi_path(),taxi_path()[1:]):
            length=math.hypot(ex-x,ez-z)
            dx,dz=(ex-x)/length,(ez-z)/length
            for begin in range(0,math.ceil(length),6):
                end=min(begin+6,length)
                for width,offset,color in ((6.,.075,(.32,.33,.32)),(.095,.10,(.91,.73,.18))):
                    corners=[]
                    for t,side in ((begin,-1),(begin,1),(end,1),(end,-1)):
                        px,pz=x+t*dx+side*width*dz,z+t*dz-side*width*dx
                        corners.append((px,surface(field,px,pz)+offset,pz))
                    quad(corners,color)
        # Game scenery at named locations. Runway paint follows the sampled terrain.
        for x,z,a,length,width in runway_geometry():
            def strip(width,start,end,color,lift):
                for side,t in ((-1,start),(1,start),(-1,end),(-1,end),(1,start),(1,end)):
                    xx=x+t*math.sin(a)+side*width*math.cos(a)
                    zz=z+t*math.cos(a)-side*width*math.sin(a)
                    mesh.extend((xx,surface(field,xx,zz)+lift,zz,*color,0.))
            for t in range(0,math.ceil(length),25):
                strip(width/2,t,min(length,t+25),(.19,.20,.21),.14)
                if t%50==0:strip(.65,t,min(length,t+15),(.94,.93,.80),.18)
        from pnw.seattle_places import sound_landmarks
        sound_landmarks(lambda x,z:surface(field,x,z),quad,box)
        rail.mesh(lambda x,z:surface(field,x,z),quad,box)
        from pnw.seattle_places import waterfront_piers
        waterfront_piers(lambda x,z:surface(field,x,z),quad)
        x,z=location('sound',*WHEEL)
        base=field.height(x,z)+27
        # Two rims, axle braces and radial spokes facing Elliott Bay.
        def beam(a,b,width,color):
            dx,dy,dz=(v-u for u,v in zip(a,b))
            length=math.hypot(dy,dz) or 1.
            uy,uz=width*dz/length,-width*dy/length
            for point,side in ((a,-1),(a,1),(b,-1),(b,-1),(a,1),(b,1)):
                mesh.extend((point[0],point[1]+side*uy,point[2]+side*uz,*color,0.))
        for side in (-1,1):
            xx=x+side*2.
            for j in range(48):
                a=j*math.tau/48;b=(j+1)*math.tau/48
                tip=(xx,base+24*math.cos(a),z+24*math.sin(a))
                beam(tip,(xx,base+24*math.cos(b),z+24*math.sin(b)),.45,(.89,.89,.84))
                if j%2==0:beam((xx,base,z),tip,.13,(.70,.76,.78))
            for foot in (-1,1):beam((xx,base-26,z+foot*10),(xx,base,z),.65,(.42,.48,.51))
        for j in range(32):
            a=j*math.tau/32
            zz=z+24*math.sin(a)
            y=base+24*math.cos(a)-2.4
            box(x,zz,y,3.8,2.3,1.15,(.80,.83,.81))
            box(x,zz,y+1.15,3.5,2.,1.05,(.24,.38,.45))
            box(x,zz,y+2.2,3.8,2.3,.18,(.84,.85,.80))
        from pnw import pike_market
        from pnw.seattle_places import arcade_origin,bridge_mesh,buildings,roadside_trees,space_needle,streets
        def ground(x,z):return surface(field,x,z)
        pike_market.build(arcade_origin(),ground,quad)
        streets(ground,quad,field)
        from pnw.seattle_places import corridor_path
        last_lamp=-100.
        for start,x,z,dx,dz,length,_,kind,width in corridor_path()[0]:
            spacing=95. if kind=='freeway' else 43.
            at=max(start,last_lamp+spacing)
            while at<start+length:
                px=x+dx*(at-start)+dz*(width+.65)
                pz=z+dz*(at-start)-dx*(width+.65)
                py=ground(px,pz)
                box(px,pz,py,.16,.16,7.2,(.38,.41,.42))
                box(px-dz*.65,pz+dx*.65,py+7.15,.13,1.55,.13,(.40,.43,.44),rotation=(dx,-dz))
                box(px-dz*1.35,pz+dx*1.35,py+7.04,.54,.42,.12,(.98,.84,.59),.247)
                last_lamp=at;at+=spacing
        bridge_mesh(ground,quad,box)
        roadside_trees(ground,quad)
        buildings(ground,quad)
        space_needle(ground,quad)
        market_visit.outdoor(ground,quad,box)
    else:
        from pnw.forest_floor import broadleaf_clump,nurse_log,fern
        rng=random.Random(47861)
        def face(a,b,c,color,material=0.):
            materials=material if isinstance(material,tuple) else (material,)*3
            for v,m in zip((a,b,c),materials):
                mesh.extend((v.x,v.y,v.z,*(k/255 for k in color),m))
        # Clumps within the opening sightline give the rainforest a middle
        # storey. Keep an irregular gap through the centre for the walker.
        for _ in range(85):
            z=rng.uniform(-15,40)
            x=rng.choice((-1,1))*rng.uniform(1.8,18)+1.15*math.sin(z*.22)
            y=field.height(x,z)
            if rng.random()<.67:fern(x,z,y,rng.uniform(.7,1.55),face,rng,compact=True)
            else:broadleaf_clump(x,y,z,rng.uniform(.55,1.1),(73,113,57),face,rng)
        for _ in range(40):
            x,z=rng.uniform(-80,80),rng.uniform(-80,80)
            a=rng.random()*math.tau
            nurse_log(x,z,math.sin(a),math.cos(a),field.height,face,rng)
            for _ in range(3):
                px,pz=x+rng.uniform(-2,2),z+rng.uniform(-2,2)
                fern(px,pz,field.height(px,pz),rng.uniform(.6,1.4),face,rng,compact=True)
    return mesh

def terrain_grid_mesh(field, raw, aerial, region):
    nx,nz=field.nx,field.nz
    d=field.dx
    mesh=array('f')
    rows=[]
    for j in range(nz):
        row=[]
        for i in range(nx):
            k=j*nx+i
            y=field.values[k]
            dx=(field.values[j*nx+min(nx-1,i+1)]-field.values[j*nx+max(0,i-1)])/(2*d)
            dz=(field.values[min(nz-1,j+1)*nx+i]-field.values[max(0,j-1)*nx+i])/(2*d)
            shade=max(.45,min(1.2,.88+.52*(dx-dz)))
            color=(.11,.32,.37) if raw[k]<=0 else (.88,.92,.95) if y>2400 else (.28,.39,.24)
            material = .20 if raw[k]<=0 else .216 if aerial is not None else .974 if region=='hoh' else .197
            r,g,b = color
            row.append(_VERTEX.pack(field.origin.x+i*d,y,field.origin.z+j*d,
                                    r*shade,g*shade,b*shade,material))
        rows.append(row)
    # Keep 384-vertex culling batches spatially compact in both dimensions.
    for z0 in range(0,nz-1,8):
        for x0 in range(0,nx-1,8):
            vertices=[]
            for j in range(z0,min(nz-1,z0+8)):
                a,b=rows[j:j+2]
                for i in range(x0,min(nx-1,x0+8)):
                    vertices.extend((a[i],b[i],a[i+1],a[i+1],b[i],b[i+1]))
            mesh.frombytes(b''.join(vertices))
    return mesh


class StreetRide:
    """First-person street ride with an optional flower delivery at the market."""
    def __init__(self,kind):
        import os
        from pnw.seattle_places import delivery_route,street_lines,tacoma_corridor
        self.overhead=False
        self.kind=kind.removeprefix('tacoma-')
        self.assist=os.environ.get('POCKET_KID_MODE')=='1'
        self.route=(next(points for name,_,points,_,_ in street_lines('tacoma') if name=='Dock Street' and len(points)>=30)
                    if kind.startswith('tacoma-') else delivery_route())
        if self.kind=='sports-car':
            lines=tacoma_corridor()
            self.route=lines[0][2]+tuple(p for line in lines[1:] for p in line[2][1:])
            self.road_names=tuple(name for name,_,points,_,_ in lines for _point in points[1:])
        elif self.kind in ('bicycle','scooter') and not kind.startswith('tacoma-'):
            self.route=self.route[2:]
        self.x,self.z=self.route[0]
        self.leg=1
        self.heading=self.bearing(self.route[1])
        self.chase_heading=self.heading
        self.bridge_roads=None
        self.speed=self.steer=0.
        self.slip=self.spin=self.damage=0.
        self.actor_kind=10 if self.kind=="sports-car" else 5
        self.paint=0
        self.tuned=False
        self.shop_target=None
        self.cruise=self.delivered=False
        self.keys=set()
        self.contact=None
        self.drag=(0.,0.)
        self.menu=False
        self.patrol=None
        if self.kind=='sports-car' and not self.assist:
            # A fictional encounter at the start of the southbound freeway.
            freeway=next(points for _,kind,points,_,_ in tacoma_corridor() if kind=='freeway')
            x,z=freeway[0]
            self.patrol_heading=math.atan2(freeway[1][0]-x,freeway[1][1]-z)
            self.patrol=(x+5*math.cos(self.patrol_heading),z-5*math.sin(self.patrol_heading))
            self.pursuit='parked'
            self.tracks=deque()

    def alert_patrol(self,traffic):
        if not self.patrol or self.pursuit=='following':return
        if math.dist(self.patrol,(self.x,self.z))>140:
            candidates=[body for body in traffic if 45<math.hypot(body.x-self.x,body.z-self.z)<140]
            if not candidates:return
            source=min(candidates,key=lambda body:math.hypot(body.x-self.x,body.z-self.z))
            self.patrol=(source.x+3*math.cos(source.heading),source.z-3*math.sin(source.heading))
            self.patrol_heading=source.heading
        self.tracks.clear()
        self.pursuit='following'

    def advance_patrol(self,dt):
        if self.patrol is None:return
        x,z=self.patrol
        gap=math.hypot(self.x-x,self.z-z)
        if self.pursuit=='parked':
            if gap>24 or self.speed<24:return
            self.pursuit='following'
        if self.pursuit!='following':return
        if gap>160 or (gap<6 and abs(self.speed)<1):
            self.pursuit='Clear' if gap>160 else 'Traffic stop'
            self.tracks.clear()
            return
        here=(self.x,self.z)
        if not self.tracks or math.dist(self.tracks[-1],here)>3:self.tracks.append(here)
        travel=min(dt*33,max(0.,gap-5.7))
        while self.tracks and travel>0:
            px,pz=self.tracks[0]
            distance=math.hypot(px-x,pz-z)
            if distance>.01:self.patrol_heading=math.atan2(px-x,pz-z)
            if travel<distance:
                x+=(px-x)*travel/distance
                z+=(pz-z)*travel/distance
                break
            travel-=distance
            x,z=self.tracks.popleft()
        self.patrol=(x,z)

    def bearing(self,point):
        return math.atan2(point[0]-self.x,point[1]-self.z)

    def cancel_input(self):
        self.keys.clear()
        self.contact=None
        self.drag=(0.,0.)

    def advance(self,dt,sticks):
        steer=max(-1.,min(1.,sticks[0]+self.drag[0]+('right' in self.keys)-('left' in self.keys)))
        pedal=max(-1.,min(1.,-sticks[1]+self.drag[1]+('up' in self.keys)-('down' in self.keys)))
        maximum={'car':12.,'motorcycle':16.,'bicycle':6.,'scooter':5.5,'sports-car':62.}[self.kind]
        maximum={11:25.,12:29.,9:58.}.get(self.actor_kind,maximum)
        if self.tuned:maximum*=1.12
        target=(pedal if pedal else float(self.cruise))*maximum*(1.-.60*self.damage)
        if self.assist:target=max(0.,min(5.,target))
        else:target=max(-2.5,target)
        change=(target-self.speed)*(-math.expm1(-dt*(3 if target==0 else 1.4)))
        if self.kind=='sports-car':change=max(-11*dt,min(({11:2.,12:1.5}.get(self.actor_kind,7.))*(1.3 if self.tuned else 1.)*dt,change))
        self.speed+=change
        self.steer+=(steer-self.steer)*(-math.expm1(-dt*6))
        distance=self.speed*dt
        if self.assist:
            while distance>0 and self.leg<len(self.route):
                end=self.route[self.leg]
                left=math.dist((self.x,self.z),end)
                self.heading=self.bearing(end)
                if distance<left:
                    self.x+=distance*math.sin(self.heading)
                    self.z+=distance*math.cos(self.heading)
                    break
                self.x,self.z=end
                distance-=left
                self.leg+=1
            if self.leg==len(self.route):self.speed=0.;self.cruise=False
        else:
            wheelbase={'car':2.6,'motorcycle':1.45,'bicycle':1.1,'scooter':1.,'sports-car':2.65}[self.kind]
            steer_angle=.48/(1.+abs(self.speed)*.075) if self.kind=='sports-car' else .48
            self.heading+=distance*math.tan(steer_angle*self.steer)/wheelbase+self.spin*dt
            self.spin*=math.exp(-1.8*dt)
            x=self.x+distance*math.sin(self.heading)
            z=self.z+distance*math.cos(self.heading)
            self.x=x+self.slip*dt*math.cos(self.heading)
            self.z=z-self.slip*dt*math.sin(self.heading)
            self.slip*=math.exp(-2.4*dt)
        if self.kind=='sports-car' and not self.assist:
            from bisect import bisect_right
            from pnw.seattle_places import corridor_position,corridor_path
            position=corridor_position(self.x,self.z)
            if position:
                self.leg=min(len(self.route)-1,1+bisect_right(corridor_path()[1],position[0]+8.))
            self.advance_patrol(dt)
        if abs(self.speed)<.5 and math.dist((self.x,self.z),self.route[-1])<6:self.delivered=True
        turn=math.remainder(self.heading-self.chase_heading,math.tau)
        self.chase_heading+=turn*(-math.expm1(-dt*6))
        return self.x,self.z,self.heading,.045

    @property
    def has_car_camera(self):
        return self.kind in ('car','sports-car')

    def shop_action(self,action):
        from pnw.seattle_places import repair_shops
        here=self.x,self.z
        if action=='shop':
            self.shop_target=min(repair_shops(),key=lambda shop:math.dist(here,shop[1]))
            return self.shop_target[0]
        if not self.at_shop():return 'Park near the shop to service this vehicle'
        if action=='repair':
            self.spin=self.slip=self.damage=0.
            return 'Repaired'
        if action=='paint':
            self.paint=(self.paint+1)%5
            return 'Paint changed'
        if action=='tune':
            self.tuned=not self.tuned
            return 'Street tune installed' if self.tuned else 'Factory tune restored'
        if action=='leave-shop':self.shop_target=None
        return ''

    def at_shop(self):
        return self.shop_target and abs(self.speed)<.8 and math.dist((self.x,self.z),self.shop_target[1])<=35.

    def drive_guidance(self):
        from pnw.seattle_places import corridor_milestones,corridor_position
        here=(self.x,self.z)
        if self.shop_target:
            name,point=self.shop_target
            return point,name,math.dist(here,point)
        position=corridor_position(*here)
        marks=corridor_milestones()
        if position:
            along=position[0]
            distance,target,label=next((mark for mark in marks if mark[0]>along+1.),marks[-1])
            return target,label,max(0.,distance-along)
        _,target,_=min((marks[0],marks[-2]),key=lambda mark:math.dist(here,mark[1]))
        return target,'I-5 ramp',math.dist(here,target)

    def draw_minimap(self,ink,width,height):
        import ctypes as C
        from pnw.seattle_places import nearby_driving_segments
        size=min(144,width*3,height*5)
        if size<40:return
        x0,y0=ink.x+8,ink.y+height*16-size-6
        radius=145.+min(110.,abs(self.speed)*2)
        scale=size/(2*radius)
        sin,cos=math.sin(self.heading),math.cos(self.heading)
        def project(x,z):
            dx,dz=x-self.x,z-self.z
            return size*.5+scale*(dx*cos-dz*sin),size*.5-scale*(dx*sin+dz*cos)
        cx,cz=math.floor(self.x/32),math.floor(self.z/32)
        reach=math.ceil(radius*1.42/32)
        roads=array('f')
        def add(segments):
            for x,z,dx,dz,_,_ in segments:
                roads.extend((*project(x,z),*project(x+dx,z+dz)))
        add(nearby_driving_segments(cx,cz,reach,False))
        ordinary=len(roads)//4
        add(nearby_driving_segments(cx,cz,reach,True))
        access,label,distance=self.drive_guidance()
        ax,ay=project(*access)
        edge=max(1.,abs(ax-size*.5)/(size*.5-5),abs(ay-size*.5)/(size*.5-5))
        draw=ink.ctx.lib.pocket_scene_drive_map
        draw.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_void_p,C.c_uint,C.c_uint,C.c_float,C.c_float]
        ink.ctx.check(draw(ink.ctx.handle,x0,y0,size,roads.buffer_info()[0],len(roads)//4,ordinary,
                           size*.5+(ax-size*.5)/edge,size*.5+(ay-size*.5)/edge))
        units=road_distance(distance)
        ink.label(1,(y0-ink.y)/16-1,label+' · '+units,0xFFCB68)

    def hint(self):
        if self.kind=='sports-car':
            if self.delivered:return 'Arrived · Dock Street, Tacoma'
            if self.patrol and self.pursuit=='following':
                return f'Pursuit · {road_distance(math.dist(self.patrol,(self.x,self.z)))} · {mph(self.speed)}'
            next_point=self.route[min(self.leg,len(self.route)-1)]
            turn=math.remainder(self.bearing(next_point)-self.heading,math.tau)
            arrow='↑' if abs(turn)<.35 else '↓' if abs(turn)>2.65 else '→' if turn>0 else '←'
            street=self.road_names[min(self.leg-1,len(self.road_names)-1)]
            from pnw.seattle_places import corridor_position
            position=corridor_position(self.x,self.z)
            note=position[1] if position else street
            return f'{arrow} {note} · {mph(self.speed)}'
        if self.delivered:return 'Flowers delivered'
        end=self.route[-1]
        turn=math.remainder(self.bearing(end)-self.heading,math.tau)
        arrow='↑' if abs(turn)<.48 else '↓' if abs(turn)>2.65 else '→' if turn>0 else '←'
        metres=round(math.dist((self.x,self.z),end))
        return f'Flowers {arrow} {road_distance(metres)}' if metres>6 else 'Stop to deliver flowers'


class ExploreMenu(HikeMenu):
    groups={'Fly':('Thun Field hangar','Skydive over Rainier','Balloon over the Sound','Plane from Rainier','Plane from Thun Field','Research jet from Rainier','Hang glide','Paramotor'),
            'Mountain sports':('Put on skis','Climb summit ice','Mountain bike loop'),
            'Passenger rail':tuple(rail.RIDES),
            'City rides':tuple(ROAD_RIDES),
            'On the water':('Boat on Commencement Bay','Bainbridge ferry','Puget Sound kelp dive'),
            'Market and waterfront':('Pike Place Market',*market_visit.DESTINATIONS),
            'Seattle':('Pike Place Market','Fish counter','Seattle Great Wheel','Space Needle'),
            'On foot':('Hoh Rain Forest walk','Local trails and activities')}

    def __init__(self,view):
        super().__init__(view)
        self.group=None

    def lines(self,width):
        v=self.view
        if v.travel_job:return ('Preparing terrain…','Opening the offline elevation grid.')
        if self.group=='Credits':
            return ('Credits','','Seattle map data','© OpenStreetMap contributors',
                    'Open Database License (ODbL)','openstreetmap.org/copyright','','Back')
        if v.party:return ('Explore','Local trails and activities','Credits','Back')
        if self.group:return (self.group,'',*self.groups[self.group],'','Back',v.travel_error[:width])
        return ('Explore','',*self.groups,'Credits','','Return to Ohanapecosh' if v.regional else 'Back',v.travel_error[:width])

    def tap_xy(self,x,y):
        v=self.view
        if v.travel_job:return True
        rows=self.lines(80)
        label=rows[int(y)] if 0<=y<len(rows) else ''
        if label in self.groups or label=='Credits':self.group=label
        elif label in ('Hang glide','Paramotor',*self.groups['Mountain sports']):
            if v.regional and not v.outing:
                return not v.start_mountain_sport(label)
            v.start_region()
            v.pending_sport=label
        elif label in OUTINGS:v.start_outing(OUTINGS[label])
        elif label=='Local trails and activities':
            if v.outing:v.return_to_valley()
            v.notebook=HikeMenu(v)
        elif label=='Return to Ohanapecosh':v.return_to_valley();return False
        elif label=='Back':
            if not self.group:return False
            self.group=None
        return True


class PauseMenu:
    """Shared local pause screen, navigable by controller or touch."""
    def __init__(self,view):
        self.view=view
        self.page='Paused'
        self.selected=0
        self.guide_page=0

    def rows(self):
        if self.page=='Controller':
            prefs=self.view.app_context.preferences
            return ('Sticks: '+prefs['stick-layout'],'Look: '+prefs['look-speed'],'Back')
        if self.page=='Flight controls':
            prefs=self.view.app_context.preferences
            rows=('Pitch: '+prefs['flight-pitch'],'Roll: '+prefs['flight-roll'])
            flight=self.view.glider
            if self.view.outing in ('jet','hangar-jet') and flight:
                rows+=('Reduce throttle','Increase throttle',f'Flaps: {flight.flaps*10} deg',
                       'Gear: '+('down' if flight.gear_down else 'up'))
            return (*rows,'Back')
        if self.page=='Driving controls':return ('Resume','Back')
        if self.page=='Flight guide':
            return ('Next page','Back')
        if getattr(self.view,'road',None):return ('Resume','Driving controls','Weather: '+('Clear','Mist','Showers')[self.view.weather],'Controller')
        flight=self.view.outing in AIRCRAFT and self.view.glider
        rows=('Resume','Controller','Flight controls','Flight guide')
        return rows+('Leave aircraft',) if flight else rows

    def lines(self,width):
        return ()

    def draw(self,ink,width,height):
        panel=min(width,36)
        ink.fill((0,0,width,height),0x10192378)
        ink.fill((0,0,panel,height),0x122024EF)
        title=self.page if self.page!='Flight guide' else f'Flight guide  {self.guide_page+1}/3'
        ink.label(1,.4,title,0xF6EFCE)
        for i,label in enumerate(self.rows()):
            y=2+i*2
            if i==self.selected:
                ink.fill((.5,y,panel-1,1.9),0x3E6159FF)
                ink.fill((.5,y,.3,1.9),0xF0CC78FF)
            ink.label(1.6,y+.42,label[:panel-2],0xFFF6DA)
        hints=(('Left stick: roll / pitch','Right stick: look','LB / RB: rudder'),
               ('LT / RT: throttle','D-pad down/up: flaps out/in','D-pad left/right: glance'),
               ('A: takeoff / approach','X: waypoint   Y: cruise','Stall: nose down, add power'))
        footer=hints[self.guide_page] if self.page=='Flight guide' else ('A: select   B: back',)
        if self.page=='Driving controls':
            footer=('W/S or up/down: gas / brake','A/D or left/right: steer','Space or Go: hold accelerator')
            if self.view.road.has_car_camera:footer+=('0 or View: switch camera','E or Exit: leave vehicle',)
        y=2+2*len(self.rows())
        for i,line in enumerate(footer):
            if y+i<height:ink.label(1,y+i,line[:panel-1],0xC3D2CA)

    def tap_xy(self,x,y):
        index=(int(y)-2)//2
        if 0<=x<36 and 0<=index<len(self.rows()):
            self.selected=index
            self.activate()
        return self.view.notebook is self

    def activate(self,direction=1):
        label=self.rows()[self.selected]
        if self.page=='Controller' and label!='Back':
            key,choices=(('stick-layout',('Standard','Southpaw')) if self.selected==0
                         else ('look-speed',('Gentle','Standard','Quick')))
            context=self.view.app_context
            context.registry.set_setting(context.identifier,key,choices[(choices.index(context.preferences[key])+direction)%len(choices)])
        elif self.page=='Flight controls' and label in ('Reduce throttle','Increase throttle'):
            flight=self.view.glider
            flight.throttle=max(0.,min(1.,flight.throttle+(.1 if label=='Increase throttle' else -.1)))
            flight.fast=flight.throttle>=.99
        elif self.page=='Flight controls' and label.startswith('Flaps:'):
            self.view.glider.flaps=(self.view.glider.flaps+direction)%3
        elif self.page=='Flight controls' and label.startswith('Gear:'):
            self.view.glider.toggle_gear()
        elif self.page=='Flight controls' and label!='Back':
            key,choices=(('flight-pitch',('Pull to climb','Push to climb')) if self.selected==0
                         else ('flight-roll',('Gentle','Standard','Quick')))
            context=self.view.app_context
            value=choices[(choices.index(context.preferences[key])+direction)%len(choices)]
            context.registry.set_setting(context.identifier,key,value)
        elif label.startswith('Weather:'):
            self.view.weather=(self.view.weather+direction)%3
        elif label=='Next page':self.guide_page=(self.guide_page+1)%3
        elif label=='Resume':self.view.resume_game()
        elif label=='Leave aircraft':
            self.view.resume_game()
            self.view.end_flight()
        else:
            self.page='Paused' if label=='Back' else label
            self.selected=0

    def button(self,button):
        if button in (11,12):
            self.selected=(self.selected+(1 if button==12 else -1))%len(self.rows())
        elif button==0:self.activate()
        elif button in (13,14) and self.page in ('Controller','Flight controls') and self.selected<2:
            self.activate(1 if button==14 else -1)
        elif button==14:self.activate()
        elif button==13:self.button(1)
        elif button==6 or (button==1 and self.page=='Paused'):self.view.resume_game()
        elif button==1:self.page='Paused';self.selected=0


class Scuba(HangGlider):
    def __init__(self,field):
        from types import SimpleNamespace
        super().__init__(SimpleNamespace(x=0.,z=0.,heading=0.),field.height)
        self.altitude=-6.
        self.swimming=False

    def action(self):self.swimming=not self.swimming

    def advance(self,dt,height,limits):
        steer=max(-1.,min(1.,self.stick+self.drag[0]+('right' in self.keys)-('left' in self.keys)))
        vertical=max(-1.,min(1.,self.pitch_stick+self.drag[1]+('up' in self.keys)-('down' in self.keys)))
        self.heading+=steer*dt
        self.speed=1.8 if self.swimming else 0.
        west,east,south,north=limits
        self.x=max(west+1,min(east-1,self.x+self.speed*dt*math.sin(self.heading)))
        self.z=max(south+1,min(north-1,self.z+self.speed*dt*math.cos(self.heading)))
        self.altitude=max(height(self.x,self.z)+.25,min(-1.8,self.altitude+vertical*1.2*dt))
        return self.x,self.z,self.heading,.08-.35*vertical

    def controls(self,w,h):
        return [('air-action','Float' if self.swimming else 'Swim',(0,0,9,2)),
                ('surface','Surface',(w-10,0,10,2))]

    def draw(self,ink,w,h):
        ink.label(1,h-2,f'{-self.altitude-1.25:.1f} m deep',0xE5F7F2)

def start_sport(kind,field):
    return Scuba(field) if kind=='scuba' else AirSport(kind,field)

class AirSport(HangGlider):
    def __init__(self,kind,field):
        from types import SimpleNamespace
        self.balloon=kind=='balloon'
        x,z=location('sound',*(BAY if self.balloon else PLACES[-1][1:]))
        super().__init__(SimpleNamespace(x=x,z=z,heading=-math.pi),field.height)
        self.altitude=field.height(x,z)+(120. if self.balloon else 1800.)
        self.clearance=self.altitude-field.height(self.x,self.z)
        self.vertical=0.
        self.open=False

    def action(self):
        if self.balloon:self.motor=not self.motor
        else:self.open=True

    def advance(self,dt,height,limits):
        steering=max(-1.,min(1.,self.stick+self.drag[0]+('right' in self.keys)-('left' in self.keys)))
        self.heading+=steering*dt
        self.speed=5. if self.balloon else 10. if self.open else 17.
        if not self.balloon and self.clearance<120.:self.open=True
        target=(4. if self.motor else -2.) if self.balloon else -4.5 if self.open else -50.
        self.vertical+=(target-self.vertical)*(-math.expm1(-dt))
        course=.8+.18*math.sin(self.altitude*.002) if self.balloon else self.heading
        west,east,south,north=limits
        self.x=max(west,min(east,self.x+dt*self.speed*math.sin(course)))
        self.z=max(south,min(north,self.z+dt*self.speed*math.cos(course)))
        ground=height(self.x,self.z)
        self.clearance=max(0.,self.altitude+self.vertical*dt-ground)
        self.altitude=ground+self.clearance
        self.landed=self.clearance==0
        return self.x,self.z,self.heading,.25+self.pitch_stick*.5

    def controls(self,w,h):
        label=('Burner off' if self.motor else 'Burner on') if self.balloon else ('Chute open' if self.open else 'Open chute')
        return [('air-action',label,(w-14,0,14,3)),('pause','Pause',(w-14,3,14,3))]

    def draw(self,ink,w,h):
        ink.label(1,1,f'{feet(self.clearance)} AGL',0xFFF6DA)


class SoundVehicle(HangGlider):
    def __init__(self,kind,field):
        from types import SimpleNamespace
        self.kind=kind
        self.boat=kind=='boat'
        self.aircraft=AIRCRAFT.get(kind)
        self.stops=[(name,*location('sound',lat,lon)) for name,lat,lon in PLACES]
        from pnw.seattle_places import places
        self.stops.append(('Space Needle',*places()['Space Needle']))
        self.stops.append(('Jimothy mural · Ballard Clay',*places()['Ballard Clay']))
        self.target_index=3 if self.boat else 1 if kind=='thun' else 0
        x,z=location('sound',*BAY) if self.boat else self.stops[0 if kind=='thun' else 4][1:]
        super().__init__(SimpleNamespace(x=x,z=z,heading=0),field.height,True)
        self.altitude=0. if self.boat else field.height(x,z)+(1200. if self.aircraft is RESEARCH_JET else 350.)
        self.throttle=self.aircraft.cruise_power if self.aircraft else 0.
        self.speed=(self.aircraft.approach+(self.aircraft.maximum-self.aircraft.approach)*self.throttle
                    if self.aircraft else 0.)
        _,tx,tz=self.stops[self.target_index]
        self.heading=math.atan2(tx-x,tz-z)

        self.runways=tuple(runway_geometry())
        self.rudder=self.throttle_rate=0.
        self.gear_down=kind!='jet'
        self.flaps=0
        self.stalled=False
        self.roll_angle=self.roll_rate=self.elevation=0.
        self.look=(0.,0.)
        self.look_yaw=self.look_pitch=0.
        self.roll_gain=1.
        self.roll_state=None
        if kind in ('thun','hangar-jet'):
            rx,rz,self.heading,_,_=self.runways[0]
            self.x=rx+18*math.sin(self.heading)
            self.z=rz+18*math.cos(self.heading)
            self.altitude=field.height(self.x,self.z)+.3
            self.speed=0.
            self.roll_state='parked'
            self.target_index=2

    def board(self,pose):
        dx,_=BAYS[self.kind]
        self.x,self.z=HANGAR[0]+dx,HANGAR[1]
        self.heading=math.pi
        self.entry=pose
        self.board_time=0.
        self.taxi_waypoint=1
        self.speed=self.throttle=0.
        self.roll_state='boarding'

    def cancel_input(self):
        super().cancel_input()
        self.rudder=self.throttle_rate=0.
        self.look=(0.,0.)

    def toggle_speed(self):
        super().toggle_speed()
        self.throttle=1. if self.fast else self.aircraft.cruise_power if self.aircraft else 0.

    def toggle_gear(self):
        if self.aircraft is RESEARCH_JET and self.roll_state not in ('boarding','taxi','parked','takeoff','rollout'):
            self.gear_down=not self.gear_down

    def runway_at(self,x,z):
        for rx,rz,yaw,length,width in self.runways:
            dx,dz=x-rx,z-rz
            along=dx*math.sin(yaw)+dz*math.cos(yaw)
            across=dx*math.cos(yaw)-dz*math.sin(yaw)
            if 0<=along<=length and abs(across)<=width/2:
                return yaw,along,length
        return None

    def toggle_motor(self):
        self.target_index=(self.target_index+1)%len(self.stops)

    def turn_aircraft(self,dt):
        """Rotate the nose and canopy together about the aircraft's local axes."""
        from geometry import Vec,add,mul,dot
        pitch_rate=-self.pitch*math.radians(self.aircraft.pitch_rate)
        yaw_rate=.14*self.rudder
        rate=math.hypot(pitch_rate,yaw_rate)
        if not rate:return
        # Work in the current heading frame: +x right, +y up, +z ahead.
        se,ce=math.sin(self.elevation),math.cos(self.elevation)
        sb,cb=math.sin(self.roll_angle),math.cos(self.roll_angle)
        nose=Vec(0.,se,ce)
        canopy=Vec(sb,cb*ce,-cb*se)
        right=Vec(cb,-sb*ce,sb*se)
        tangent=add(mul(canopy,pitch_rate/rate),mul(right,yaw_rate/rate))
        sn,cs=math.sin(rate*dt),math.cos(rate*dt)
        forward=add(mul(nose,cs),mul(tangent,sn))
        # Only the component of the canopy in the turn plane rotates.
        canopy=add(canopy,mul(add(mul(tangent,cs-1),mul(nose,-sn)),pitch_rate/rate))
        horizontal=math.hypot(forward.x,forward.z)
        yaw=math.atan2(forward.x,forward.z) if horizontal>1e-10 else 0.
        self.heading+=yaw
        self.elevation=math.atan2(forward.y,horizontal)
        sy,cy=math.sin(yaw),math.cos(yaw)
        level_right=Vec(cy,0.,-sy)
        level_up=Vec(-sy*forward.y,horizontal,-cy*forward.y)
        self.roll_angle=math.atan2(dot(canopy,level_right),dot(canopy,level_up))

    def advance(self,dt,height,limits):
        blend=-math.expm1(-8*dt)
        self.look_yaw+=(1.40*self.look[0]-self.look_yaw)*blend
        self.look_pitch+=(.68*self.look[1]-self.look_pitch)*blend
        if self.throttle_rate:
            self.throttle=max(0.,min(1.,self.throttle+self.throttle_rate*dt*.35))
            self.fast=self.throttle>=.99
        if self.roll_state=='boarding':
            self.board_time+=dt
            t=min(1.,self.board_time/1.4)
            u=t*t*(3-2*t)
            ox,oz,yaw,pitch=self.entry
            x,z=ox+(self.x-ox)*u,oz+(self.z-oz)*u
            self.altitude=height(x,z)+.15+u*.58+.32*math.sin(t*math.pi)
            if t==1:self.roll_state='taxi'
            return x,z,yaw+math.remainder(self.heading-yaw,math.tau)*u,pitch*(1-u)+.03*u
        if self.roll_state=='taxi':
            strip=self.runway_at(self.x,self.z)
            if self.descending and strip:
                self.throttle=max(.85,self.throttle)
                self.roll_state='parked'
            else:
                self.descending=False
                drive=self.throttle+self.drag[1]+('up' in self.keys)-('down' in self.keys)
                target=8*max(0.,min(1.,drive))
                self.speed+=(target-self.speed)*(-math.expm1(-dt*(2 if not target else .9)))
                steer=self.stick+self.rudder+self.drag[0]+('right' in self.keys)-('left' in self.keys)
                self.heading+=max(-1.,min(1.,steer))*dt*min(1.,self.speed*.26)
                self.x+=self.speed*dt*math.sin(self.heading)
                self.z+=self.speed*dt*math.cos(self.heading)
                self.altitude=height(self.x,self.z)+.73
                way=taxi_path()
                if math.dist((self.x,self.z),way[self.taxi_waypoint])<10:
                    self.taxi_waypoint=min(len(way)-1,self.taxi_waypoint+1)
                return self.x,self.z,self.heading+self.look_yaw,.03+self.look_pitch
        if self.roll_state in ('parked','takeoff','rollout'):
            if self.roll_state=='parked' and self.descending:
                self.descending=False
                strip=self.runway_at(self.x,self.z)
                if strip:
                    yaw,along,length=strip
                    self.heading=yaw if along<length/2 else yaw+math.pi
                    self.roll_state='takeoff'
            if self.roll_state=='takeoff':self.speed+=3.8*dt
            elif self.roll_state=='rollout':self.speed=max(0.,self.speed-self.aircraft.brakes*dt)
            self.x+=math.sin(self.heading)*self.speed*dt
            self.z+=math.cos(self.heading)*self.speed*dt
            self.altitude=height(self.x,self.z)+.3
            self.clearance=.3
            if self.roll_state=='takeoff' and self.speed>=self.aircraft.approach:self.roll_state='climbout'
            elif self.roll_state=='rollout' and self.speed==0:self.roll_state='parked'
            return self.x,self.z,self.heading+self.look_yaw,.03+self.look_pitch
        roll=self.stick+self.drag[0]+('right' in self.keys)-('left' in self.keys)
        pitch=self.pitch_stick+self.drag[1]+('up' in self.keys)-('down' in self.keys)
        smooth=-math.expm1(-3*dt)
        roll=max(-1.,min(1.,roll))
        if self.boat:
            self.bank+=(roll-self.bank)*smooth
        else:
            self.roll_rate+=(roll*self.roll_gain*math.radians(self.aircraft.roll_rate)-self.roll_rate)*smooth
            self.roll_angle=math.remainder(self.roll_angle+self.roll_rate*dt,math.tau)
        self.pitch+=(max(-1.,min(1.,pitch))-self.pitch)*smooth
        cruise=(22. if self.fast else 10.) if self.boat else self.aircraft.approach+(self.aircraft.maximum-self.aircraft.approach)*self.throttle
        if self.descending and self.aircraft:self.gear_down=True
        if self.descending:cruise=0. if self.boat else self.aircraft.approach
        if not self.boat and not self.descending:
            cruise=max(12.,cruise-8.*(1.-self.throttle)-40.*math.sin(self.elevation)-3.*self.flaps)
        if self.aircraft is RESEARCH_JET and self.gear_down and not self.descending:cruise*=.88
        self.speed+=(cruise-self.speed)*(-math.expm1(-dt/(self.aircraft.spool_time if self.aircraft else 1.)))
        if self.boat:self.heading+=self.bank*dt*.64
        else:
            self.turn_aircraft(dt)
            self.bank=self.roll_angle/math.radians(55)
            self.heading+=dt*9.81*math.sin(self.roll_angle)*math.cos(self.elevation)/max(20.,self.speed)
            stall_speed=self.aircraft.stall-2.*self.flaps+6.*max(0.,-self.pitch)
            self.stalled=self.roll_state is None and self.speed<stall_speed+(3. if self.stalled else 0.)
        west,east,south,north=limits
        ground_speed=self.speed*math.cos(self.elevation)
        x=self.x+ground_speed*dt*math.sin(self.heading)
        z=self.z+ground_speed*dt*math.cos(self.heading)
        if self.boat:x,z=max(west,min(east,x)),max(south,min(north,z))
        ground=height(x,z)
        if self.boat and ground>.01:self.speed=0.
        else:self.x,self.z=x,z
        if not self.boat:
            lift=math.cos(self.roll_angle)
            next_alt=self.altitude+dt*(self.speed*math.sin(self.elevation)-9.*(1.-lift)-12*self.descending)
            if self.stalled:next_alt=min(next_alt,self.altitude-8.*dt)
            if self.roll_state=='climbout':
                next_alt=self.altitude+dt*9.
                if next_alt-ground>=30 or self.descending:self.roll_state=None
            manual_approach=self.roll_state is None and self.speed<self.aircraft.approach+7. and abs(self.bank)<.18 and -.15<=self.elevation<=.01
            strip=self.runway_at(x,z) if self.descending or manual_approach else None
            on_approach=False
            if strip and self.gear_down and self.speed<self.aircraft.approach+7.:
                yaw,along,length=strip
                aligned=math.cos(self.heading-yaw)
                remaining=length-along if aligned>0 else along
                on_approach=abs(aligned)>.97 and remaining>self.speed**2/(2.*self.aircraft.brakes)+3.
                if on_approach and next_alt<=ground+.3:
                    self.heading=yaw if aligned>0 else yaw+math.pi
                    self.descending=False;self.roll_state='rollout'
                    self.elevation=self.roll_angle=self.roll_rate=self.bank=0.
            self.altitude=max(ground+(.3 if self.roll_state or on_approach else 6.),next_alt)
        self.clearance=max(0.,self.altitude-ground)
        camera_pitch=.06+.08*self.pitch if self.boat else -self.elevation
        return self.x,self.z,self.heading+self.look_yaw,camera_pitch+self.look_pitch

    def wheel_items(self):
        items=super().wheel_items()
        descent='Go' if self.descending else 'Stop'
        if not self.boat:
            descent='Take off' if self.roll_state in ('taxi','parked') else 'Go around' if self.descending else 'Approach'
        return [(action,'Waypoint' if action=='motor' else descent if action=='descend' else label,angle)
                for action,label,angle in items]

    def controls(self,w,h):
        if not self.menu and self.roll_state=='taxi' and self.runway_at(self.x,self.z):
            return [('descend','Take off',(w-12,0,12,2))]
        if not self.menu and self.boat:return [('wheel','Helm',(w-11,0,11,3))]
        if not self.menu and self.aircraft is RESEARCH_JET:
            return []
        if not self.menu:return [('wheel','Flight',(w-11,0,11,3)),('pause','Pause',(w-11,3,11,3))]
        return super().controls(w,h)

    def draw(self,ink,w,h):
        name,x,z=self.stops[self.target_index]
        bearing=round(math.degrees(math.atan2(x-self.x,z-self.z)))%360
        distance=math.hypot(x-self.x,z-self.z)/1852
        if self.boat:
            super().draw(ink,w,h)
            ink.label(1,h-3,name,0xFFF4DC)
            ink.label(1,h-2,f'{distance:.1f} NM  {bearing:03d} deg',0xFFF4DC)
            return
        if self.menu:
            for _,_,angle in self.wheel_items():
                ink.sector(w/2,h/2,self.radius(w,h),angle)
        if self.roll_state in ('boarding','taxi'):
            if self.roll_state=='boarding':label='Boarding'
            elif self.runway_at(self.x,self.z):label='Runway · A to take off'
            else:
                px,pz=taxi_path()[self.taxi_waypoint]
                bearing=round(math.degrees(math.atan2(px-self.x,pz-self.z)))%360
                label=f'Taxi {bearing:03d}° · {feet(math.hypot(px-self.x,pz-self.z))}'
            ink.label(1,1,label,0xFFEDBF)
            return
        power='APPR' if self.descending else f'THR {round(100*self.throttle)}%'
        if self.aircraft is RESEARCH_JET:
            if self.stalled:ink.label(w/2-2,h*.58,'STALL',0xFFCD79)
            return
        lines=(name,f'{distance:.1f} NM  BRG {bearing:03d}',
               f'HDG {round(math.degrees(self.heading))%360:03d}  {power}',
               f'{feet(self.clearance)} AGL')
        status='STALL: nose down + power' if self.stalled else f'Flaps {self.flaps*10} deg'
        lines+=(status,)
        lines+=('Start: pause   View: wheel',)
        ink.fill((.5,.6,min(w,max(map(len,lines))+1),len(lines)+.6),0x14231FE8)
        for i,line in enumerate(lines):ink.label(1,1+i,line,0xEEE8CC)
