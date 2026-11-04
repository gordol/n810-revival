"""Small deterministic demo sky and height-field light visibility, not astronomy."""
from collections import namedtuple
from functools import lru_cache
import math
from geometry import Vec,unit

Environment=namedtuple('Environment','sun moon sunlight moonlight ambient sky haze')


def mix(a,b,t):return tuple(x+(y-x)*t for x,y in zip(a,b))
def smooth(a,b,x):
    t=max(0,min(1,(x-a)/(b-a)))
    return t*t*(3-2*t)


def environment(age=0):
    # Start in morning; one virtual day per 86400 nature-clock seconds.
    angle=math.tau*(.12+age/86400)
    sun=unit(Vec(math.cos(angle),math.sin(angle),.45))
    moon=unit(Vec(-.22*math.cos(angle),-math.sin(angle),-.975*math.cos(angle)))
    day=smooth(-.12,.24,sun.y)
    dusk=(1-smooth(0,.24,abs(sun.y)))*smooth(-.20,-.03,sun.y)
    sunlight=smooth(-.025,.16,sun.y)
    moonlight=.24*smooth(0,.18,moon.y)*(1-day)
    sky=mix((5,8,15),(54,76,88),day)
    sky=mix(sky,(88,65,57),dusk*.38)
    haze=mix((14,21,33),(107,123,127),day)
    ambient=mix((.13,.17,.26),(.30,.34,.36),day)
    return Environment(sun,moon,sunlight,moonlight,ambient,sky,haze)


@lru_cache(maxsize=8)
def visibility(field,direction):
    """Bounded bilinear height-field rays; cached independently of the viewport.

    Half-grid steps, at most twice the grid diagonal. A small height bias avoids
    self shadowing. The coarse DEM limits shadow accuracy, including off-crop
    occluders; this is not a general triangle or radio visibility query.
    """
    if max(field.nx,field.nz)>33:
        from geometry import HeightField
        nx=min(33,field.nx);nz=min(33,field.nz)
        dx=(field.nx-1)*field.dx/(nx-1);dz=(field.nz-1)*field.dz/(nz-1)
        values=tuple(field.height(field.origin.x+x*dx,field.origin.z+z*dz) for z in range(nz) for x in range(nx))
        coarse=HeightField(nx,nz,field.origin,dx,dz,values,field.units)
        mask=HeightField(nx,nz,field.origin,dx,dz,visibility(coarse,direction))
        return tuple(mask.height(field.origin.x+x*field.dx,field.origin.z+z*field.dz) for z in range(field.nz) for x in range(field.nx))
    horizontal=math.hypot(direction.x,direction.z)
    if direction.y<=0:return (0.0,)*len(field.values)
    if horizontal<1e-8:return (1.0,)*len(field.values)
    step=min(field.dx,field.dz)*.5
    sx,sz=direction.x/horizontal*step,direction.z/horizontal*step
    rise=direction.y/horizontal*step
    bias=max(.0001,(max(field.values)-min(field.values))*.002)
    count=math.ceil(math.hypot(field.nx,field.nz)*2)+2
    result=[]
    from build_trace import checkpoint
    for index,height in enumerate(field.values):
        if index%32==0:checkpoint()
        x=field.origin.x+(index%field.nx)*field.dx
        z=field.origin.z+(index//field.nx)*field.dz
        visible=1.0
        for n in range(1,count):
            xx,zz=x+sx*n,z+sz*n
            try:occluder=field.height(xx,zz)
            except ValueError:break
            if occluder>height+rise*n+bias:
                visible=0.0;break
        result.append(visible)
    return tuple(result)
