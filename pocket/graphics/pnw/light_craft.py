"""Pilot controls for small craft on the shared Puget Sound terrain."""
import math
from types import SimpleNamespace

from pnw.hiking import HangGlider
from pnw.terrain import location
from pnw.units import feet, mph


class Helicopter(HangGlider):
    def __init__(self,field):
        x,z=location('sound',47.104,-122.287)
        super().__init__(SimpleNamespace(x=x,z=z,heading=0.),field.height,True)
        self.altitude=field.height(x,z)
        self.clearance=self.speed=0.
        self.motor=False  # collective climb command starts in hold

    def advance(self,dt,height,limits):
        turn=self.stick+self.drag[0]+('right' in self.keys)-('left' in self.keys)
        forward=self.pitch_stick+self.drag[1]+('up' in self.keys)-('down' in self.keys)
        response=-math.expm1(-2*dt)
        self.bank+=(max(-1.,min(1.,turn))-self.bank)*response
        self.heading+=1.15*self.bank*dt
        target=max(-.35,min(1.,forward))*(52. if self.fast else 27.)
        self.speed+=(target-self.speed)*response
        west,east,south,north=limits
        self.x=max(west,min(east,self.x+math.sin(self.heading)*self.speed*dt))
        self.z=max(south,min(north,self.z+math.cos(self.heading)*self.speed*dt))
        ground=height(self.x,self.z)
        climb=-4. if self.descending else 6. if self.motor else 0.
        self.altitude=max(ground,self.altitude+climb*dt)
        self.clearance=self.altitude-ground
        return self.x,self.z,self.heading,.04

    def wheel_items(self):
        return [('motor','Hold' if self.motor else 'Climb',math.pi),
                ('descend','Level' if self.descending else 'Lower',0.),
                ('fast','Cruise' if self.fast else 'Fast',-math.pi/2),
                ('wheel','Close',math.pi/2)]

    def draw(self,ink,w,h):
        super().draw(ink,w,h)
        ink.label(1,4,f'Helicopter · {feet(self.clearance)} · P climb/hold · Space lower',0xFFF4DC)


class PaddleCraft(HangGlider):
    def __init__(self,kind,field):
        from pnw.outings import BAY
        x,z=location('sound',*BAY)
        super().__init__(SimpleNamespace(x=x,z=z,heading=0.),field.height)
        self.kind=kind
        self.altitude=-.52
        self.speed=self.clearance=self.stroke=0.

    def advance(self,dt,height,limits):
        steer=self.stick+self.drag[0]+('right' in self.keys)-('left' in self.keys)
        effort=self.pitch_stick+self.drag[1]+('up' in self.keys)-('down' in self.keys)
        effort=max(-1.,min(1.,effort))
        self.stroke=(self.stroke+dt*abs(effort)*(6. if self.fast else 4.))%math.tau
        target=effort*(2.7 if self.kind=='canoe' else 3.4)*(1.3 if self.fast else 1.)
        self.speed+=((0 if self.descending else target)-self.speed)*(-math.expm1(-dt*(3 if self.descending else .85)))
        self.heading+=dt*max(-1.,min(1.,steer))*(.65 if self.kind=='canoe' else 1.05)
        west,east,south,north=limits
        x=max(west,min(east,self.x+dt*self.speed*math.sin(self.heading)))
        z=max(south,min(north,self.z+dt*self.speed*math.cos(self.heading)))
        if height(x,z)<=.01:self.x,self.z=x,z
        else:self.speed=0.
        return self.x,self.z,self.heading,.055

    def wheel_items(self):
        return [('descend','Release' if self.descending else 'Brake',0.),
                ('wheel','Close',math.pi/2),('fast','Easy' if self.fast else 'Sprint',-math.pi/2)]

    def controls(self,w,h):
        if not self.menu:return [('wheel','Paddle',(w-11,0,11,3))]
        return super().controls(w,h)

    def draw(self,ink,w,h):
        ink.label(1,1,f'{self.kind.title()} · {mph(abs(self.speed))}',0xFFF4DC)
        if self.menu:
            for _,_,angle in self.wheel_items():ink.sector(w/2,h/2,self.radius(w,h),angle)
