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


def river_stones(channel,face,height):
    rng=random.Random(4821)
    for r in channel.rows[4::13]:
        for _ in range(3):
            side=rng.uniform(-5.4,5.4)
            x,z=r.x+side*r.nx,r.z+side*r.nz
            scale=rng.uniform(.24,.88)
            gray=rng.randrange(68,115)
            ellipsoid(face,x,r.stage-.14,z,scale,.44*scale,.72*scale,(gray,gray+4,gray+1))
    from river_channel import TROUT_POOL
    cx,cz=TROUT_POOL
    for _ in range(52):
        x,z=cx+rng.uniform(-5,5),cz+rng.uniform(-8,8)
        level=channel.water_height(x,z)
        ground=height(x,z)
        if level is None or level-ground<.25:continue
        r=rng.uniform(.08,.31)
        grey=rng.randrange(86,158)
        ellipsoid(face,x,ground,z,r,r*.48,r*.73,(grey,grey-3,grey-10))

# Loose material at the practice camp. A set of each makes one campsite.
SUPPLIES=(('stones',-4.,9.),('sticks',-10.,14.),('log',-7.,22.))

def camp_materials(height,face):
    def stones(x,z,material):
        for dx,dz in ((-.22,0.),(.1,-.19),(.18,.13)):
            ellipsoid(face,x+dx,height(x+dx,z+dz)+.08,z+dz,.21,.14,.17,(133,130,117),material)
    def wood(x,z,length,radius,material):
        rings=[]
        for side in (-1,1):
            cx=x+side*length/2
            rings.append([Vec(cx,height(cx,z)+radius*(1+math.sin(i*math.tau/8)),
                              z+radius*math.cos(i*math.tau/8)) for i in range(8)])
        for i in range(8):
            j=(i+1)%8
            a,b=rings
            face(a[i],b[i],a[j],(84,63,46),material)
            face(b[i],b[j],a[j],(102,76,51),material)
            if 0<i<7:
                for ring in rings:face(ring[0],ring[i],ring[j],(158,123,80),material)
    for i,(name,x,z) in enumerate(SUPPLIES):
        material=.60+.01*i
        if name=='stones':stones(x,z,material)
        elif name=='sticks':
            for j in range(4):wood(x+j*.15,z+j*.11,1.1-.08*j,.045,material)
        else:wood(x,z,1.65,.18,material)
    x,z=CAMP
    wood(x+1.7,z+2.,2.1,.23,.63)
    for i in range(7):
        a=i*math.tau/7
        px,pz=x+.55*math.cos(a),z+2.5+.55*math.sin(a)
        ellipsoid(face,px,height(px,pz)+.08,pz,.23,.15,.19,(117,116,104),.63)
