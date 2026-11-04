"""Independent held actions and bounded elapsed-time movement.

No terminal/evdev I/O, rendering, timers or inferred key releases.  Call event()
for explicit press/repeat/release reports, advance() on simulation ticks, and
clear() whenever the input owner loses focus or its source disconnects.
"""
from collections import namedtuple
import math

MotionStep=namedtuple('MotionStep','seconds forward strafe turn look')
DEFAULT_BINDINGS={
    'w':('forward',1),'up':('forward',1),'s':('forward',-1),'down':('forward',-1),
    'a':('strafe',-1),'d':('strafe',1),'left':('turn',-1),'right':('turn',1),
    'i':('look',-1),'k':('look',1),
}
AXES=('forward','strafe','turn','look')


def _time(now):
    if type(now) not in (int,float) or not math.isfinite(now):
        raise ValueError('finite monotonic timestamp required')
    return float(now)


class HeldMotion:
    def __init__(self,now,*,max_step=.1,bindings=None):
        if type(max_step) not in (int,float) or not math.isfinite(max_step) or not 0<max_step<=1:
            raise ValueError('motion time bound must be in (0,1]')
        self.max_step=float(max_step);self.last=_time(now);self.held=set()
        self.bindings=dict(DEFAULT_BINDINGS if bindings is None else bindings)
        if len(self.bindings)>128:raise ValueError('too many motion bindings')
        for key,binding in self.bindings.items():
            if type(key) is not str or not key or len(binding)!=2 or binding[0] not in AXES or binding[1] not in (-1,1):
                raise ValueError('invalid motion binding')

    def axes(self):
        values={axis:0 for axis in AXES}
        # Multiple aliases hold an action; they never multiply its speed.
        positive=set();negative=set()
        for key in self.held:
            axis,direction=self.bindings[key]
            (positive if direction>0 else negative).add(axis)
        for axis in AXES:values[axis]=int(axis in positive)-int(axis in negative)
        forward,strafe=values['forward'],values['strafe']
        length=math.hypot(forward,strafe)
        if length>1:forward/=length;strafe/=length
        return forward,strafe,values['turn'],values['look']

    def advance(self,now):
        now=_time(now)
        if now<self.last:raise ValueError('motion clock moved backwards')
        seconds=min(now-self.last,self.max_step);self.last=now
        return MotionStep(seconds,*self.axes())

    def event(self,key,kind,now):
        """Return the previous held interval, then apply this key edge.

        The caller integrates the returned step once.  Repeat notifications
        advance time normally and never add a separate repeat-driven impulse.
        Unknown keys return None and leave the movement clock untouched.
        """
        if kind not in ('press','repeat','release'):raise ValueError('invalid key event kind')
        if key not in self.bindings:return None
        step=self.advance(now)
        if kind=='release':self.held.discard(key)
        elif kind=='press':self.held.add(key)
        # A repeat without an owned press must not restart movement after a
        # focus reset, a disconnect, or loss of the original key-down event.
        return step

    def clear(self,now):
        """Discard held state and unsampled time at a focus/lifecycle boundary."""
        now=_time(now)
        if now<self.last:raise ValueError('motion clock moved backwards')
        self.held.clear();self.last=now
