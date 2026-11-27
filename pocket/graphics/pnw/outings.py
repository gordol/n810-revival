"""Regional travel, aircraft, and scenes for Pacific Northwest outings."""
from array import array
import math
import random
from struct import Struct

from pnw import market_visit
from pnw.terrain import GRIDS,elevations,layout,location,sound_aerial
from pnw.hiking import HangGlider,HikeMenu

_VERTEX = Struct('=7f')

PLACES=(('Thun Field',47.104,-122.287),('Tacoma waterfront',47.266,-122.449),
        ('Tacoma Narrows Airport',47.268,-122.578),('Seattle waterfront',47.604,-122.339),
        ('Rainier',46.852,-121.760))
BAY=(47.295,-122.435)
OUTINGS={'Plane from Rainier':'plane','Plane from Thun Field':'thun',
         'Boat on Commencement Bay':'boat','Hoh Rain Forest walk':'hoh','Bainbridge ferry':'ferry','Seattle Great Wheel':'wheel',
         'Pike Place Market':'market','Fish counter':'fishshop','Space Needle':'needle'}

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
                      ((47.2747,-122.577004),(47.261135,-122.579335),30.48)):
        x,z=location('sound',*a)
        ex,ez=location('sound',*b)
        yield x,z,math.atan2(ex-x,ez-z),math.hypot(ex-x,ez-z),width

def ride_pose(outing,elapsed):
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

def build_world(outing,*,require_cache=False,prepare=False):
    from geometry import Vec
    from pnw.summit_detail import RegionalTerrain
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
            mesh.frombytes(b''.join((a,b,c,a,c,d)))
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
        for name,lat,lon in (PLACES[1],):
            rng=random.Random(name)
            x,z=location(region,lat,lon)
            for col in range(10):
                for row in range(18):
                    xx=x+col*96+rng.uniform(-12,12)
                    zz=z+(row-8)*106+rng.uniform(-15,15)
                    y=surface(field,xx,zz)
                    if y<4:continue
                    width,depth=rng.uniform(30,63),rng.uniform(34,76)
                    tower=math.exp(-((col-4)**2+(row-9)**2)/15)
                    height=rng.uniform(14,48)+tower*rng.uniform(40,200)
                    color=rng.choice(((.41,.51,.56),(.47,.49,.51),(.59,.47,.40),(.44,.57,.63)))
                    box(xx,zz,y-2,width,depth,height,color,.228)
                    box(xx,zz,y+height-2,width*.65,depth*.66,rng.uniform(2,10),color,.228)
        # Long timber piers and gabled sheds step out into Elliott Bay.
        for lat,lon,length in ((47.6056,-122.3412,108),(47.6065,-122.3418,122),
                               (47.6075,-122.3423,112),(47.6093,-122.3441,94)):
            x,z=location(region,lat,lon)
            deck=surface(field,x,z)+2.
            box(x,z,deck-1.2,length,29,1.2,(.42,.34,.25))
            for u in range(-int(length/2)+3,int(length/2),7):
                for side in (-1,1):
                    box(x+u,z+side*13,deck-11,.7,.7,10.,(.22,.22,.17))
            box(x+5,z,deck,length*.79,19.,6.,(.64,.42,.32),.228)
            for side in (-1,1):
                eave=z+side*10.
                left=x+5-length*.41
                right=x+5+length*.41
                quad(((left,deck+6,eave),(right,deck+6,eave),(right,deck+10,z),
                      (left,deck+10,z)),(.33,.38,.39))
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
        from pnw.seattle_places import arcade_origin,buildings,space_needle,streets
        def ground(x,z):return surface(field,x,z)
        pike_market.build(arcade_origin(),ground,quad)
        streets(ground,quad)
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
            material = .20 if raw[k]<=0 else .216 if aerial is not None else .974 if region=='hoh' else .0
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


class ExploreMenu(HikeMenu):
    groups={'Fly':('Plane from Rainier','Plane from Thun Field','Hang glide','Paramotor'),
            'Mountain sports':('Put on skis','Climb summit ice','Mountain bike loop'),
            'On the water':('Boat on Commencement Bay','Bainbridge ferry'),
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


class SoundVehicle(HangGlider):
    def __init__(self,kind,field):
        from types import SimpleNamespace
        self.kind=kind
        self.boat=kind=='boat'
        self.stops=[(name,*location('sound',lat,lon)) for name,lat,lon in PLACES]
        from pnw.seattle_places import places
        self.stops.append(('Space Needle',*places()['Space Needle']))
        self.stops.append(('Jimothy mural · Ballard Clay',*places()['Ballard Clay']))
        self.target_index=3 if self.boat else 1 if kind=='thun' else 0
        x,z=location('sound',*BAY) if self.boat else self.stops[0 if kind=='thun' else 4][1:]
        super().__init__(SimpleNamespace(x=x,z=z,heading=0),field.height,True)
        self.altitude=0. if self.boat else field.height(x,z)+350.
        self.speed=0. if self.boat else 80.
        _,tx,tz=self.stops[self.target_index]
        self.heading=math.atan2(tx-x,tz-z)

        self.runways=tuple(runway_geometry())
        self.rudder=self.throttle_rate=0.
        self.throttle=48./118.
        self.roll_state=None
        if kind=='thun':
            rx,rz,self.heading,_,_=self.runways[0]
            self.x=rx+18*math.sin(self.heading)
            self.z=rz+18*math.cos(self.heading)
            self.altitude=field.height(self.x,self.z)+.3
            self.speed=0.
            self.roll_state='parked'
            self.target_index=2

    def cancel_input(self):
        super().cancel_input()
        self.rudder=self.throttle_rate=0.

    def toggle_speed(self):
        super().toggle_speed()
        self.throttle=1. if self.fast else 48./118.

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

    def advance(self,dt,height,limits):
        if self.throttle_rate:
            self.throttle=max(0.,min(1.,self.throttle+self.throttle_rate*dt*.35))
            self.fast=self.throttle>=.99
        if self.roll_state in ('parked','takeoff','rollout'):
            if self.roll_state=='parked' and self.descending:
                self.descending=False
                strip=self.runway_at(self.x,self.z)
                if strip:
                    yaw,along,length=strip
                    self.heading=yaw if along<length/2 else yaw+math.pi
                    self.roll_state='takeoff'
            if self.roll_state=='takeoff':self.speed+=3.8*dt
            elif self.roll_state=='rollout':self.speed=max(0.,self.speed-4.*dt)
            self.x+=math.sin(self.heading)*self.speed*dt
            self.z+=math.cos(self.heading)*self.speed*dt
            self.altitude=height(self.x,self.z)+.3
            self.clearance=.3
            if self.roll_state=='takeoff' and self.speed>=32:self.roll_state='climbout'
            elif self.roll_state=='rollout' and self.speed==0:self.roll_state='parked'
            return self.x,self.z,self.heading,.03
        roll=self.stick+self.drag[0]+('right' in self.keys)-('left' in self.keys)
        pitch=self.pitch_stick+self.drag[1]+('up' in self.keys)-('down' in self.keys)
        smooth=-math.expm1(-3*dt)
        self.bank+=(max(-1.,min(1.,roll))-self.bank)*smooth
        self.pitch+=(max(-1.,min(1.,pitch))-self.pitch)*smooth
        cruise=(22. if self.fast else 10.) if self.boat else 32.+118.*self.throttle
        if self.descending:cruise=0. if self.boat else 32.
        self.speed+=(cruise-self.speed)*(-math.expm1(-dt))
        if self.boat:self.heading+=self.bank*dt*.64
        else:
            # Coordinated turn rate falls with airspeed for the same bank angle.
            self.heading+=dt*(9.81*math.tan(math.radians(55)*self.bank)/max(25.,self.speed)+.14*self.rudder)
        west,east,south,north=limits
        x=max(west,min(east,self.x+self.speed*dt*math.sin(self.heading)))
        z=max(south,min(north,self.z+self.speed*dt*math.cos(self.heading)))
        ground=height(x,z)
        if self.boat and ground>.01:self.speed=0.
        else:self.x,self.z=x,z
        if not self.boat:
            next_alt=self.altitude-dt*(self.speed*math.sin(.40*self.pitch)+12*self.descending)
            if self.roll_state=='climbout':
                next_alt=self.altitude+dt*9.
                if next_alt-ground>=30 or self.descending:self.roll_state=None
            manual_approach=self.roll_state is None and self.speed<39. and abs(self.bank)<.18 and 0<=self.pitch<=.30
            strip=self.runway_at(x,z) if self.descending or manual_approach else None
            on_approach=False
            if strip and self.speed<39.:
                yaw,along,length=strip
                aligned=math.cos(self.heading-yaw)
                remaining=length-along if aligned>0 else along
                on_approach=abs(aligned)>.97 and remaining>self.speed**2/8.+3.
                if on_approach and next_alt<=ground+.3:
                    self.heading=yaw if aligned>0 else yaw+math.pi
                    self.descending=False;self.roll_state='rollout'
            self.altitude=max(ground+(.3 if self.roll_state or on_approach else 6.),next_alt)
        self.clearance=max(0.,self.altitude-ground)
        return self.x,self.z,self.heading,.06+(.08 if self.boat else .40)*self.pitch

    def wheel_items(self):
        items=super().wheel_items()
        descent='Go' if self.descending else 'Stop'
        if not self.boat:
            descent='Take off' if self.roll_state=='parked' else 'Go around' if self.descending else 'Approach'
        return [(action,'Waypoint' if action=='motor' else descent if action=='descend' else label,angle)
                for action,label,angle in items]

    def controls(self,w,h):
        if not self.menu and self.boat:return [('wheel','Helm',(w-11,0,11,3))]
        return super().controls(w,h)

    def draw(self,ink,w,h):
        name,x,z=self.stops[self.target_index]
        bearing=round(math.degrees(math.atan2(x-self.x,z-self.z)))%360
        distance=math.hypot(x-self.x,z-self.z)/1000
        if self.boat:
            super().draw(ink,w,h)
            ink.label(1,h-3,name,0xFFF4DC)
            ink.label(1,h-2,f'{distance:.1f} km  {bearing:03d} deg',0xFFF4DC)
            return
        if self.menu:
            for _,_,angle in self.wheel_items():
                ink.sector(w/2,h/2,self.radius(w,h),angle)
        power='APPR' if self.descending else f'THR {round(100*self.throttle)}%'
        lines=(name,f'{distance:.1f} km  BRG {bearing:03d}',
               f'HDG {round(math.degrees(self.heading))%360:03d}  {power}',
               f'{round(self.clearance)} m AGL')
        ink.fill((.5,.6,max(map(len,lines))+1,4.6),0x14231FE8)
        for i,line in enumerate(lines):ink.label(1,1+i,line,0xEEE8CC)
