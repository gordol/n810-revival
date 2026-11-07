"""Shared exploration actions for graphical frontends with key edges."""
import math
from held_motion import HeldMotion

BINDINGS={
    'w':('forward',1),'s':('forward',-1),'a':('strafe',-1),'d':('strafe',1),
    'up':('forward',1),'down':('forward',-1),'left':('turn',-1),'right':('turn',1),
    'i':('look',-1),'k':('look',1),'j':('turn',-1),'l':('turn',1),
}

class ExploreControls:
    def __init__(self,now):
        self.motion=HeldMotion(now,bindings=BINDINGS)
        self.shifts=set();self.space=False;self.height=0.;self.velocity=0.

    def clear(self,now):
        self.motion.clear(now);self.shifts.clear();self.space=False

    def key(self,key,released,now,room):
        if key not in BINDINGS and key not in ('shift-left','shift-right','space'):return False
        self.advance(now,room)
        if key in BINDINGS:
            self.motion.event(key,'release' if released else 'press',now)
        elif key.startswith('shift-'):
            if released:self.shifts.discard(key)
            else:self.shifts.add(key)
        else:
            if not released and not self.space and self.height==0:self.velocity=460.
            self.space=not released
        if not released:room._leave_walkthrough(now)
        return True

    def advance(self,now,room):
        step=self.motion.advance(now);dt=step.seconds
        if not room._active():self.clear(now);return
        turn=step.turn*dt;heading=room.yaw+turn*.5
        room.yaw+=turn
        distance=dt*(3.2 if room.outdoors else 380.)*(3 if self.shifts else 1)
        room._translate(step.forward,step.strafe,distance,heading)
        room.pitch=max(-1.,min(1.,room.pitch+step.look*dt*.8))
        if self.height>0 or self.velocity>0:
            self.height+=self.velocity*dt-.5*1200*dt*dt
            self.velocity-=1200*dt
            if self.height<=0:self.height=0.;self.velocity=0.
        if any(step[1:]) or self.height or self.velocity:room.next_poll=0

    def look(self,dx,dy,room):
        if not (math.isfinite(dx) and math.isfinite(dy)):raise ValueError('finite mouse motion required')
        room.yaw+=dx*.003
        room.pitch=max(-1.,min(1.,room.pitch+dy*.003))
        room._leave_walkthrough(room.clock());room.next_poll=0
