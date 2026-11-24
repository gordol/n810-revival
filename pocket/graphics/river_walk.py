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
BUSHES=((-1.,5.),(2.,10.),(-1.,16.))
FOX=(-2.,22.)


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


def wet(x,z,segments,margin=0.):
    radius=8.+margin
    for a,b,u,v,length in segments:
        t=max(0.,min(length,(x-a)*u+(z-b)*v))
        if (x-a-t*u)**2+(z-b-t*v)**2<radius**2:return True
    return False


def river_mesh(segments,height,face):
    # NHD supplies the centerline. Width and the gravel margins are illustrative.
    for x,z,u,v,length in segments:
        count=math.ceil(length/3)
        previous=None
        for i in range(count+1):
            t=length*i/count
            a,b=x+t*u,z+t*v
            row=[]
            for side in (-8,-6,0,6,8):
                px,pz=a+side*v,b-side*u
                row.append(Vec(px,height(px,pz)+(.14 if abs(side)<8 else .06),pz))
            if previous:
                for j in range(4):
                    water=j in (1,2)
                    color=(52,132,131) if water else (142,137,119)
                    for tri in ((previous[j],row[j],previous[j+1]),(previous[j+1],row[j],row[j+1])):
                        face(*tri,color,.35 if water else 0.)
            previous=row


def blueberry_patch(x,z,height,face,rng,material,high=True):
    for _ in range(20):
        a=rng.random()*math.tau
        r=rng.uniform(.15,.68)
        cx,cz=x+r*math.cos(a),z+r*math.sin(a)
        y=height(cx,cz)+rng.uniform(.38,.70)
        branch=Vec(cx,y,cz)
        face(Vec(x-.025,height(x,z),z),Vec(x+.025,height(x,z),z+.02),branch,(106,76,54))
        foot=Vec(x,height(x,z),z)
        for k in range(1,7):
            t=k/7
            stalk=Vec(foot.x+(cx-foot.x)*t,foot.y+(y-foot.y)*t,foot.z+(cz-foot.z)*t)
            angle=a+2.4*k
            blade(stalk,angle,rng.uniform(.09,.16),rng.uniform(.029,.051),
                  rng.uniform(.008,.045),(55+4*k,111+4*k,54),face,serrated=True)
        # Plump blue clusters with a dark calyx, enlarged for a small screen.
        for offset in (0.,.059):
            bx=cx+offset;by=y+.045-offset*.35
            face(branch,Vec(cx+.012,y+.015,cz+.007),Vec(bx,by,cz),(108,106,66))
            rings=[]
            sides=24 if high else 9
            bands=12 if high else 4
            for k in range(bands+1):
                lat=-math.pi/2+math.pi*k/bands
                rings.append([Vec(bx+.041*math.cos(lat)*math.cos(i*math.tau/sides),
                                  by+.038*math.sin(lat),cz+.041*math.cos(lat)*math.sin(i*math.tau/sides))
                              for i in range(sides)])
            for band,(lo,hi) in enumerate(zip(rings,rings[1:])):
                color=((57,69,128),(71,92,165),(94,119,191),(94,109,167))[band*4//bands]
                for i,p in enumerate(lo):
                    j=(i+1)%sides
                    if band:face(p,hi[i],lo[j],color,material)
                    if band+1<bands:face(lo[j],hi[i],hi[j],color,material)
            if high:
                crown=Vec(bx,by+.0388,cz)
                for j in range(5):
                    a=j*math.tau/5
                    face(crown,Vec(bx+.013*math.cos(a),by+.038,cz+.013*math.sin(a)),
                         Vec(bx+.006*math.cos(a+.7),by+.039,cz+.006*math.sin(a+.7)),
                         (52,65,108),material)
