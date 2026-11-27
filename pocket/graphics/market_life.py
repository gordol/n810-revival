"""Market visitors and an order at the public fish counter, in game time."""
import math
from pike_market import HEADING,offset
from seattle_places import arcade_origin

class FishCounter:
    """Queue orders only when a shopper buys or the player taps the counter."""
    def __init__(self):
        self.started=None
        self.waiting=0
        self.player_ready=0.
        self.last_visit=None

    def order(self,age):
        if age<self.player_ready:return
        self.player_ready=age+5.
        self.waiting+=1

    def advance(self,age):
        visit=int(age//32)
        if age%32>=12 and self.last_visit!=visit:
            self.last_visit=visit
            if visit%3!=1:self.waiting+=1
        if self.started is not None and age-self.started>=4.4:self.started=None
        if self.started is None and self.waiting:
            self.waiting-=1
            self.started=age
        return None if self.started is None else age-self.started

def actors(age,ground,since):
    # Rows passed to GL: kind, world position, yaw (degrees), pose and palette.
    center=arcade_origin()
    floor=ground(*center)
    rows=[]
    def actor(kind,u,v,height,heading,pose,palette=0):
        x,z=offset(center,u,v)
        rows.append((kind,x,height,z,math.degrees(HEADING+heading),pose,palette))

    phase=age%32
    # A shopper approaches, orders, waits for wrapping and walks away.
    walk=min(1.,phase/11.)
    u=-8.5+walk*10
    v=-3.+walk*5.
    if phase>18:
        u+=1.2*(phase-18)
        v-=min(5.,phase-18)
    def walker(u,v,heading,gait,palette):
        actor(0,u,v,ground(*offset(center,u,v)),heading,gait,palette)
    walker(u,v,.9 if phase<11 else 1.95 if phase>18 else 0,
           (age*11)%12 if phase<11 or phase>18 else 12,2)
    for i in range(4):
        t=(age+i*13)%70
        east=t<35
        walker(-20+(t if east else 70-t)*1.3,-4.4-(i%2)*1.4,
               math.pi/2 if east else -math.pi/2,(age*12.5+i*2.3)%12,i+1)
    if since is None:since=-1.
    t=max(0.,min(1.,(since-.8)/.95))
    sender=ground(*offset(center,1.7,3.35))
    catcher=ground(*offset(center,3.4,6.25))
    actor(1,1.7,3.35,sender,.25,math.sin(math.pi*t),0)
    actor(1,3.4,6.25,catcher,math.pi,math.sin(math.pi*t),1)
    if 0<=since<=2.45:
        actor(2,1.7+1.7*t,3.72+2.18*t,sender+(catcher-sender)*t+1.08+4.8*t*(1-t),1.3+.7*t,.18-.38*t)
    if 2.45<since<4.4:actor(6,3.4,6.4,catcher+1.05,0,0)
    # Gulls bank over the street. Pigeons forage and pause on the paving.
    for i in range(2):
        a=age*.16+i*2.9
        actor(3,19*math.sin(a),-6+12*math.cos(a),floor+15+i*2+math.sin(a),
              math.atan2(19*math.cos(a),-12*math.sin(a)),.2+.5*max(0.,math.sin(a*3))*math.sin(age*5+i))
    for i in range(3):
        a=age*.31+i*1.93
        u,v=4+1.4*math.sin(a)+i*.48,-8+.9*math.cos(a*.7+i)
        actor(4,u,v,ground(*offset(center,u,v))+.14,math.atan2(math.cos(a),-.7*math.sin(a*.7+i)),
              max(0.,math.sin(age*2+i))**4)
    return rows

class Delivery:
    """One local delivery on the mapped one-way street. Yield to people ahead."""
    def __init__(self):
        self.distance=0.
        self.last=None
        self.speed=0.

    def advance(self,age,player,people,ground):
        from seattle_places import delivery_route
        dt=max(0.,min(.25,age-self.last)) if self.last is not None else 0.
        self.last=age
        ahead=self.distance
        route=delivery_route()
        for (x,z),(ex,ez) in zip(route,route[1:]):
            length=math.hypot(ex-x,ez-z)
            if ahead>=length:
                ahead-=length
                continue
            dx,dz=(ex-x)/length,(ez-z)/length
            x+=ahead*dx
            z+=ahead*dz
            blocked=False
            for px,pz in [player]+[(p[1],p[3]) for p in people if p[0]<=1]:
                fx,fz=px-x,pz-z
                if -2.5<fx*dx+fz*dz<5.5 and abs(fx*dz-fz*dx)<1.6:
                    blocked=True
                    break
            self.speed=0. if blocked else min(2.5,self.speed+dt)
            self.distance+=self.speed*dt
            return (5,x,ground(x,z),z,math.degrees(math.atan2(dx,dz)),0,0)
        return None
