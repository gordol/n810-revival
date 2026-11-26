"""A fictional ski and ice traverse on the registered summit approach DEM."""
import json
import math
import os
import shutil
import subprocess
import threading

from river_explore import project_subject

LENGTH=150.
HEADING=math.radians(225)
SIDE=math.sqrt(.5)
GATES=((24.,-4.),(52.,5.),(80.,-5.),(108.,4.))


def location(distance,lane=0.):
    return -90.-SIDE*(distance+lane),4390.+SIDE*(lane-distance)


class SkiRun:
    def __init__(self):
        self.assist=True
        self.tilt=None
        self.reset()

    def reset(self):
        self.mode='ready'
        self.distance=self.lane=self.steer=self.speed=self.angle=0.
        self.score=0
        self.tracks=[]
        self.left=True
        self.grip_uv=None
        self.hold=0
        self.goal=0.
        self.climb_lane=0.

    def controls(self,w,h):
        half=w//2
        buttons=[('leave','Walk',(0,0,9,3)),('reset','Reset',(w-9,0,9,3))]
        if self.mode=='climb':
            x=2 if self.left else w-14
            y=max(5,h//2-2)
            if self.grip_uv:
                x=max(0,min(w-12,round(w*self.grip_uv[0])-6))
                y=max(6,min(h-4,round(h*self.grip_uv[1])-2))
            buttons.append(('reach','Left grip' if self.left else 'Right grip',(x,y,12,4)))
        elif self.mode=='bottom':buttons.append(('climb','Climb back',(half-7,h-5,14,4)))
        else:
            buttons.extend([('brake','Brake' if self.mode=='ski' else 'Glide',(half,h-5,w-half,5)),
                            ('assist','Assist '+('on' if self.assist else 'off'),(0,h-5,half,5))])
        return buttons

    def action(self,key):
        if key=='reset':self.reset()
        elif key=='assist':self.assist=not self.assist
        elif key=='brake' and self.mode in ('ready','ski','braked'):
            self.mode='braked' if self.mode=='ski' else 'ski'
            self.speed=0.
        elif key=='climb' and self.mode=='bottom':
            self.mode='climb'
            self.goal=self.distance
            self.climb_lane=self.lane
        elif key=='reach' and self.mode=='climb' and self.distance<=self.goal+.05:
            self.goal=max(0.,self.distance-10.)
            self.left=not self.left
            self.hold+=1

    def advance(self,dt,height):
        d=self.distance
        if self.mode=='ski':
            turn=self.steer
            if self.tilt and abs(turn)<.04:turn=self.tilt.turn
            self.angle+=(turn*.73-self.angle)*min(1.,dt*4.)
            ahead=min(LENGTH,d+1.)
            grade=(height(*location(d,self.lane))-height(*location(ahead,self.lane)))/max(.01,ahead-d)
            cap=8. if self.assist else 15.
            acceleration=9.81*grade/math.hypot(1.,grade)-.25-.014*self.speed**2
            self.speed=min(cap,max(1.2,self.speed+dt*acceleration))
            if d>120:self.speed=min(self.speed,math.sqrt(2.*1.3*(LENGTH-d))+.35)
            self.distance=min(LENGTH,d+self.speed*dt*math.cos(self.angle))
            self.lane=max(-10.,min(10.,self.lane+self.speed*dt*math.sin(self.angle)))
            for gate,side in GATES:
                if d<gate<=self.distance and abs(self.lane-side)<2.7:self.score+=1
            if not self.tracks or self.distance-self.tracks[-1][0]>=1.5:self.tracks.append((self.distance,self.lane))
            if self.distance>=LENGTH:self.mode='bottom';self.speed=0.
        elif self.mode=='climb':
            self.distance=max(self.goal,d-9.*dt)
            fraction=self.distance/LENGTH
            self.lane=self.climb_lane*fraction+9.*math.sin(fraction*math.pi)
            if self.distance<=0.:self.reset()
        x,z=location(self.distance,self.lane)
        uphill=self.mode in ('bottom','climb')
        yaw=HEADING+(math.pi if uphill else self.angle)
        ahead=location(max(0.,self.distance-2.) if uphill else min(LENGTH,self.distance+2.),self.lane)
        pitch=math.atan2(height(x,z)-height(*ahead),2.)*.75+.08
        return x,z,yaw,pitch

    def draw(self,ink,w,h,camera,aspect,height):
        # Ground marks project through the same camera as the slope.
        for d,lane in self.tracks:
            for side in (-.22,.22):
                x,z=location(d,lane+side)
                uv=project_subject(camera,aspect,1.,('',x,height(x,z)+.035,z,.3))
                if uv and 0<uv[0]<1 and 0<uv[1]<1:
                    ink.fill((uv[0]*w,uv[1]*h,.16,.10),0x90ADC0CC)
        if self.mode in ('ski','ready','braked'):
            # Foreshortened ski tips, with the edges banking into the carve.
            for side in (-1,1):
                for j in range(9):
                    t=j/8
                    x=w*(.5+side*(.075+.055*t))+.6*self.angle*(1-t)
                    ink.fill((x,h-8+t*3,.48+.32*t,.46),0xE7AA54FF)
                    ink.fill((x+.12,h-8+t*3,.12,.46),0x3F5662FF)
        if self.mode=='climb':
            d=max(0.,self.distance-10.)
            x,z=location(d,9.*math.sin(d*math.pi/LENGTH))
            side=-1 if self.left else 1
            x+=side*1.25
            z-=side*.48
            self.grip_uv=project_subject(camera,aspect,1.,('',x,height(x,z)+.26,z,.8))
        label=(f'{round(self.speed*3.6)} km/h   {self.score}/4 gates' if self.mode=='ski'
               else 'Runout   '+str(self.score)+'/4 gates' if self.mode=='bottom'
               else f'{self.hold}/15 grips' if self.mode=='climb' else 'Drag to carve')
        ink.fill((.6,3.7,len(label)+.8,1.5),0x243E42E8)
        ink.label(1,4,label,0xFFF4D7)


class TiltSteering:
    """Finite sensor requests off the render thread, relative to the starting roll."""
    def __init__(self,command):
        self.turn=0.
        self.stop=threading.Event()
        threading.Thread(target=self.listen,args=(command,),daemon=True).start()

    def listen(self,command):
        neutral=None
        while not self.stop.is_set():
            try:
                result=subprocess.run([command,'-s','accelerometer','-d','60','-n','1'],
                                      capture_output=True,text=True,timeout=2,check=True)
                xyz=next(iter(json.loads(result.stdout).values()))['values']
                roll=-xyz[0]/max(1.,math.hypot(*xyz[:3]))
                if neutral is None:neutral=roll
                self.turn=max(-1.,min(1.,(roll-neutral)*2.4))
            except (OSError,ValueError,TypeError,IndexError,KeyError,StopIteration,subprocess.SubprocessError):
                self.turn=0.
                break
            self.stop.wait(.08)


def start_tilt():
    if os.environ.get('POCKET_TERMUX')=='1' and os.environ.get('POCKET_SKI_TILT')=='1':
        command=shutil.which('termux-sensor')
        if command:return TiltSteering(command)
