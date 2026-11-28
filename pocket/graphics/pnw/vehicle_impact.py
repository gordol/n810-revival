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


def collide(a, b):
    if math.hypot(a.x-b.x, a.z-b.z) > a.length+b.length:
        return 0.
    # Choose the deepest contact between the two rounded vehicle hulls.
    depth = 0.
    for ax, az in a.discs():
        for bx, bz in b.discs():
            dx, dz = bx-ax, bz-az
            gap = math.hypot(dx, dz)
            overlap = a.radius+b.radius-gap
            if overlap > depth:
                depth = overlap
                nx, nz = (dx/gap, dz/gap) if gap > .001 else (math.sin(a.heading), math.cos(a.heading))
                cx, cz = (ax+bx)*.5, (az+bz)*.5
    if not depth:
        return 0.
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
    impulse = 1.15*closing/(1/a.mass+1/b.mass+ra*ra*ia+rb*rb*ib)
    for body, sign, lever, inertia in ((a,-1,ra,ia),(b,1,rb,ib)):
        delta = sign*impulse/body.mass
        body.vx += nx*delta
        body.vz += nz*delta
        body.spin += sign*impulse*lever*inertia
        body.damage = min(1., body.damage + max(0., abs(delta)-1.5)/26.)
    return closing
