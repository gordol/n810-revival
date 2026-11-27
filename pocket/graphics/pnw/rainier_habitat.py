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
                # Closed valley forest has several canopy layers and a few emergent trees.
                age=rng.random()
                if age<.28:height=6+age/.28*15
                elif age<.93:height=25+(age-.28)/.65*29
                else:height=56+(age-.93)/.07*21
                yield x,z,height,distance<65
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


def parkland_height(rng,fraction):
    # Open-grown mountain conifers taper to wind-pruned trees at timberline.
    return rng.uniform(12.,43.)*(.25+.75*fraction)


def regional_stand(field,base_y,cx,cz,surface,lookout,meadow=None):
    """Stable world-grid trees and meadow clumps within walking distance."""
    from array import array
    import random
    from pnw.river_detail import shade_tree

    vertices=array('f')
    canopy=bytearray(512*512)
    east=field.origin.x+(field.nx-1)*field.dx
    north=field.origin.z+(field.nz-1)*field.dz
    def cone(x,y,z,r,h,tone,angle,sides):
        ring=[]
        for i in range(sides):
            a=angle+i*math.tau/sides
            ring.append((x+r*math.cos(a),y,z+r*math.sin(a)))
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
            in_meadow=meadow and math.hypot(x-meadow[0],(z-meadow[1]-9)/.8)<18
            if meadow:
                dx,dz=x-meadow[0],z-meadow[1]
                # Keep the uphill sightline open; forest islands frame the summit.
                if abs(dx)<73:
                    t=max(-1.,min(1.,dx/70))
                    crossing=90*t*math.sqrt(1-t*t)
                    in_meadow|=abs(abs(dz)-abs(crossing))<4.
                in_meadow|=0<dz<64 and abs(dx+.31*dz)<7+.10*dz
            has_tree=rng.random()<density*fraction and not in_meadow
            if has_tree:
                h=parkland_height(rng,fraction)
                ground=y-base_y
                cone(x,ground-.2,z,h*.020,h*.93,(.36,.28,.19),angle,4)
                shade=rng.uniform(.8,1.1)
                tone=(.18*shade,.34*shade,.24*shade)
                lean_x,lean_z=rng.uniform(-.08,.08)*h,rng.uniform(-.08,.08)*h
                # Individual sloping boughs leave windows of sky and exposed trunk.
                tiers=rng.randint(5,7)
                for tier in range(tiers):
                    rise=.16+.81*tier/tiers
                    hub=(x+lean_x*rise,ground+h*rise,z+lean_z*rise)
                    angle+=2.4
                    for branch in range(5):
                        a=angle+branch*math.tau/5+rng.uniform(-.24,.24)
                        u,v=math.cos(a),math.sin(a)
                        reach=h*(1-rise)*rng.uniform(.20,.36)
                        width=rng.uniform(.25,.48)*reach
                        mx,my,mz=hub[0]+.56*u*reach,hub[1]-.03*h,hub[2]+.56*v*reach
                        left=(mx-v*width,my-.12*reach,mz+u*width)
                        right=(mx+v*width,my-.17*reach,mz-u*width)
                        tip=(hub[0]+reach*u,my-.20*reach,hub[2]+reach*v)
                        ridge=(mx,my+.16*reach,mz)
                        light=.85+.24*math.cos(a-.6)
                        for tri,lit in (((hub,left,ridge),light),((ridge,left,tip),light),
                                        ((hub,ridge,right),light*.73),((ridge,tip,right),light*.73)):
                            color=tuple(c*lit for c in tone)
                            for point in tri:
                                edge=.514 if point in (left,right,tip) else .5
                                vertices.extend((*point,*color,edge))
                cone(x+lean_x,ground+h*.89,z+lean_z,h*.044,h*.11,tone,angle,5)
                shade_tree(canopy,x-cx,z-cz,h)
            if rng.random()<.82:
                for _ in range(4 if has_tree else 10):
                    px=x+rng.uniform(-3.1,3.1)
                    pz=z+rng.uniform(-3.1,3.1)
                    ground=surface(field,px,pz)-base_y
                    h=rng.uniform(.18,.54)
                    for _ in range(5):
                        a=rng.random()*math.tau
                        u,v=math.cos(a),math.sin(a)
                        for vx,vy,vz in ((-.04*v,0,.04*u),(.04*v,0,-.04*u),(.65*h*u,h,.65*h*v)):
                            vertices.extend((px+vx,ground+vy,pz+vz,.40,.47,.25,0.))
    # Crossed crowns are visible edge-on as the player turns. Use progressively
    # wider cells for distant stands and retain a sample across every bearing.
    distant=[]
    for inner,outer,spacing in ((128,480,16),(480,1200,30),(1200,2400,56)):
        for j in range(math.floor(max(field.origin.z,cz-outer)/spacing),math.ceil(min(north,cz+outer)/spacing)):
            for i in range(math.floor(max(field.origin.x,cx-outer)/spacing),math.ceil(min(east,cx+outer)/spacing)):
                rng=random.Random((i*73856093)^(j*19349663)^spacing)
                x=(i+rng.random())*spacing
                z=(j+rng.random())*spacing
                if not (field.origin.x<x<east and field.origin.z<z<north):continue
                if not inner<=max(abs(x-cx),abs(z-cz))<outer:continue
                y=surface(field,x,z)
                line=1990+100*math.sin(x*.0017)+55*math.cos(z*.0021)
                fraction=max(0.,min(1.,(line-y)/190))
                if rng.random()>=fraction*(.76+.19*math.sin(x*.036+math.sin(z*.024))):continue
                h=parkland_height(rng,fraction)
                distant.append((x,y-base_y,z,h,rng.uniform(.17,.26)*h,rng.random()*math.pi))
    slots=(250000-len(vertices)//7)//12
    visible=min(slots,len(distant))
    for k in range(visible):
        x,y,z,h,r,a=distant[k*len(distant)//visible]
        for heading,light in ((a,.9),(a+math.pi/2,1.05)):
            u,v=math.cos(heading),math.sin(heading)
            for rise,width,peak in ((.09,1.,.76),(.44,.63,1.)):
                for side,level in ((-1,rise),(0,peak),(1,rise+.04)):
                    vertices.extend((x+side*r*width*u,y+h*level,z+side*r*width*v,
                                     (1+side)*.5,.28*light,.21*light,.54+.02*level))
    return vertices,canopy
