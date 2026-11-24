"""Illustrative forest, talus and snowmelt beside the Rainier starting meadow."""
import math
import random

from geometry import Vec


def channel(z):
    return -10 - .09*z + 1.7*math.sin(z*.11)


def shelf_height(x, z):
    """Rock lip under the falls, relative to the elevation grid."""
    flank = max(0., min(1., (8 - abs(x-channel(z)))/4))
    rise = max(0., min(1., (z-31)/1.5, (66-z)/16))
    across = x-channel(z)
    strata = .45*math.sin(across*1.7+.12*z) + .22*math.cos(.9*z-across)
    return (4.2+strata)*flank*rise


def draw_watershed(origin, height, face):
    rng = random.Random(431)
    def point(x, z, lift=0.):
        return Vec(origin.x+x, height(x,z)+shelf_height(x,z)+lift, origin.z+z)

    def strip(rows, color, material=0.):
        previous = None
        for row in rows:
            if previous:
                for i in range(len(row)-1):
                    a,b = previous[i:i+2]
                    c,d = row[i:i+2]
                    face(a,c,b,color,material)
                    face(b,c,d,color,material)
            previous = row

    # Sample the lip and the curtain at identical cross sections.
    levels = sorted({*range(8,81), 31.5, 32.5})
    strip(([point(channel(z)+dx,z,.03) for dx in range(-8,9)]
           for z in levels if 30<=z<=66), (99,101,98))
    for left,right,color in [(-1,-.60,(114,183,184)),(-.60,.65,(69,149,160)),(.65,1,(142,201,198))]:
        rows=[]
        for z in levels:
            width=1.05+.26*math.cos(z*.31)+2.1*math.exp(-((z-28)/3)**2)
            rows.append([point(channel(z)+side*width,z,.11) for side in (left,right)])
        strip(rows,color,.35)

    # Fractured blocks at the base break up the silhouette of the ledge.
    for _ in range(95):
        z=rng.uniform(27,45)
        side=rng.choice((-1,1))
        x=channel(z)+side*rng.uniform(1.6,8.4)
        size=rng.uniform(.25,1.1)
        base=[point(x+size*math.cos(i*math.tau/5),z+size*math.sin(i*math.tau/5),.04)
              for i in range(5)]
        top=point(x+size*.25,z,.2+size*.85)
        tone=rng.randrange(80,130)
        for i,p in enumerate(base):
            face(p,top,base[(i+1)%5],(tone,tone*.98,tone*.9))

    # Overlapping lobes of dirty, lingering snow feed the upper channel.
    for offset,start,end,width in [(0,61,86,3.3),(-3,70,101,4.7),(2,78,106,3.9)]:
        rows=[]
        for z in range(start,end+1):
            profile=math.sin(math.pi*(z-start+.3)/(end-start+.6))**.65
            rows.append([point(channel(z)+offset+t*width*profile,z,.16+(1-abs(t))*.87*profile)
                         for t in (-1,0,1)])
        strip(rows,(196+int(width)*3,218,219))

    # A narrow head scarp widens into a fan of angular volcanic debris.
    rows=[]
    for z in range(23,81,2):
        t=(z-23)/57
        center=13+.22*z+2*math.sin(z*.10)
        width=1.4+7.2*(1-t)**.66
        rows.append([point(center+u*width*rng.uniform(.91,1.09),z,.09)
                     for u in (-1,-.45,0,.45,1)])
    strip(rows,(140,119,101))
    for _ in range(240):
        z=rng.uniform(23,79)
        x=13+.22*z+2*math.sin(z*.10)+rng.uniform(-1,1)*(1.4+7.2*((80-z)/57)**.66)
        size=rng.uniform(.13,.9)
        base=[point(x+size*math.cos(i*math.tau/5),z+size*.7*math.sin(i*math.tau/5),.08)
              for i in range(5)]
        top=point(x+.21*size,z,size*.8+.1)
        tone=rng.randrange(92,159)
        for i,p in enumerate(base):
            face(p,top,base[(i+1)%5],(tone,tone*.95,tone*.89))


def forest_sites(rng):
    """Jittered stands, with compact crowns for the more distant trees."""
    for extent,step,inner in ((90,5,0),(260,11,90),(700,28,260)):
        for iz in range(-extent,extent,step):
            for ix in range(-extent,extent,step):
                x=ix+rng.random()*step
                z=iz+rng.random()*step
                distance=math.hypot(x,z)
                if not inner<=distance<extent or distance<14:continue
                # The clearing narrows uphill, opening onto a continuous wood.
                if 0<z<85 and -17-.09*z<x<7+.04*z:continue
                if 5<z<108 and abs(x-channel(z))<9:continue
                if 20<z<83 and abs(x-(13+.22*z))<11:continue
                if rng.random()<.19+.14*math.sin(.08*x+.06*z):continue
                yield x,z,rng.uniform(4,20),distance<65
