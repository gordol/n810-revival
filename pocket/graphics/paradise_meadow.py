"""Illustrative flower drifts above Paradise on Rainier's regional elevation grid."""
import math
import random

from geometry import Vec

LATITUDE,LONGITUDE=46.791,-121.736
FLOWERS=('lupine','paintbrush','avalanche_lily')


def blooming(key,season):
    return season==0 or (season==3 and key=='avalanche_lily')


def patches():
    """The first three patches flank the viewpoint. Larger drifts extend uphill."""
    rng=random.Random(8621)
    yield 'lupine',-1.1,2.4
    yield 'paintbrush',1.4,3.1
    yield 'avalanche_lily',-.4,5.2
    for i in range(104):
        angle=rng.uniform(0,math.tau)
        radius=48*math.sqrt(rng.random())
        yield FLOWERS[i%3],radius*math.cos(angle),9+.69*radius*math.sin(angle)


def meadow(height,face,cx,cz):
    rng=random.Random(1916)
    for key,dx,dz in patches():
        for _ in range(rng.randint(5,12)):
            x,z=cx+dx+rng.gauss(0,.77),cz+dz+rng.gauss(0,.58)
            y=height(x,z)
            h=rng.uniform(.31,.62)*(.73 if key=='avalanche_lily' else 1.)
            a=rng.uniform(0,math.tau)
            mat=.88 if key=='avalanche_lily' else .86
            base=Vec(x,y-.01,z)
            top=Vec(x+.065*math.cos(a),y+h,z+.065*math.sin(a))
            # Crossed ribbon stems keep their width as the camera turns.
            for sx,sz in ((.009,0),(0,.009)):
                low=Vec(x-sx,y,z-sz)
                high=Vec(top.x+sx,top.y,top.z+sz)
                face(low,Vec(x+sx,y,z+sz),high,(83,126,59),mat)
                face(low,high,Vec(top.x-sx,top.y,top.z-sz),(83,126,59),mat)
            leaves=7 if key=='lupine' else 3 if key=='avalanche_lily' else 5
            for j in range(leaves):
                t=a+j*math.tau/leaves
                u,v=math.cos(t),math.sin(t)
                lily=key=='avalanche_lily'
                origin=Vec(x,y+h*.25,z) if key=='lupine' else base
                reach=.24 if lily else .14
                width=.044 if lily else .017
                tip=Vec(x+reach*u,y+h*(.63 if lily else .48),z+reach*v)
                mid=Vec(x+reach*.54*u,y+h*.4,z+reach*.54*v)
                for sign in (-1,1):
                    edge=Vec(mid.x-sign*v*width,mid.y-.009,mid.z+sign*u*width)
                    face(origin,edge,tip,(65,122+j*3,59),mat)
            if key=='avalanche_lily':
                for j in range(6):
                    t=a+j*math.tau/6
                    u,v=math.cos(t),math.sin(t)
                    edge=Vec(top.x+.047*u-.025*v,top.y-.033,top.z+.047*v+.025*u)
                    tip=Vec(top.x+.092*u,top.y+.026,top.z+.092*v)
                    other=Vec(top.x+.047*u+.025*v,edge.y,top.z+.047*v-.025*u)
                    face(top,edge,tip,(244,242,219),mat)
                    face(top,tip,other,(255,253,235),mat)
                face(top,Vec(top.x+.021,top.y+.01,top.z),Vec(top.x+.01,top.y-.05,top.z+.013),(250,184,45),mat)
            else:
                # Whorled pea flowers on a lupine spike; upright colored bracts on paintbrush.
                for j in range(20):
                    t=a+j*2.4
                    u,v=math.cos(t),math.sin(t)
                    r=.055*(1-j/30)
                    b=Vec(top.x,top.y-h*.35*(1-j/20),top.z)
                    l=Vec(b.x+r*u-.021*v,b.y+.012,b.z+r*v+.021*u)
                    rgt=Vec(b.x+r*u+.021*v,b.y+.012,b.z+r*v-.021*u)
                    lupine=key=='lupine'
                    tip=Vec(b.x+.94*r*u,b.y+(.034 if lupine else .068),b.z+.94*r*v)
                    face(b,l,rgt,(100,90,177) if lupine else (174,44,100),mat)
                    face(l,tip,rgt,(173,154,236) if lupine else (248,91,155),mat)

        # Short sedges fill the gaps between flower stems on the coarse DEM.
        for _ in range(70):
            x,z=cx+dx+rng.gauss(0,1.4),cz+dz+rng.gauss(0,1.)
            y=height(x,z)
            for _ in range(5):
                a=rng.random()*math.tau
                u,v=math.cos(a),math.sin(a)
                h=rng.uniform(.08,.24)
                face(Vec(x-.018*v,y,z+.018*u),Vec(x+.018*v,y,z-.018*u),
                     Vec(x+.65*h*u,y+h,z+.65*h*v),(104,rng.randrange(129,158),74),.815)


def groundcover(height,face,cx,cz):
    """Low woody cover and glacial stones in irregular drifts across the opening."""
    rng=random.Random(7131)
    for patch in range(225):
        if patch<60:
            x,z=cx+rng.uniform(-13,13),cz+rng.uniform(-5,20)
        else:
            x,z=cx+rng.uniform(-47,47),cz+rng.uniform(-28,55)
        reach=rng.uniform(.9,3.2)
        # Nearby shrubs share leaf color through the season.
        tone=.5+.5*math.sin(.18*x+.8*math.cos(.23*z))
        for _ in range(24):
            px,pz=x+rng.gauss(0,reach),z+rng.gauss(0,reach*.55)
            y=height(px,pz)
            h=rng.uniform(.10,.37)
            for j in range(4):
                a=rng.random()*math.tau
                u,v=math.cos(a),math.sin(a)
                base=Vec(px,y,pz)
                tip=Vec(px+.65*h*u,y+h,pz+.65*h*v)
                foot=Vec(px+.009*v,y,pz-.009*u)
                face(base,foot,tip,(97,71,54),.84)
                for leaf in range(3):
                    t=.32+leaf*.23
                    side=1 if leaf%2 else -1
                    stem=Vec(px+t*.65*h*u,y+t*h,pz+t*.65*h*v)
                    ex,ez=.08*u-side*.07*v,.08*v+side*.07*u
                    end=Vec(stem.x+ex,stem.y+.057,stem.z+ez)
                    left=Vec(stem.x+.45*ex-.21*ez,stem.y+.031,stem.z+.45*ez+.21*ex)
                    right=Vec(stem.x+.45*ex+.21*ez,stem.y+.018,stem.z+.45*ez-.21*ex)
                    color=(74+36*tone,98+rng.uniform(-12,22),56)
                    face(stem,left,end,color,.83)
                    face(end,right,stem,color,.83)
    for _ in range(165):
        x,z=cx+rng.uniform(-46,46),cz+rng.uniform(-26,65)
        y=height(x,z)
        r=rng.uniform(.12,.57)
        angle=rng.random()*math.tau
        top=Vec(x+r*.18,y+r*.54,z)
        ring=[]
        for j in range(7):
            a=angle+j*math.tau/7
            ring.append(Vec(x+math.cos(a)*r*rng.uniform(.77,1.2),y+r*rng.uniform(.07,.26),
                            z+.75*r*math.sin(a)))
        for j,p in enumerate(ring):
            q=ring[j-1]
            grey=rng.uniform(115,148)
            color=(grey,grey*.98,grey*.91)
            foot=Vec(p.x,height(p.x,p.z)-.03,p.z)
            end=Vec(q.x,height(q.x,q.z)-.03,q.z)
            face(p,q,top,color)
            face(foot,p,q,color)
            face(end,foot,q,color)
