"""A drifting dry fly and a catch-and-release fight at the trout pool."""
from functools import lru_cache
import math
import os
import random
import shutil
import subprocess
import threading

from river_channel import TROUT_POOL
from river_walk import channel


@lru_cache(maxsize=1)
def current():
    x,z=TROUT_POOL
    rows=channel().rows
    i=min(range(len(rows)-1),key=lambda j:math.hypot(rows[j].x-x,rows[j].z-z))
    dx,dz=rows[i+1].x-rows[i].x,rows[i+1].z-rows[i].z
    length=math.hypot(dx,dz)
    return dx/length,dz/length


def vibration(ms):
    if os.environ.get('POCKET_TERMUX')!='1' or os.environ.get('POCKET_HAPTICS')=='0':return
    command=shutil.which('termux-vibrate')
    if not command:return
    def pulse():
        try:subprocess.run([command,'-d',str(ms)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2)
        except (OSError,subprocess.TimeoutExpired):pass
    threading.Thread(target=pulse,daemon=True).start()


class Fishing:
    def __init__(self,rng=None):
        self.rng=rng or random.Random()
        self.kept_brook=False
        self.target='trout'
        self.state='idle'
        self.note=''
        self.tension=0.
        self.remaining=1.

    def position(self,now):
        if self.state in ('idle','over'):return None
        u,v=current()
        elapsed=max(0.,now-self.cast)
        drift=min(8.,elapsed)*.47-1.7
        x,z=TROUT_POOL
        x+=u*drift+v*self.offset
        z+=v*drift-u*self.offset
        if self.state in ('fight','landed'):
            t=now-self.hook
            progress=1-self.remaining
            run=self.remaining*math.sin(t*2.4)*.9
            x=self.strike[0]+progress*self.bank[0]+run*v
            z=self.strike[1]+progress*self.bank[1]-run*u
        return x,z,elapsed

    def pulling(self,now):
        return self.state=='fight' and (now-self.hook)%3.8<1.35

    def finish(self,note):
        self.state='over'
        self.note=note

    def update(self,now):
        if self.state=='drift':
            elapsed=now-self.cast
            if elapsed>9:self.finish('No bite this drift')
            elif self.willing and elapsed>=1.5:
                x,z,_=self.position(now)
                fx,fz=TROUT_POOL
                if self.target=='trout':
                    fx+=.3*math.cos(now*.8)
                    fz+=1.6*math.sin(now*.8)
                else:
                    fx+=.65
                    fz+=.5
                if math.hypot(x-fx,z-fz)<1.65:
                    self.state='bite'
                    self.bite=self.last_pulse=now
                    self.note='A rise! Lift the rod'
                    return 220
        elif self.state=='bite':
            if now-self.bite>3.5:self.finish('The trout let go')
            elif now-self.last_pulse>=1.:
                self.last_pulse=now
                return 140
        elif self.state=='fight':
            dt=min(.25,max(0.,now-self.last))
            self.last=now
            run=self.pulling(now)
            if self.reeling:
                self.turn=now
                self.remaining=max(0.,self.remaining-dt*(.04 if run else .17))
                self.tension=min(1.,self.tension+dt*(.55 if run else -.09))
            else:
                self.remaining=min(1.,self.remaining+dt*(.04 if run else 0.))
                self.tension-=.38*dt
            self.tension=max(0.,self.tension)
            if self.tension>=1.:
                self.finish('Line broke - trout away')
                return 300
            if self.remaining<=0.:
                self.state='landed'
                self.note='Brook trout' if self.target!='trout' else 'Native rainbow - release'
                return 350
            if now-self.turn>8:self.finish('Slack line - trout away')
            elif run and now-self.last_pulse>=.8:
                self.last_pulse=now
                return 240
        return 0

    def label(self,now):
        if self.state=='fight':return 'Ease line' if self.reeling else 'Reel'
        return {'idle':'Cast fly','drift':'Fly drifting','bite':'Lift rod!',
                'landed':'Release trout','over':'Cast again'}[self.state]

    def keep(self):
        if self.state=='landed' and self.target=='brook_trout#1':
            self.kept_brook=True
            self.state='idle'
            self.note='Brook trout kept'

    def tap(self,now,angler):
        if self.state in ('idle','over'):
            self.state='drift'
            self.cast=now
            self.offset=self.rng.uniform(-1.1,1.1)
            self.willing=self.rng.random()<.73
            self.target='brook_trout#1' if not self.kept_brook and self.rng.random()<.30 else 'trout'
            self.tension=0.
            self.remaining=1.
            self.note='Watch the drift'
        elif self.state=='bite':
            self.strike=self.position(now)[:2]
            dx,dz=angler[0]-self.strike[0],angler[1]-self.strike[1]
            scale=min(1.,2.5/max(.01,math.hypot(dx,dz)))
            self.bank=dx*scale,dz*scale
            self.state='fight'
            self.hook=self.last=self.turn=self.last_pulse=now
            self.reeling=False
            self.tension=.42
            self.note='Fish running - ease the line'
            return 130
        elif self.state=='fight':
            self.reeling=not self.reeling
            self.turn=now
            self.note='Reeling in' if self.reeling else 'Let it run'
        elif self.state=='landed':
            self.state='idle'
            self.note='Trout released'
        return 0
