"""Planar vehicle contacts. Distances are metres and velocities are m/s."""
from dataclasses import dataclass
import math


@dataclass
class Body:
    x: float
    z: float
    heading: float
    vx: float
    vz: float
    spin: float
    mass: float
    length: float
    radius: float
    damage: float = 0.

    def coast(self, dt):
        self.x += self.vx * dt
        self.z += self.vz * dt
        self.heading += self.spin * dt
        drag = math.exp(-.78 * dt)
        self.vx *= drag
        self.vz *= drag
        self.spin *= math.exp(-1.55 * dt)

    def discs(self):
        reach = self.length - self.radius
        intervals = max(1, math.ceil(2 * reach / self.radius))
        for i in range(intervals + 1):
            offset = reach * (2 * i / intervals - 1)
            yield self.x + offset * math.sin(self.heading), self.z + offset * math.cos(self.heading)


def contact(a,b):
    dx,dz=b.x-a.x,b.z-a.z
    if math.hypot(dx,dz)>a.length+b.length+a.radius+b.radius:return None
    axes=[(math.sin(v.heading),math.cos(v.heading)) for v in (a,b)]
    depth=math.inf
    for ux,uz in (*axes,*((z,-x) for x,z in axes)):
        span=sum(abs(ux*x+uz*z)*v.length+abs(ux*z-uz*x)*v.radius
                 for (x,z),v in zip(axes,(a,b)))
        offset=dx*ux+dz*uz
        overlap=span-abs(offset)
        if overlap<=0:return None
        if overlap<depth:
            depth=overlap
            nx,nz=(ux,uz) if offset>=0 else (-ux,-uz)
    return depth,nx,nz


def collide(a, b):
    hit=contact(a,b)
    if hit is None:return 0.
    depth,nx,nz=hit
    # Use the midpoint of the overlapping faces along the contact tangent.
    tx,tz=nz,-nx
    def interval(body):
        sn,cs=math.sin(body.heading),math.cos(body.heading)
        center=tx*body.x+tz*body.z
        extent=abs(tx*sn+tz*cs)*body.length+abs(tx*cs-tz*sn)*body.radius
        return center-extent,center+extent
    l,r=interval(a);u,v=interval(b)
    tangent=(max(l,u)+min(r,v))*.5
    normal=((a.x+b.x)*nx+(a.z+b.z)*nz)*.5
    cx,cz=tangent*tx+normal*nx,tangent*tz+normal*nz
    # Positive yaw rotates forward (+z) towards +x.
    ra = (cz-a.z)*nx - (cx-a.x)*nz
    rb = (cz-b.z)*nx - (cx-b.x)*nz
    closing = (a.vx-b.vx)*nx + (a.vz-b.vz)*nz + ra*a.spin - rb*b.spin
    ia = 3/(a.mass*(a.length**2+a.radius**2))
    ib = 3/(b.mass*(b.length**2+b.radius**2))
    share = b.mass/(a.mass+b.mass)
    a.x -= nx*depth*share
    a.z -= nz*depth*share
    b.x += nx*depth*(1-share)
    b.z += nz*depth*(1-share)
    if closing <= 0:
        return 0.
    impulse = 1.02*closing/(1/a.mass+1/b.mass+ra*ra*ia+rb*rb*ib)
    for body, sign, lever, inertia in ((a,-1,ra,ia),(b,1,rb,ib)):
        delta = sign*impulse/body.mass
        body.vx += nx*delta
        body.vz += nz*delta
        body.spin = max(-3.,min(3.,body.spin + sign*impulse*lever*inertia))
        body.damage = min(1., body.damage + max(0., abs(delta)-1.5)/26.)
    return closing
