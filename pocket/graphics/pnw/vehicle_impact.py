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
    elevation: float = 0.

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


class StreetObstacles:
    """Index upright faces of the same local meshes used for rendering."""
    def __init__(self, mesh, vertices):
        self.cells = {}
        for i in range(0, vertices * 7, 21):
            ax, ay, az = mesh[i:i+3]
            bx, by, bz = mesh[i+7:i+10]
            cx, cy, cz = mesh[i+14:i+17]
            low, high = min(ay, by, cy), max(ay, by, cy)
            if high-low < .65:
                continue
            # Each wall quad has a vertical edge. Also accept tapered trunks.
            if abs(ax-bx)+abs(az-bz) < .35 and abs(ay-by) > .6:
                bx, bz = cx, cz
            elif abs(ax-cx)+abs(az-cz) < .35 and abs(ay-cy) > .6:
                pass
            elif abs(bx-cx)+abs(bz-cz) >= .35 or abs(by-cy) <= .6:
                continue
            edge = (ax, az, bx-ax, bz-az, low, high)
            for u in range(math.floor((min(ax,bx)-1.4)/16), math.floor((max(ax,bx)+1.4)/16)+1):
                for v in range(math.floor((min(az,bz)-1.4)/16), math.floor((max(az,bz)+1.4)/16)+1):
                    self.cells.setdefault((u,v), set()).add(edge)

    def contact(self, x, z, y, radius):
        for ax,az,dx,dz,low,high in self.cells.get((math.floor(x/16),math.floor(z/16)), ()):
            if not low-.1 <= y <= high+.1:
                continue
            t=max(0.,min(1.,((x-ax)*dx+(z-az)*dz)/max(.0001,dx*dx+dz*dz)))
            nx,nz=x-ax-t*dx,z-az-t*dz
            distance=math.hypot(nx,nz)
            if .00001 < distance < radius:
                return nx/distance,nz/distance
        return None


def walk_past_obstacles(previous,goal,height,layers):
    x,z=previous
    dx,dz=goal[0]-x,goal[1]-z
    steps=max(1,math.ceil(math.hypot(dx,dz)/.18))
    for _ in range(steps):
        ux,uz=dx/steps,dz/steps
        for layer in layers:
            normal=layer.contact(x+ux,z+uz,height(x,z)+.45,.32)
            if normal:
                inward=min(0.,ux*normal[0]+uz*normal[1])
                ux-=inward*normal[0]
                uz-=inward*normal[1]
        x+=ux
        z+=uz
    return x,z


def strike_scenery(ride, previous, height, layers):
    dx,dz=ride.x-previous[0],ride.z-previous[1]
    steps=max(1,math.ceil(math.hypot(dx,dz)/.45))
    sn,cs=math.sin(ride.heading),math.cos(ride.heading)
    length={11:5.8,12:7.8}.get(ride.actor_kind,2.2)
    radius=1.2 if ride.actor_kind in (11,12) else .95
    for i in range(1,steps+1):
        x,z=previous[0]+dx*i/steps,previous[1]+dz*i/steps
        y=height(x,z)+.75
        for j in range(math.ceil(length*2)+1):
            u=(length-radius)*(2*j/math.ceil(length*2)-1)
            for layer in layers:
                normal=layer.contact(x+sn*u,z+cs*u,y,radius)
                if not normal:continue
                nx,nz=normal
                vx,vz=sn*ride.speed+cs*ride.slip,cs*ride.speed-sn*ride.slip
                inward=vx*nx+vz*nz
                if inward>=0:continue
                ride.x,ride.z=x-dx/steps,z-dz/steps
                vx-=nx*inward
                vz-=nz*inward
                ride.speed,ride.slip=vx*sn+vz*cs,vx*cs-vz*sn
                ride.damage=min(1.,ride.damage+max(0.,-inward-3.)/60)
                return
