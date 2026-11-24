"""Conifer stands for the Ohanapecosh valley."""
import math


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
                if 0<z<85 and abs(x+6-4*math.sin(z*.13))<11+.06*z:
                    if rng.random()<.87 or math.hypot(x+6,z-15)<7:continue
                if rng.random()<.19+.14*math.sin(.08*x+.06*z):continue
                yield x,z,rng.uniform(4,20),distance<65
                if rng.random()<.16:
                    # Regeneration beside a mature tree breaks up the even spacing.
                    sx,sz=x+rng.uniform(-3,3),z+rng.uniform(-3,3)
                    yield sx,sz,rng.uniform(1.3,4.2),False


def understory(rng,stops):
    """Overlapping patches of understory and scattered outliers along the valley."""
    centers=[(rng.uniform(-63,36),rng.uniform(-25,135)) for _ in range(137)]
    for x,z in stops:
        for _ in range(4):
            centers.append((x+rng.uniform(-4,4),z+rng.uniform(-4,4)))
    for cx,cz in centers:
        reach=rng.uniform(.8,5.5)
        angle=rng.uniform(0,math.tau)
        color=rng.choice(((84,110,65),(117,128,69),(72,104,68),(98,118,64)))
        size=rng.uniform(.12,.44)
        for _ in range(rng.randint(3,14)):
            u,v=rng.gauss(0,reach),rng.gauss(0,reach*.45)
            yield (cx+u*math.cos(angle)-v*math.sin(angle),
                   cz+u*math.sin(angle)+v*math.cos(angle),size*rng.uniform(.55,1.35),color)


def ridge_grass(height,face,rng,cx,cz):
    """Wind-bent tussocks in broken patches near a ridge viewpoint."""
    from geometry import Vec
    for _ in range(125):
        a=rng.uniform(0,math.tau)
        r=58*math.sqrt(rng.random())
        clump_x,clump_z=cx+r*math.cos(a),cz+r*math.sin(a)
        for _ in range(8):
            x,z=clump_x+rng.uniform(-2,2),clump_z+rng.uniform(-2,2)
            if max(abs(x-cx),abs(z-cz))<8:continue
            y=height(x,z)-.02
            for _ in range(6):
                a=rng.uniform(0,math.tau)
                dx,dz=math.cos(a),math.sin(a)
                length=rng.uniform(.12,.36)
                base=Vec(x+.04*dx,y,z+.04*dz)
                edge=Vec(base.x-.026*dz,y,base.z+.026*dx)
                tip=Vec(base.x+.09+dx*length,y+length,base.z+dz*length)
                face(base,tip,edge,(rng.randrange(110,147),rng.randrange(122,147),76))


def regional_stand(field,base_y,cx,cz,surface,lookout):
    """Stable world-grid trees and meadow clumps within walking distance."""
    from array import array
    import random
    from river_detail import shade_tree

    vertices=array('f')
    canopy=bytearray(512*512)
    east=field.origin.x+(field.nx-1)*field.dx
    north=field.origin.z+(field.nz-1)*field.dz
    def cone(x,y,z,r,h,tone,angle,sides,foliage=False):
        ring=[]
        for i in range(sides):
            a=angle+i*math.tau/sides
            spread=r*(.81+.25*math.sin(2*a+angle)) if foliage else r
            drop=-.19*r if foliage and i%2 else 0.
            ring.append((x+spread*math.cos(a),y+drop,z+spread*math.sin(a)))
        for i,p in enumerate(ring):
            light=.80+.16*math.cos(angle+(i+.5)*math.tau/sides)
            color=tuple(c*light for c in tone)+(0.,)
            for pt in (p,(x,y+h,z),ring[(i+1)%sides]):vertices.extend((*pt,*color))

    for j in range((cz-128)//12,(cz+128)//12):
        for i in range((cx-128)//12,(cx+128)//12):
            rng=random.Random((i*73856093)^(j*19349663))
            x=(i+rng.random())*12
            z=(j+rng.random())*12
            if not (field.origin.x+4<x<east-4 and field.origin.z+4<z<north-4):continue
            if lookout and math.hypot(x-lookout[0],z-lookout[1])<12:continue
            y=surface(field,x,z)
            if y>2420:continue
            slope=math.hypot(surface(field,x+3,z)-y,surface(field,x,z+3)-y)/3
            if slope>.84:continue
            treeline=1920+100*math.sin(x*.0017)+55*math.cos(z*.0021)
            density=.66+.23*math.sin(x*.021+math.cos(z*.03))
            fraction=max(0.,min(1.,(treeline-y)/250))
            angle=rng.random()*math.tau
            if rng.random()<density*fraction:
                h=rng.uniform(5,21)*(.4+.6*fraction)
                ground=y-base_y
                cone(x,ground-.2,z,h*.032,h*.8,(.36,.28,.19),angle,4)
                shade=rng.uniform(.8,1.1)
                tone=(.18*shade,.34*shade,.24*shade)
                lean_x,lean_z=rng.uniform(-.08,.08)*h,rng.uniform(-.08,.08)*h
                for rise,width in ((.18,.22),(.35,.20),(.52,.17),(.68,.12),(.81,.075)):
                    level=rise+rng.uniform(-.04,.04)
                    cone(x+lean_x*rise,ground+h*level,z+lean_z*rise,h*width,h*min(.33,1-level),
                         tone,angle+rng.uniform(-1,1),8,True)
                shade_tree(canopy,x-cx,z-cz,h)
            elif rng.random()<.64:
                for _ in range(7):
                    px=x+rng.uniform(-1.8,1.8)
                    pz=z+rng.uniform(-1.8,1.8)
                    ground=surface(field,px,pz)-base_y
                    h=rng.uniform(.18,.54)
                    for _ in range(5):
                        a=rng.random()*math.tau
                        u,v=math.cos(a),math.sin(a)
                        for vx,vy,vz in ((-.04*v,0,.04*u),(.04*v,0,-.04*u),(.65*h*u,h,.65*h*v)):
                            vertices.extend((px+vx,ground+vy,pz+vz,.40,.47,.25,0.))
    return vertices,canopy
