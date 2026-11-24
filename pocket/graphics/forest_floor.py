"""Folded and toothed foliage for the near field of the walking camera."""
import math
from geometry import Vec


def blade(base,angle,length,width,rise,color,face,serrated=False,steps=7):
    """Taper both ends around a raised midrib and a recurved tip."""
    u,v=math.cos(angle),math.sin(angle)
    old=None
    if serrated:steps=12
    for i in range(steps+1):
        t=i/steps
        profile=math.sin(math.pi*t)**.78
        half=width*profile*(.85 if serrated and i%2 else 1.)
        y=base.y+rise*t+length*.17*math.sin(math.pi*t)
        x,z=base.x+length*u*t,base.z+length*v*t
        row=(Vec(x-v*half,y,z+u*half),Vec(x,y+width*.24*profile,z),Vec(x+v*half,y,z-u*half))
        if old:
            for j,tone in enumerate((color,tuple(c*.86 for c in color))):
                if i>1:face(old[j],row[j],old[j+1],tone)
                if i<steps:face(old[j+1],row[j],row[j+1],tone)
        old=row


def fern(x,z,y,size,face,rng):
    arms=rng.randint(4,8)
    rotation=rng.uniform(0,math.tau)
    for arm in range(arms):
        a=rotation+(arm+rng.uniform(-.35,.35))*math.tau/arms
        length=size*rng.uniform(.65,1.05)
        u,v=math.cos(a),math.sin(a)
        arch=rng.uniform(.38,.72)
        previous=Vec(x,y,z)
        for i in range(1,10):
            t=i/10
            p=Vec(x+u*t*length,y+length*(arch*math.sin(t*2.45)+.10*t),z+v*t*length)
            edge=Vec(p.x-.009*v,p.y,p.z+.009*u)
            face(previous,p,edge,(109,122,61))
            for side in (-1,1):
                span=length*(.21*math.sin(t*math.pi)**.62+.025)*rng.uniform(.72,1.1)
                blade(p,a+side*(1.12-.36*t),span,.16*span,.025,(53+i,99+i*2,56),face,steps=4)
            previous=p


def broadleaf_clump(x,y,z,height,color,face,rng):
    """Branching understory with offset, folded leaves of different ages."""
    for _ in range(rng.randint(3,6)):
        heading=rng.uniform(0,math.tau)
        u,v=math.cos(heading),math.sin(heading)
        reach=height*rng.uniform(.45,1.)
        tip=Vec(x+u*reach,y+height*rng.uniform(.65,1.25),z+v*reach)
        face(Vec(x-.012,y,z),Vec(x+.012,y,z),tip,(106,89,60))
        for i in range(1,6):
            t=i/6
            base=Vec(x+(tip.x-x)*t,y+(tip.y-y)*t,z+(tip.z-z)*t)
            a=heading+(-1 if i%2 else 1)*rng.uniform(.65,1.65)
            dx,dz=math.cos(a),math.sin(a)
            length=height*rng.uniform(.30,.56)
            mid=Vec(base.x+.52*length*dx,base.y+.19*length,base.z+.52*length*dz)
            end=Vec(base.x+length*dx,base.y+.08*length,base.z+length*dz)
            for side in (-1,1):
                width=side*.21*length
                edge=Vec(mid.x-dz*width,mid.y-.05*length,mid.z+dx*width)
                face(base,mid,edge,color)
                face(mid,end,edge,color)


def snag(x,y,z,height,face):
    """A broken snag with a sloped crown and one level landing spot."""
    sides=9
    rings=[]
    for dy,radius in ((-.07,.30),(.19,.21),(height*.65,.13),(height,.10)):
        rings.append([Vec(x+radius*math.cos(a*math.tau/sides),y+dy+(0 if dy!=height or a<4 else .12),
                          z+radius*math.sin(a*math.tau/sides)) for a in range(sides)])
    for lower,upper in zip(rings,rings[1:]):
        for i,p in enumerate(lower):
            j=(i+1)%sides
            color=(98+i%3*10,87+i%3*9,70+i%3*5)
            face(p,upper[i],lower[j],color)
            face(upper[i],upper[j],lower[j],color)
    for i,p in enumerate(rings[-1]):face(p,Vec(x,y+height,z),rings[-1][i-1],(162,138,100))


def spruce_sprays(x,y,z,h,t,angle,needles,face,rng):
    """Layered lateral shoots on the outer silhouette of nearby conifers."""
    shoots=rng.randint(5,9)
    for j in range(shoots):
        a=angle+(j+rng.uniform(-.38,.38))*math.tau/shoots
        u,v=math.cos(a),math.sin(a)
        reach=h*(.24-.19*t)*rng.uniform(.65,1.18)
        for k in range(1,5):
            f=k/5
            bx,bz=x+reach*f*u,z+reach*f*v
            by=y+h*(.30+.66*t)-reach*f*.37
            tip=Vec(bx+reach*.42*u,by-reach*.06,bz+reach*.42*v)
            for side in (-1,1):
                width=reach*(1-f*.75)*.24*side
                edge=Vec(bx-width*v+reach*.15*u,by-reach*.12,bz+width*u+reach*.15*v)
                mid=Vec(bx,by+.03*reach,bz)
                face(mid,tip,edge,tuple(c*(.80+.19*f) for c in needles))


def trail_cover(stops,height,wet,face):
    """Low-cost beds of grass and fern fronds along both sides of the walk."""
    import random
    rng=random.Random(4815)
    for (x,z),(ex,ez) in zip(stops,stops[1:]):
        length=math.hypot(ex-x,ez-z)
        u,v=(ex-x)/length,(ez-z)/length
        for _ in range(round(length*1.8)):
            t=rng.uniform(0,length)
            offset=rng.choice((-1,1))*rng.uniform(1.5,10.)
            cx,cz=x+t*u-offset*v,z+t*v+offset*u
            fern_bed=rng.random()<.30
            size=rng.uniform(.24,.64) if fern_bed else rng.uniform(.16,.40)
            green=rng.randrange(88,130)
            for _ in range(rng.randint(4,11)):
                px,pz=cx+rng.gauss(0,1.1),cz+rng.gauss(0,1.1)
                if wet(px,pz):continue
                y=height(px,pz)-.025
                base=Vec(px,y,pz)
                for _ in range(rng.randint(3,6)):
                    angle=rng.uniform(0,math.tau)
                    dx,dz=math.cos(angle),math.sin(angle)
                    h=size*rng.uniform(.65,1.2)
                    reach=h*(1.1 if fern_bed else .52)
                    mid=Vec(px+.5*reach*dx,y+h*.76,pz+.5*reach*dz)
                    tip=Vec(px+reach*dx,y+h*(.6 if fern_bed else 1.),pz+reach*dz)
                    width=h*(.16 if fern_bed else .067)
                    edge=Vec(mid.x-width*dz,mid.y-.04*h,mid.z+width*dx)
                    face(base,edge,mid,(green*.74,green,51))
                    face(edge,tip,mid,(green*.82,green+8,56))
                    if fern_bed:
                        for side in (-1,1):
                            leaf=Vec(mid.x-side*dz*width*1.7,mid.y,mid.z+side*dx*width*1.7)
                            face(base,leaf,mid,(57,green-6,62))
