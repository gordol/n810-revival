"""Local traffic on the mapped northbound and southbound Seattle–Tacoma routes."""
from bisect import bisect_left
from functools import lru_cache
import math
from pnw.seattle_places import corridor_path, freeway_data
from pnw.terrain import location

@lru_cache(maxsize=1)
def routes():
    south=[(s[1],s[2]) for s in corridor_path()[0]]
    last=corridor_path()[0][-1]
    south.append((last[1]+last[3]*last[5],last[2]+last[4]*last[5]))
    north=[location('sound',lat/1e7,lon/1e7) for lon,lat in freeway_data()['north']]
    paths=[]
    for points in (south,north):
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

def point(route,at,lane):
    spans,ends,_=route
    x,z,dx,dz,start=spans[min(bisect_left(ends,at),len(spans)-1)]
    return x+dx*(at-start)+dz*lane,z+dz*(at-start)-dx*lane,math.atan2(dx,dz)

class Traffic:
    def __init__(self):
        self.cars={}
        self.last=None
        self.horn=False
        self.visible=[]

    def update(self,x,z,age,radius,driver=None):
        dt=min(.15,max(0.,age-self.last)) if self.last is not None else 0.
        self.last=age
        visible=[];active={}
        for direction,route in enumerate(routes()):
            spans,ends,cells=route
            indices={i for cx in range(math.floor((x-radius)/256),math.floor((x+radius)/256)+1)
                       for cz in range(math.floor((z-radius)/256),math.floor((z+radius)/256)+1)
                       for i in cells.get((cx,cz),())}
            if not indices:continue
            for lane,pace in enumerate((24.,29.)):
                lateral=(1.8,-1.8)[lane]
                gap=103.+lane*12
                shift=age*pace+direction*32+lane*48
                ids={n for i in indices for n in range(math.ceil((spans[i][4]-shift)/gap),
                                                         math.floor((ends[i]-shift)/gap)+1)}
                ids.update(key[2] for key in self.cars if key[:2]==(direction,lane))
                leader=math.inf
                for n in sorted(ids,reverse=True):
                    key=(direction,lane,n)
                    at,speed,blocked=self.cars.get(key,(n*gap+shift,pace,False))
                    if not 0<=at<=ends[-1]:continue
                    px,pz,angle=point(route,at,lateral)
                    distance=math.hypot(x-px,z-pz)
                    if distance>radius+30:continue
                    clearance=leader-at-5.
                    if driver:
                        dx,dz=driver.x-px,driver.z-pz
                        along=dx*math.sin(angle)+dz*math.cos(angle)
                        across=dx*math.cos(angle)-dz*math.sin(angle)
                        if abs(across)<1.95 and along>=0:clearance=min(clearance,along-4.8)
                    target=min(pace,math.sqrt(2*6.*max(0.,clearance-2)))
                    speed+=max(-8.*dt,min(3.*dt,target-speed))
                    at+=max(0.,min(clearance,dt*speed))
                    stopped=clearance<5
                    if driver and stopped and not blocked and distance<14:self.horn=True
                    leader=at
                    active[key]=(at,speed,stopped)
                    px,pz,angle=point(route,at,lateral)
                    visible.append((distance,px,pz,angle,n+direction,speed<pace-2))
        self.cars=active
        self.visible=sorted(visible)
        return self.visible

    def contact(self,x,z):
        for _,px,pz,angle,*_ in self.visible:
            dx,dz=x-px,z-pz
            if (abs(dx*math.sin(angle)+dz*math.cos(angle))<4.3 and
                abs(dx*math.cos(angle)-dz*math.sin(angle))<1.85):return True
        return False
