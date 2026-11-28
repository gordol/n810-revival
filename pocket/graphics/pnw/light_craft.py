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
