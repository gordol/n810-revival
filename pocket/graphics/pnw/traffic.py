"""Local traffic on the mapped northbound and southbound Seattle–Tacoma routes."""
from bisect import bisect_left
from functools import lru_cache
import math
from pnw.seattle_places import corridor_path, freeway_data, freeway_lines, street_lines
from pnw.terrain import location
from pnw.vehicle_impact import Body, collide, contact

@lru_cache(maxsize=1)
def routes():
    south=[(s[1],s[2]) for s in corridor_path()[0]]
    last=corridor_path()[0][-1]
    south.append((last[1]+last[3]*last[5],last[2]+last[4]*last[5]))
    north=[location('sound',lat/1e7,lon/1e7) for lon,lat in freeway_data()['north']]
    # Follow directed OSM links onto and off the through carriageway.
    network=freeway_lines()
    starts={};finishes={}
    for _,kind,points,_,_ in network:
        starts.setdefault(points[0],[]).append((kind,points))
        finishes.setdefault(points[-1],[]).append((kind,points))
    extras=[]
    for _,kind,points,_,_ in network:
        if kind!='motorway_link':continue
        adjoining=(*finishes.get(points[0],()),*starts.get(points[-1],()))
        if not any(k=='motorway' for k,_ in adjoining):continue
        path=list(points)
        for backwards,adjacency in ((True,finishes),(False,starts)):
            used={points}
            for _ in range(5):
                end=path[0] if backwards else path[-1]
                options=[(k,p) for k,p in adjacency.get(end,()) if p not in used]
                if not options:break
                k,extension=max(options,key=lambda item:(item[0]=='motorway',len(item[1])))
                used.add(extension)
                if backwards:path=list(extension[:-1])+path
                else:path.extend(extension[1:])
                if k=='motorway':break
        if sum(math.dist(a,b) for a,b in zip(path,path[1:]))>250:extras.append(path)
    for city in ('seattle','tacoma','airports'):
        for _,kind,points,_,_ in street_lines(city):
            if kind in ('primary','secondary','tertiary') and math.dist(points[0],points[-1])>100:
                extras.append(points)
    paths=[]
    for points in (south,north,*extras):
        spans=[];ends=[];cells={};start=0.
        for a,b in zip(points,points[1:]):
            length=math.dist(a,b)
            if length<.01:continue
            spans.append((*a,(b[0]-a[0])/length,(b[1]-a[1])/length,start))
            for i in range(math.floor(min(a[0],b[0])/256),math.floor(max(a[0],b[0])/256)+1):
                for j in range(math.floor(min(a[1],b[1])/256),math.floor(max(a[1],b[1])/256)+1):
                    cells.setdefault((i,j),[]).append(len(spans)-1)
            start+=length;ends.append(start)
        paths.append((spans,ends,cells))
    return paths

@lru_cache(maxsize=1)
def road_cells():
    cells={}
    for direction,(_,_,by_cell) in enumerate(routes()):
        for cell in by_cell:cells.setdefault(cell,set()).add(direction)
    return cells

def vehicle_type(identity):
    value=identity%23
    return 11 if value==3 else 12 if value==7 else 5 if value%4==0 else 10

def half_length(identity):
    return {11:5.8,12:7.8}.get(vehicle_type(identity),2.2)

def point(route,at,lane):
    spans,ends,_=route
    x,z,dx,dz,start=spans[min(bisect_left(ends,at),len(spans)-1)]
    return x+dx*(at-start)+dz*lane,z+dz*(at-start)-dx*lane,math.atan2(dx,dz)

class Traffic:
    def __init__(self):
        self.cars={}
        self.offsets={}
        self.last=None
        self.horn=False
        self.visible=[]
        self.bodies={}
        self.wrecks={}
        self.taken={}
        self.impact=0.

    def update(self,x,z,age,radius,driver=None):
        dt=min(.15,max(0.,age-self.last)) if self.last is not None else 0.
        self.last=age
        visible=[];active={};offsets={}
        occupied={}
        previous=self.bodies
        space={}
        def cell(body):return math.floor(body.x/20),math.floor(body.z/20)
        def reserve(key,body):space.setdefault(cell(body),{})[key]=body
        for key,body in previous.items():reserve(key,body)
        self.bodies={}
        self.taken={key:pos for key,pos in self.taken.items() if math.dist((x,z),pos)<radius+100}
        for key,body in list(self.wrecks.items()):
            if math.hypot(x-body.x,z-body.z)>radius+100:
                del self.wrecks[key]
                continue
            body.coast(dt)
            reserve(key,body)
            identity=key[0]+key[2]
            visible.append((math.hypot(x-body.x,z-body.z),body.x,body.z,body.heading,identity,True,2))
        for key,(at,_,_) in self.cars.items():
            offset=self.offsets.get(key,(1.8,-1.8)[key[1]])
            for side,center in enumerate((1.8,-1.8)):
                if abs(offset-center)<2.2:occupied.setdefault((key[0],side),[]).append((key,at))
        nearby=[(cx,cz) for cx in range(math.floor((x-radius)/256),math.floor((x+radius)/256)+1)
                          for cz in range(math.floor((z-radius)/256),math.floor((z+radius)/256)+1)]
        directions={d for cell in nearby for d in road_cells().get(cell,())}
        for direction in sorted(directions):
            route=routes()[direction]
            spans,ends,cells=route
            indices={i for cell in nearby for i in cells.get(cell,())}
            if not indices:continue
            for lane,pace in enumerate((24.,29.) if direction<2 else (12.,)):
                home=(1.8,-1.8)[lane]
                gap=103.+lane*12 if direction<2 else 245.
                shift=age*pace+direction*32+lane*48
                ids={n for i in indices for n in range(math.ceil((spans[i][4]-shift)/gap),
                                                         math.floor((ends[i]-shift)/gap)+1)}
                ids.update(key[2] for key in self.cars if key[:2]==(direction,lane))
                leader=math.inf
                for n in sorted(ids,reverse=True):
                    key=(direction,lane,n)
                    if key in self.wrecks or key in self.taken:continue
                    at,speed,blocked=self.cars.get(key,(n*gap+shift,pace,False))
                    if not 0<=at<=ends[-1]:continue
                    lateral=self.offsets.get(key,home)
                    px,pz,angle=point(route,at,lateral)
                    distance=math.hypot(x-px,z-pz)
                    if distance>radius+30:continue
                    clearance=leader-at-half_length(n+direction)-1.
                    if driver:
                        dx,dz=driver.x-px,driver.z-pz
                        along=dx*math.sin(angle)+dz*math.cos(angle)
                        across=dx*math.cos(angle)-dz*math.sin(angle)
                        if abs(across)<2.1 and along>=0:clearance=min(clearance,along-half_length(n+direction)-2.6)
                        on_freeway=direction==1 or (route is routes()[0] and
                            corridor_path()[0][min(bisect_left(ends,at),len(ends)-1)][7]=='freeway')
                        if on_freeway and lateral==home and 12<along<38 and abs(across)<2.1:
                            adjacent=occupied.get((direction,1-lane),())
                            if all(abs(other-at)>32 for _,other in adjacent):
                                self.offsets[key]=lateral-home*.001
                    changing=lateral!=home or self.offsets.get(key,home)!=home
                    if changing:
                        target_lane=1-lane
                        neighbors=occupied.setdefault((direction,target_lane),[])
                        if all(k==key or abs(other-at)>8 for k,other in neighbors):
                            lateral+=max(-2.2*dt,min(2.2*dt,-home-lateral))
                            neighbors.append((key,at))
                        for k,other in neighbors:
                            if k!=key and other>at:clearance=min(clearance,other-at-5.)
                    offsets[key]=lateral
                    target=min(pace,math.sqrt(2*6.*max(0.,clearance-2)))
                    speed+=max(-8.*dt,min(3.*dt,target-speed))
                    at+=max(0.,min(clearance,dt*speed))
                    stopped=clearance<5
                    if driver and stopped and not blocked and distance<14:self.horn=True
                    leader=at-half_length(n+direction)
                    active[key]=(at,speed,stopped)
                    px,pz,angle=point(route,at,lateral)
                    identity=n+direction
                    kind=vehicle_type(identity)
                    body=Body(px,pz,angle,speed*math.sin(angle),speed*math.cos(angle),0.,
                              {11:10500.,12:18000.,5:2200.}.get(kind,1500.),half_length(identity),1.2 if kind in (11,12) else .95)
                    cx,cz=cell(body)
                    blocked_by_traffic=any(contact(body,other) for u in range(cx-1,cx+2)
                        for v in range(cz-1,cz+2) for k,other in space.get((u,v),{}).items() if k!=key)
                    if blocked_by_traffic:
                        if key not in previous:
                            del active[key]
                            continue
                        body=previous[key]
                        px,pz,angle=body.x,body.z,body.heading
                        active[key]=(self.cars[key][0],0.,True)
                        offsets[key]=self.offsets.get(key,home)
                        body.vx=body.vz=speed=0.
                    if key in previous:space.get(cell(previous[key]),{}).pop(key,None)
                    reserve(key,body)
                    self.bodies[key]=body
                    visible.append((distance,px,pz,angle,n+direction,speed<pace-2,
                                    (1 if home<0 else -1) if 0<abs(lateral+home)<3.6 else 0))
        self.offsets=offsets
        self.cars=active
        self.visible=sorted(visible)
        return self.visible

    def nearest_car(self,x,z):
        return min(((math.hypot(body.x-x,body.z-z),key,body)
                    for rows in (self.bodies,self.wrecks) for key,body in rows.items()),
                   key=lambda entry:entry[0],default=(math.inf,None,None))

    def take(self,key,body):
        self.taken[key]=(body.x,body.z)
        self.bodies.pop(key,None)
        self.wrecks.pop(key,None)

    def strike(self,road,previous):
        sn,cs=math.sin(road.heading),math.cos(road.heading)
        player=Body(*previous,road.heading,road.speed*sn+road.slip*cs,road.speed*cs-road.slip*sn,
                    road.spin,{11:10500.,12:18000.,5:2200.}.get(road.actor_kind,1500.),
                    {11:5.8,12:7.8}.get(road.actor_kind,2.2),.95,road.damage)
        dx,dz=road.x-player.x,road.z-player.z
        steps=max(1,math.ceil(math.hypot(dx,dz)/.7))
        for _ in range(steps):
            player.x+=dx/steps
            player.z+=dz/steps
            for key,body in (*self.bodies.items(),*self.wrecks.items()):
                impact=collide(player,body)
                if not impact:continue
                self.wrecks[key]=body
                self.bodies.pop(key,None)
                road.x,road.z=player.x,player.z
                road.speed=player.vx*sn+player.vz*cs
                road.slip=player.vx*cs-player.vz*sn
                road.spin=player.spin
                road.damage=player.damage
                self.impact=max(self.impact,min(1.,impact/18.))
                return
