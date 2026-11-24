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
                if 0<z<85 and -17-.09*z<x<7+.04*z:continue
                if rng.random()<.19+.14*math.sin(.08*x+.06*z):continue
                yield x,z,rng.uniform(4,20),distance<65


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
