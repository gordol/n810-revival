"""Illustrative campsite, campfire legend and water-worn river stones."""
import math
import random
from geometry import Vec

CAMP=(-6.,15.)
LEGEND=(-11.,29.)
OVERLOOK=(516.,544.,596.,537.)


def ellipsoid(face,x,y,z,rx,ry,rz,color,material=0.,lean=0.):
    count=10
    rings=[]
    for j in range(6):
        lat=-math.pi/2+j*math.pi/5
        rings.append([Vec(x+rx*math.cos(lat)*math.cos(i*math.tau/count)+lean*math.sin(lat),
                          y+ry*math.sin(lat),z+rz*math.cos(lat)*math.sin(i*math.tau/count))
                      for i in range(count)])
    for j,(a,b) in enumerate(zip(rings,rings[1:])):
        for i in range(count):
            k=(i+1)%count
            if j:face(a[i],b[i],a[k],color,material)
            if j<4:face(a[k],b[i],b[k],color,material)


def campsite(height,face):
    x,z=CAMP
    def foot(dx,dz):return Vec(x+dx,height(x+dx,z+dz)+.02,z+dz)
    for side in (-1,1):
        near,far=foot(side*1.15,-1.4),foot(side*1.15,1.4)
        a,b=foot(0,-1.4),foot(0,1.4)
        top=Vec(a.x,a.y+1.48,a.z);end=Vec(b.x,b.y+1.48,b.z)
        face(near,top,far,(191,112,52),.57);face(far,top,end,(204,130,65),.57)
        face(far,end,b,(159,94,49),.57)
        flap=foot(side*.38,-1.4)
        face(near,flap,top,(171,100,48),.57)
        face(flap,a,top,(46,48,38),.57)

    x,z=LEGEND
    y=height(x,z)
    fur=(79,57,43)
    for side in (-1,1):
        ellipsoid(face,x+side*.20,y+.51,z,.18,.53,.21,fur,.59)
        ellipsoid(face,x+side*.48,y+1.15,z,.17,.63,.18,fur,.59,-side*.12)
    ellipsoid(face,x,y+1.33,z,.49,.66,.28,fur,.59)
    ellipsoid(face,x,y+2.01,z,.24,.30,.22,(85,64,46),.59)
    ellipsoid(face,x,y+1.99,z-.17,.17,.14,.09,(112,88,65),.59)


def river_stones(channel,face):
    rng=random.Random(4821)
    for r in channel.rows[4::13]:
        for _ in range(3):
            side=rng.uniform(-5.4,5.4)
            x,z=r.x+side*r.nx,r.z+side*r.nz
            scale=rng.uniform(.24,.88)
            gray=rng.randrange(68,115)
            ellipsoid(face,x,r.stage-.14,z,scale,.44*scale,.72*scale,(gray,gray+4,gray+1))
