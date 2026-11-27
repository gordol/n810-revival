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


def fern(x,z,y,size,face,rng,compact=False):
    arms=rng.randint(3,5) if compact else rng.randint(4,8)
    rotation=rng.uniform(0,math.tau)
    for arm in range(arms):
        a=rotation+(arm+rng.uniform(-.35,.35))*math.tau/arms
        length=size*rng.uniform(.65,1.05)
        u,v=math.cos(a),math.sin(a)
        arch=rng.uniform(.38,.72)
        previous=Vec(x,y,z)
        pairs=14 if compact else 23
        for i in range(1,pairs+1):
            t=i/(pairs+1)
            p=Vec(x+u*t*length,y+length*(arch*math.sin(t*2.45)+.10*t),z+v*t*length)
            edge=Vec(p.x-.006*v*size,p.y,p.z+.006*u*size)
            face(previous,p,edge,(106,133,63))
            for side in (-1,1):
                span=length*(.16*math.sin(t*math.pi)**.70+.012)*rng.uniform(.91,1.08)
                offset=side*.19*length/pairs
                leaflet=Vec(p.x+offset*u,p.y,p.z+offset*v)
                blade(leaflet,a+side*rng.uniform(1.03,1.25)*(1-.34*t),
                      span,.085*span,span*(.27-.42*t),(55+13*t,110+29*t,56),face,steps=2)
            previous=p
        blade(previous,a,length/(pairs+1)*1.4,.012*length,-.035*length,(63,130,60),face,steps=2)


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
            length=rng.uniform(.085,.17)
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


def nurse_log(x,z,u,v,height,face,rng):
    """Rotten wood, a broken end and a moss bed over the dorsal bark."""
    length=rng.uniform(4.2,5.7)
    radius=rng.uniform(.30,.47)
    low=height(x-u*length/2,z-v*length/2)
    high=height(x+u*length/2,z+v*length/2)
    def point(t,angle,r):
        along=(t-.5)*length
        across=r*math.cos(angle)
        return Vec(x+along*u-across*v,low+(high-low)*t+radius*.51+r*math.sin(angle),
                   z+along*v+across*u)
    sides=14
    rims=[]
    for k in range(6):
        rim=[]
        for j in range(sides):
            angle=math.tau*j/sides
            t=k/5+rng.uniform(-.045,.045)*(1 if k in (0,5) else .3)
            r=radius*(1.12-.27*t)*rng.uniform(.93,1.05)
            rim.append(point(t,angle,r))
        rims.append(rim)
    for a,b in zip(rims,rims[1:]):
        for j,p in enumerate(a):
            nxt=(j+1)%sides
            # Encode upper-surface exposure continuously so the moss can
            # break up along the grain without following triangle edges.
            m=.030+.009*math.sin(j*math.tau/sides)
            n=.030+.009*math.sin(nxt*math.tau/sides)
            tone=(100,72,49)
            face(p,b[j],a[nxt],tone,(m,m,n))
            face(a[nxt],b[j],b[nxt],tone,(n,m,n))
    for t,rim in ((0,rims[0]),(1,rims[-1])):
        core=point(t+(.035 if not t else -.035),0,0)
        for j,p in enumerate(rim):
            face(p,rim[j-1],core,(135+7*(j%3),89+4*(j%3),52))
    for t in (.23,.49,.78):
        base=point(t,math.pi/2,radius*(1.12-.27*t))
        h=rng.uniform(.33,.84)
        peak=Vec(base.x+.03,base.y+h,base.z)
        face(Vec(base.x-.018,base.y,base.z),Vec(base.x+.018,base.y,base.z),peak,(118,83,53))
        for j in range(16):
            f=.15+.048*j
            angle=j*2.4+rng.uniform(-.21,.21)
            dx,dz=math.cos(angle),math.sin(angle)
            reach=h*(1-f)*rng.uniform(.31,.55)
            root=Vec(base.x,base.y+h*f,base.z)
            tip=Vec(root.x+reach*dx,root.y+.11*reach,root.z+reach*dz)
            for side in (-1,1):
                edge=Vec(root.x+(.53*dx-side*.21*dz)*reach,root.y-.10*reach,
                         root.z+(.53*dz+side*.21*dx)*reach)
                face(root,edge,tip,(56+18*f,106+29*f,68))


def spruce_sprays(x,y,z,h,t,angle,needles,face,rng,crown_base,breadth):
    """Two orders of lateral growth, with smaller forks toward the bough tip."""
    shoots=rng.randint(5,8)
    for j in range(shoots):
        a=angle+(j+rng.uniform(-.38,.38))*math.tau/shoots
        u,v=math.cos(a),math.sin(a)
        reach=h*breadth*(.24-.19*t)*rng.uniform(.78,1.18)
        level=y+h*(crown_base+.10+(.86-crown_base)*t)
        for k in range(3):
            f=.24+.25*k
            root=Vec(x+reach*f*u,level-reach*.28*f,z+reach*f*v)
            for side in (-1,1):
                direction=a+side*rng.uniform(.56,.98)
                dx,dz=math.cos(direction),math.sin(direction)
                length=reach*(.60-.39*f)*rng.uniform(.83,1.13)
                tip=Vec(root.x+dx*length,root.y-.16*length,root.z+dz*length)
                mid=Vec(root.x+.47*dx*length,root.y-.22*length,root.z+.47*dz*length)
                for fork in (-1,1):
                    width=fork*.22*length
                    edge=Vec(mid.x-width*dz,mid.y-.12*length,mid.z+width*dx)
                    tone=tuple(c*(.87+.12*f+.06*fork) for c in needles)
                    face(root,mid,edge,tone,.506)
                    face(mid,tip,edge,tone,.514)


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
