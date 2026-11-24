"""Offline Ohanapecosh terrain, mapped river and the blueberry trail."""
from array import array
from functools import lru_cache
import json
import math
from pathlib import Path
import sys
import zlib

from geometry import HeightField, Vec
from forest_floor import blade

ASSETS=Path(__file__).parent/'assets'/'ohanapecosh'
BUSHES=((-13.,5.),(-27.,42.),(-11.,82.))
FOX=(-40.,113.)
BERRY_BLUFF=(56.,56.)


class BerryTrail:
    def __init__(self):
        self.picked=set()
        self.fed=False
        self.guiding=False
        self.free_look=False

    def target(self,x,z):
        return min((p for p in BUSHES if p not in self.picked),
                   key=lambda p:math.hypot(x-p[0],z-p[1]),default=FOX)

    def visit(self,x,z):
        if self.fed:return
        target=self.target(x,z)
        if math.hypot(x-target[0],z-target[1])>2.2:return
        if target==FOX:self.fed=True
        else:self.picked.add(target)
        self.guiding=False

    def advance(self,owner,dt,local_pick=True):
        if self.guiding and not self.fed:
            x,z=self.target(owner.x,owner.z)
            dx,dz=x-owner.x,z-owner.z
            heading=math.atan2(dx,dz)
            turn=math.remainder(heading-owner.yaw,math.tau)
            if not self.free_look:owner.yaw+=max(-2.5*dt,min(2.5*dt,turn))
            if self.free_look or abs(turn)<.4:
                step=min(3.2*dt,math.hypot(dx,dz))
                owner.x+=step*math.sin(heading)
                owner.z+=step*math.cos(heading)
        arriving=self.guiding and not self.fed
        if local_pick:self.visit(owner.x,owner.z)
        if arriving and self.fed:
            owner.yaw=math.atan2(FOX[0]-owner.x,FOX[1]-owner.z)
            owner.pitch=.38


@lru_cache(maxsize=1)
def site():
    data=json.loads((ASSETS/'site.json').read_text())
    heights=array('h')
    heights.frombytes(zlib.decompress((ASSETS/'ground.i16.zlib').read_bytes()))
    if sys.byteorder!='little':heights.byteswap()
    n=data['size'];step=data['spacing_m'];radius=(n-1)*step/2
    if len(heights)!=n*n:raise ValueError('Ohanapecosh terrain is incomplete')
    field=HeightField(n,n,Vec(-radius,0,-radius),step,step,tuple(h/10 for h in heights),'meters')
    segments=[]
    for reach in data['river']:
        for (x,z),(ex,ez) in zip(reach['xz'],reach['xz'][1:]):
            dx,dz=ex-x,ez-z
            length=math.hypot(dx,dz)
            if length:segments.append((x,z,dx/length,dz/length,length))
    return field,segments


def centerline_distances_sq(x,z,segments):
    for a,b,u,v,length in segments:
        t=max(0.,min(length,(x-a)*u+(z-b)*v))
        yield (x-a-t*u)**2+(z-b-t*v)**2


def wet(x,z,segments,margin=0.):
    radius_sq=(8.+margin)**2
    return any(d<radius_sq for d in centerline_distances_sq(x,z,segments))


def river_gain(x,z,segments):
    nearest=min(centerline_distances_sq(x,z,segments),default=math.inf)
    bank_distance=max(0.,math.sqrt(nearest)-8.)
    # Broad valley ambience: half the bank amplitude at 160 metres.
    return 160./(160.+bank_distance)


@lru_cache(maxsize=1)
def channel():
    from river_channel import RiverChannel
    field,segments=site()
    return RiverChannel(field,segments)


def blueberry_patch(x,z,height,face,rng,material,high=True):
    lean=rng.uniform(-.32,.32)
    width=rng.uniform(.76,1.28)
    for _ in range(rng.randint(15,20)):
        a=rng.random()*math.tau
        r=rng.uniform(.15,.68)
        cx,cz=x+r*width*math.cos(a)+lean,z+r*math.sin(a)
        y=height(cx,cz)+rng.uniform(.38,.70)
        branch=Vec(cx,y,cz)
        face(Vec(x-.025,height(x,z),z),Vec(x+.025,height(x,z),z+.02),branch,(106,76,54))
        foot=Vec(x,height(x,z),z)
        for k in range(1,7):
            t=k/7
            stalk=Vec(foot.x+(cx-foot.x)*t,foot.y+(y-foot.y)*t,foot.z+(cz-foot.z)*t)
            angle=a+2.4*k+rng.uniform(-.4,.4)
            blade(stalk,angle,rng.uniform(.09,.16),rng.uniform(.029,.051),
                  rng.uniform(.008,.045),(55+4*k,111+4*k,54),face,serrated=True)
        # Plump blue clusters with a dark calyx, enlarged for a small screen.
        for offset in (0.,rng.uniform(.044,.073)):
            bx=cx+offset*math.cos(a);by=y+.045-offset*.35
            bz=cz+offset*math.sin(a)
            face(branch,Vec(cx+.012,y+.015,cz+.007),Vec(bx,by,bz),(108,106,66))
            rings=[]
            sides=24 if high else 9
            bands=12 if high else 4
            for k in range(bands+1):
                lat=-math.pi/2+math.pi*k/bands
                rings.append([Vec(bx+.041*math.cos(lat)*math.cos(i*math.tau/sides),
                                  by+.038*math.sin(lat),bz+.041*math.cos(lat)*math.sin(i*math.tau/sides))
                              for i in range(sides)])
            for band,(lo,hi) in enumerate(zip(rings,rings[1:])):
                color=((57,69,128),(71,92,165),(94,119,191),(94,109,167))[band*4//bands]
                for i,p in enumerate(lo):
                    j=(i+1)%sides
                    if band:face(p,hi[i],lo[j],color,material)
                    if band+1<bands:face(lo[j],hi[i],hi[j],color,material)
            if high:
                crown=Vec(bx,by+.0388,bz)
                for j in range(5):
                    a=j*math.tau/5
                    face(crown,Vec(bx+.013*math.cos(a),by+.038,bz+.013*math.sin(a)),
                         Vec(bx+.006*math.cos(a+.7),by+.039,bz+.006*math.sin(a+.7)),
                         (52,65,108),material)


# Short illustrative calls and their audible radii in game metres.
CALLS={'american_crow':(1,50.),'common_raven':(1,60.),'barred_owl':(2,65.),
       'great_horned_owl':(2,70.),'american_dipper':(3,32.),'pika':(3,24.),
       'chipmunk':(4,18.),'squirrel':(4,24.),'marmot':(3,45.)}


def nearby_calls(subjects,x,y,z):
    voices=[]
    for key,px,py,pz,_ in subjects:
        species=key.split('#')[0]
        if species in CALLS:
            voice,radius=CALLS[species]
            gain=1.-math.dist((x,y,z),(px,py,pz))/radius
            if gain>0:voices.append((key,voice,gain))
    return sorted(voices)

@lru_cache(maxsize=1)
def hiking_paths():
    return json.loads((ASSETS/'trails.json').read_text())['paths']


def hiking_segments():
    for path in hiking_paths():
        for (x,z),(ex,ez) in zip(path['xz'],path['xz'][1:]):
            length=math.hypot(ex-x,ez-z)
            if length:yield x,z,(ex-x)/length,(ez-z)/length,length


def trail_surface(height,face):
    for x,z,u,v,length in hiking_segments():
        steps=math.ceil(length/1.8)
        previous=None
        for j in range(steps+1):
            px,pz=x+u*length*j/steps,z+v*length*j/steps
            if channel().water_height(px,pz) is not None:
                previous=None
                continue
            left,right=(Vec(px+s*v,height(px+s*v,pz-s*u)+.085,pz-s*u) for s in (-.9,.9))
            if previous:
                a,b=previous
                face(a,b,left,(133,109,79),.53)
                face(left,b,right,(133,109,79),.53)
            previous=left,right
