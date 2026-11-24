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
