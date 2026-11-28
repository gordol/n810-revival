"""Local traffic on the mapped northbound and southbound Seattle–Tacoma routes."""
from bisect import bisect_left
from functools import lru_cache
import math
from pnw.seattle_places import corridor_path, freeway_data, freeway_lines, street_lines
from pnw.terrain import location
from pnw.vehicle_impact import Body, collide, contact

@lru_cache(maxsize=1)
def highway_geometry():
    """Index the directed OSM pavement used to draw the freeway."""
    nodes={}
    widths={}
    for _,_,points,half,_ in freeway_lines():
        for index,p in enumerate(points):
            nodes.setdefault((round(p[0]),round(p[1])),[]).append((points,index))
        for a,b in zip(points,points[1:]):
            widths[a,b]=round((half-.6)/1.8)
    return nodes,widths


def pavement_path(points):
    # The bundled itinerary rounds coordinates and simplifies bends. Restore
    # intermediate road vertices before placing traffic on either carriageway.
    nodes,_=highway_geometry()
    def matches(p):
        x,z=map(round,p)
        return [(way,i) for u in range(x-1,x+2) for v in range(z-1,z+2)
                for way,i in nodes.get((u,v),()) if math.dist(way[i],p)<.25]
    result=[]
    prev=matches(points[0])
    result.append(prev[0][0][prev[0][1]] if prev else points[0])
    for p in points[1:]:
        curr=matches(p)
        part=next((way[i+1:j+1] for way,i in prev for other,j in curr if way is other and i<j),None)
        result.extend(part or [curr[0][0][curr[0][1]] if curr else p])
        prev=curr
    return result


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
    return [make_route(points,highways=True) for points in (pavement_path(south),pavement_path(north),*extras)]


def make_route(points,highways=False):
    widths=highway_geometry()[1] if highways else {}
    spans=[];ends=[];cells={};start=0.
    for a,b in zip(points,points[1:]):
        length=math.dist(a,b)
        if length<.01:continue
        spans.append((*a,(b[0]-a[0])/length,(b[1]-a[1])/length,start,widths.get((a,b),0)))
        for i in range(math.floor(min(a[0],b[0])/256),math.floor(max(a[0],b[0])/256)+1):
            for j in range(math.floor(min(a[1],b[1])/256),math.floor(max(a[1],b[1])/256)+1):
                cells.setdefault((i,j),[]).append(len(spans)-1)
        start+=length;ends.append(start)
    return spans,ends,cells


@lru_cache(maxsize=1024)
def mapped_paths(way,directions,blob):
    import json,zlib
    points=json.loads(zlib.decompress(blob))
    return [make_route(points if i==0 else points[::-1]) for i in range(directions)]


@lru_cache(maxsize=96)
def traffic_tile(path,tx,tz):
    import sqlite3
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='traffic_cells'").fetchone():return ()
        result=[]
        for way,dirs,blob in db.execute('SELECT way,directions,points FROM traffic_cells JOIN traffic_paths USING(way) WHERE tx=? AND tz=?',(tx,tz)):
            for i,route in enumerate(mapped_paths(way,dirs,blob)):
                result.append((10000000+2*way+i,route))
        return result


@lru_cache(maxsize=1)
def road_cells():
    cells={}
    for direction,(_,_,by_cell) in enumerate(routes()):
        for cell in by_cell:cells.setdefault(cell,set()).add(direction)
    return cells

def vehicle_type(identity):
    if identity%67==39:return 9  # occasional marked cruiser on ordinary routes
    if identity%19==12:return 17  # pickup
    if identity%29==13:return 18  # electric
    if identity%43==14:return 19  # motorbike
    value=identity%23
    if value==3:return 11  # bus
    if value==7:return 12  # tractor-trailer
    if value==18:return 10  # sports coupe
    if value in (0,9,15):return 5  # delivery van
    return 14 if value%2 else 15  # sedan or crossover

def half_length(identity):
    return {11:5.8,12:7.8,17:2.6,19:1.02}.get(vehicle_type(identity),2.2)

def point(route,at,lane):
    spans,ends,_=route
    x,z,dx,dz,start,lanes=spans[min(bisect_left(ends,at),len(spans)-1)]
    if lanes:
        # Route streams use the two rightmost lanes; one-lane links merge
        # both streams onto their centre. Keep a stopped vehicle inside it.
        outer=(lanes-1)*1.8
        lane=max(-outer,min(outer,lane+outer-1.8))
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

    def update(self,x,z,age,radius,driver=None,lane_height=None,parked=(),pedestrian=None,signals=()):
        first_frame=self.last is None
        dt=min(.15,max(0.,age-self.last)) if self.last is not None else 0.
        self.last=age
        visible=[];active={};offsets={}
        occupied={}
        previous=self.bodies
        space={}
        def cell(body):return math.floor(body.x/20),math.floor(body.z/20)
        def reserve(key,body):space.setdefault(cell(body),{})[key]=body
        for key,body in previous.items():reserve(key,body)
        if pedestrian:reserve("walker",pedestrian)
        for index,body in enumerate(parked):reserve(('parked',index),body)
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
        from pnw.regional_scenery import database_path
        network={d:routes()[d] for d in directions}
        path=database_path().resolve()
        for i,j in {(cx//2,cz//2) for cx,cz in nearby}:
            network.update(traffic_tile(path,i,j))
        for direction,route in sorted(network.items()):
            spans,ends,cells=route
            indices={i for cell in nearby for i in cells.get(cell,())}
            if not indices:continue
            for lane,pace in enumerate((24.,29.) if direction<2 else (12.,)):
                home=(1.8,-1.8)[lane]
                gap=69.+lane*11 if direction<2 else 156.
                shift=age*pace+(direction%4096)*32+lane*48
                ids={n for i in indices for n in range(math.ceil((spans[i][4]-shift)/gap),
                                                         math.floor((ends[i]-shift)/gap)+1)}
                ids.update(key[2] for key in self.cars if key[:2]==(direction,lane))
                leader=math.inf
                for n in sorted(ids,reverse=True):
                    key=(direction,lane,n)
                    if key in self.wrecks or key in self.taken:continue
                    at,speed,blocked=self.cars.get(key,(n*gap+shift,pace,False))
                    if not 0<=at<=ends[-1]:continue
                    if lane and key not in previous and spans[bisect_left(ends,at)][5]==1:continue
                    lateral=self.offsets.get(key,home)
                    px,pz,angle=point(route,at,lateral)
                    distance=math.hypot(x-px,z-pz)
                    if distance>radius+30:continue
                    if not first_frame and key not in previous and distance<42:continue
                    clearance=leader-at-half_length(n+direction)-1.
                    obstacle=driver or pedestrian
                    py=lane_height(px,pz,angle) if lane_height else 0.
                    for lx,lz,bearing,red,height in signals:
                        if abs(py-height)>2.5:continue
                        aligned=abs(math.cos(bearing-angle))>.707
                        if aligned!=red:continue
                        dx,dz=lx-px,lz-pz
                        along=dx*math.sin(angle)+dz*math.cos(angle)
                        across=dx*math.cos(angle)-dz*math.sin(angle)
                        if 0<along<85 and abs(across)<6.5:clearance=min(clearance,along-half_length(n+direction)-1.8)
                    if obstacle and (not pedestrian or abs(py-pedestrian.elevation)<2.7):
                        dx,dz=obstacle.x-px,obstacle.z-pz
                        along=dx*math.sin(angle)+dz*math.cos(angle)
                        across=dx*math.cos(angle)-dz*math.sin(angle)
                        if abs(across)<2.1 and along>=0:clearance=min(clearance,along-half_length(n+direction)-2.6)
                        on_freeway=direction<2 and spans[bisect_left(ends,at)][5]>=2
                        if driver and on_freeway and lateral==home and 12<along<38 and abs(across)<2.1:
                            adjacent=occupied.get((direction,1-lane),())
                            if all(abs(other-at)>32 for _,other in adjacent):
                                self.offsets[key]=lateral-home*.001
                    changing=lateral!=home or self.offsets.get(key,home)!=home
                    pulling_over=driver is not None and getattr(driver,'stop_target',None)==key
                    if pulling_over:
                        lateral+=max(0.,min(2.8-lateral,dt*.9))
                    elif changing:
                        target_lane=1-lane
                        neighbors=occupied.setdefault((direction,target_lane),[])
                        if all(k==key or abs(other-at)>8 for k,other in neighbors):
                            lateral+=max(-2.2*dt,min(2.2*dt,-home-lateral))
                            neighbors.append((key,at))
                        for k,other in neighbors:
                            if k!=key and other>at:clearance=min(clearance,other-at-5.)
                    offsets[key]=lateral
                    target=min(pace,math.sqrt(2*6.*max(0.,clearance-2)))
                    if pulling_over:target=0.
                    speed+=max(-8.*dt,min(3.*dt,target-speed))
                    at+=max(0.,min(clearance,dt*speed))
                    stopped=clearance<5
                    if obstacle and stopped and not blocked and distance<14:self.horn=True
                    leader=at-half_length(n+direction)
                    active[key]=(at,speed,stopped)
                    px,pz,angle=point(route,at,lateral)
                    identity=n+direction
                    kind=vehicle_type(identity)
                    body=Body(px,pz,angle,speed*math.sin(angle),speed*math.cos(angle),0.,
                              {11:10500.,12:18000.,5:2200.,17:2250.,18:1950.,19:260.}.get(kind,1500.),half_length(identity),.36 if kind==19 else 1.2 if kind in (11,12) else .95)
                    cx,cz=cell(body)
                    body.elevation=lane_height(px,pz,angle) if lane_height else py
                    blocked_by_traffic=any(abs(body.elevation-other.elevation)<2.7 and contact(body,other) for u in range(cx-1,cx+2)
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
        if driver and getattr(driver,"stop_target",None) not in active:driver.stop_target=None
        self.visible=sorted(visible)
        return self.visible

    def car_ahead(self,road,elevation):
        sn,cs=math.sin(road.heading),math.cos(road.heading)
        choices=[]
        for key,body in self.bodies.items():
            dx,dz=body.x-road.x,body.z-road.z
            along=dx*sn+dz*cs
            if (0<along<65 and abs(dx*cs-dz*sn)<3.5 and abs(elevation-body.elevation)<2.7
                    and math.cos(road.heading-body.heading)>.75):
                choices.append((along,key))
        return min(choices)[1] if choices else None

    def nearest_car(self,x,z):
        return min(((min(math.hypot(u-x,v-z) for u,v in body.discs())-body.radius,key,body)
                    for rows in (self.bodies,self.wrecks) for key,body in rows.items()),
                   key=lambda entry:entry[0],default=(math.inf,None,None))

    def separate_walker(self,x,z,elevation):
        for body in (*self.bodies.values(),*self.wrecks.values()):
            if abs(elevation-body.elevation)>2.7 or math.hypot(x-body.x,z-body.z)>body.length+1.5:continue
            sn,cs=math.sin(body.heading),math.cos(body.heading)
            dx,dz=x-body.x,z-body.z
            side,along=dx*cs-dz*sn,dx*sn+dz*cs
            width,length=body.radius+.32,body.length+.32
            if abs(side)>=width or abs(along)>=length:continue
            if width-abs(side)<length-abs(along):side=math.copysign(width,side)
            else:along=math.copysign(length,along)
            x,z=body.x+side*cs+along*sn,body.z-side*sn+along*cs
        return x,z

    def take(self,key,body):
        self.taken[key]=(body.x,body.z)
        self.bodies.pop(key,None)
        self.wrecks.pop(key,None)

    def strike(self,road,previous,elevation=None,damage=True):
        sn,cs=math.sin(road.heading),math.cos(road.heading)
        player=Body(*previous,road.heading,road.speed*sn+road.slip*cs,road.speed*cs-road.slip*sn,
                    road.spin,{11:10500.,12:18000.,5:2200.,17:2250.,18:1950.,19:260.}.get(road.actor_kind,1500.),
                    {11:5.8,12:7.8,17:2.6,19:1.02}.get(road.actor_kind,2.2),.36 if road.actor_kind==19 else .95,road.damage)
        dx,dz=road.x-player.x,road.z-player.z
        steps=max(1,math.ceil(math.hypot(dx,dz)/.7))
        for _ in range(steps):
            player.x+=dx/steps
            player.z+=dz/steps
            for key,body in (*self.bodies.items(),*self.wrecks.items()):
                if elevation is not None and abs(elevation-body.elevation)>2.7:continue
                if contact(player,body) is None:continue
                old_damage=body.damage
                impact=collide(player,body)
                if not damage:body.damage=old_damage
                self.wrecks[key]=body
                self.bodies.pop(key,None)
                road.x,road.z=player.x,player.z
                road.speed=player.vx*sn+player.vz*cs
                road.slip=player.vx*cs-player.vz*sn
                road.spin=player.spin
                if damage:road.damage=player.damage
                self.impact=max(self.impact,min(1.,impact/18.))
                return
