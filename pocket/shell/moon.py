"""Small analytical lunar sphere with authored procedural relief, not a catalog.

    Physical radius is in meters. Direction, phase, and apparent size are inputs;
    the demo exaggerates apparent size so terminal cells can reveal the model.
"""
from dataclasses import dataclass
from functools import lru_cache
import math
from geometry import Vec,dot,unit,add,mul
from scenery import PHASES


def phase_value(name,age):
    if name=='auto':return (age/(29.53*86400))%1
    return {'full':0,'waxing':.25,'crescent':.38,'new':.5,'waning':.75}[name]


@dataclass(frozen=True)
class Moon:
    direction: Vec
    phase: float=0.0  # 0 = full, .5 = new; local light orientation around sphere
    angular_radius: float=.018
    radius: float=1737400.0

    def __post_init__(self):
        if self.radius<=0 or not 0<self.angular_radius<math.pi/2:raise ValueError('invalid lunar sphere size')
        object.__setattr__(self,'direction',unit(self.direction))
        object.__setattr__(self,'phase',self.phase%1)

    @property
    def distance(self):return self.radius/math.sin(self.angular_radius)

    def surface(self,normal,detail=True):
        # Two broad dark basins plus spherical crater profiles; sphere coordinates
        # stay fixed as the terminator moves across them.
        maria=.10*math.sin(normal.x*8+normal.y*3)+.07*math.sin(normal.y*11-normal.x*4)
        albedo=.66+maria
        shade_normal=normal
        angle=self.phase*math.tau
        light=unit(Vec(math.sin(angle),.12,math.cos(angle)))
        visibility=1.0
        for center,radius,depth in craters() if detail else ():
            cosine=dot(normal,center)
            if cosine<math.cos(radius*1.35):continue
            angle=math.acos(max(-1,min(1,cosine)));r=angle/radius
            # A depressed bowl and raised rim perturb the sphere's surface normal.
            bowl=math.exp(-r*r*3);rim=math.exp(-((r-1)/.16)**2)
            albedo*=1-.13*bowl+.10*rim
            tangent=add(center,mul(normal,-cosine))
            # Local ray toward the light: a raised circular rim can occlude the
            # depressed bowl. This is an analytic crater approximation.
            elevation=dot(normal,light)
            if r<1 and elevation>0:
                offset=add(normal,mul(center,-cosine))
                tangent_light=add(light,mul(center,-dot(light,center)))
                tangent_length=math.sqrt(dot(tangent_light,tangent_light))
                if tangent_length>1e-8:
                    along=dot(offset,mul(tangent_light,1/tangent_length))
                    edge=-along+math.sqrt(max(0,radius*radius-dot(offset,offset)+along*along))
                    rim_height=radius*depth*(bowl+.35)
                    if edge*elevation/max(.001,math.sqrt(max(0,1-elevation*elevation)))<rim_height:visibility=.06
            slope=depth*(r*6*bowl-((r-1)/.0256)*rim)
            shade_normal=unit(add(shade_normal,mul(tangent,slope/max(radius,.001))))
        illumination=max(0,dot(shade_normal,light))*visibility
        value=albedo*(.035+.965*illumination)
        return tuple(c*value for c in (231,231,219))


@lru_cache(maxsize=1)
def craters():
    result=[]
    for i in range(48):
        z=.08+.90*((i*.75487766625)%1)
        a=i*2.39996322973;r=math.sqrt(1-z*z)
        result.append((Vec(math.cos(a)*r,math.sin(a)*r,z),.035+.095*((i*.61803398875)%1),.035))
    return tuple(result)


def draw(pixels,samples,camera,pw,ph,moon):
    """Ray/sphere intersection with analytic per-hit relief shading."""
    right,down,forward=camera.axes()
    depth=dot(moon.direction,forward)
    if depth<=0:return
    focal=camera.focal or camera.span_x*.7
    cx=(.5+dot(moon.direction,right)*focal/depth/camera.span_x)*pw
    cy=(.5+dot(moon.direction,down)*focal/depth/camera.span_y)*ph
    rx=pw*math.tan(moon.angular_radius)*focal/depth/camera.span_x
    ry=ph*math.tan(moon.angular_radius)*focal/depth/camera.span_y
    center=mul(moon.direction,moon.distance)
    # Observer-facing sphere axes are fixed relative to the sky, not the screen.
    from geometry import cross
    east=unit(cross(Vec(0,1,0),moon.direction))
    north=unit(cross(east,mul(moon.direction,-1)))
    facing=mul(moon.direction,-1)
    for y in range(max(0,int(cy-ry*1.1)-1),min(ph,int(cy+ry*1.1)+2)):
        for x in range(max(0,int(cx-rx*1.1)-1),min(pw,int(cx+rx*1.1)+2)):
            index=y*pw+x
            if samples[index] is not None:continue
            direction=unit(add(forward,add(mul(right,((x+.5)/pw-.5)*camera.span_x/focal),mul(down,((y+.5)/ph-.5)*camera.span_y/focal))))
            along=dot(direction,center)
            discriminant=along*along-dot(center,center)+moon.radius*moon.radius
            if discriminant<0:continue
            point=add(mul(direction,along-math.sqrt(discriminant)),mul(center,-1))
            normal=unit(point)
            local=Vec(dot(normal,east),dot(normal,north),dot(normal,facing))
            pixels[index]=moon.surface(local,detail=min(rx,ry)>=4)
