"""Folded and toothed foliage for the near field of the walking camera."""
import math
from geometry import Vec


def blade(base,angle,length,width,rise,color,face,serrated=False):
    """Taper both ends around a raised midrib and a recurved tip."""
    u,v=math.cos(angle),math.sin(angle)
    old=None
    steps=12 if serrated else 7
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
    for arm in range(7):
        a=arm*math.tau/7+rng.uniform(-.25,.25)
        length=size*rng.uniform(.65,1.05)
        u,v=math.cos(a),math.sin(a)
        previous=Vec(x,y,z)
        for i in range(1,10):
            t=i/10
            p=Vec(x+u*t*length,y+length*(.58*math.sin(t*2.45)+.10*t),z+v*t*length)
            edge=Vec(p.x-.009*v,p.y,p.z+.009*u)
            face(previous,p,edge,(109,122,61))
            for side in (-1,1):
                span=length*(.21*math.sin(t*math.pi)**.62+.025)
                blade(p,a+side*(1.12-.36*t),span,.16*span,.025,(53+i,99+i*2,56),face)
            previous=p


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


def spruce_sprays(x,y,z,h,t,angle,needles,face):
    """Layered lateral shoots on the outer silhouette of nearby conifers."""
    for j in range(8):
        a=angle+j*math.tau/8
        u,v=math.cos(a),math.sin(a)
        reach=h*(.24-.19*t)
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
