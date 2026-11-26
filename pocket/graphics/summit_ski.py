"""A fictional ski and ice traverse on the registered summit approach DEM."""
from dataclasses import dataclass
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


@dataclass(frozen=True)
class Course:
    name:str
    length:float
    start:tuple
    heading:float
    gates:tuple
    jumps:tuple
    bends:int=0

    def gate_line(self,d):
        """Lane and lateral slope of a smooth carve through each gate centre."""
        start,lane=0.,0.
        for end,next_lane in (*self.gates,(self.length,0.)):
            if d<=end:
                t=(d-start)/(end-start)
                delta=next_lane-lane
                return lane+delta*t*t*(3.-2.*t),delta*6.*t*(1.-t)/(end-start)
            start,lane=end,next_lane
        return 0.,0.

    def bearing(self,d):
        phase=self.bends*math.tau*d/self.length
        return self.heading+math.atan(12.*self.bends*math.tau/self.length*math.sin(phase))

    def location(self,d,lane=0.):
        u,v=math.sin(self.heading),math.cos(self.heading)
        bend=12.*(1.-math.cos(self.bends*math.tau*d/self.length))
        angle=self.bearing(d)
        return (self.start[0]+u*d+v*bend+math.cos(angle)*lane,
                self.start[1]+v*d-u*bend-math.sin(angle)*lane)


def slalom(length):
    return tuple((d,(-5.,3.,6.,-3.)[i%4]) for i,d in enumerate(range(55,length-50,90)))


COURSES=(
    Course('150 m',LENGTH,location(0),HEADING,GATES,()),
    Course('1.2 km',1200.,(-2000.,4600.),HEADING,slalom(1200),((120.,0.),(510.,5.),(920.,-4.)),2),
    Course('2.6 km',2600.,(1500.,6100.),math.radians(75),slalom(2600),
           ((160.,0.),(480.,-4.),(870.,5.),(1330.,0.),(1820.,-5.),(2260.,4.)),5),
)
RAMP_LENGTH=8.
LIP_HEIGHT=1.55
HALF_WIDTH=2.8


class SkiRun:
    def __init__(self,courses=COURSES):
        self.courses=courses
        self.course=courses[0]
        self.room=None
        self.assist=True
        self.tilt=None
        self.reset()

    def reset(self):
        self.mode='ready'
        self.distance=self.lane=self.steer=self.speed=self.angle=0.
        self.side_speed=0.
        self.view_pitch=None
        self.tap_lane=self.tap_point=None
        self.cue_time=self.manual_time=0.
        self.score=self.landings=0
        self.lift=self.vertical=0.
        self.air_y=None
        self.brake_on_landing=False
        self.tracks=[]
        self.left=True
        self.grip_uv=None
        self.hold=0
        self.goal=0.
        self.climb_lane=0.

    def enter_room(self,room):
        self.course=COURSES[1]
        self.reset()
        self.room=room

    def leave_room(self):
        self.room.close()
        self.room=None
        self.reset()

    def family_positions(self):
        roster=self.room.roster
        if self.room.ident not in roster:return
        my_slot=list(roster).index(self.room.ident)
        for slot,(uid,(distance,lane)) in enumerate(roster.items()):
            if uid!=self.room.ident:
                yield self.course.location(distance/10,lane/10+1.25*(slot-my_slot))

    @property
    def finish_action(self):
        return 'climb' if self.course==COURSES[0] else 'reset'

    def controls(self,w,h):
        half=w//2
        buttons=[('leave','Walk',(0,0,9,3)),('reset','Reset',(w-9,0,9,3))]
        if self.room:
            buttons=[buttons[0],('family','Room',(w-9,0,9,3))]
            if not self.room.running or self.mode=='bottom':return buttons
        elif self.mode=='ready':
            buttons.append(('family','Family',(half-5,0,10,3)))
        if not self.room and self.mode in ('ready','bottom'):
            label='Course '+self.course.name
            buttons.append(('course',label,((w-len(label)-2)//2,3,len(label)+2,3)))
        if self.mode=='climb':
            x=2 if self.left else w-14
            y=max(5,h//2-2)
            if self.grip_uv:
                x=max(0,min(w-12,round(w*self.grip_uv[0])-6))
                y=max(6,min(h-4,round(h*self.grip_uv[1])-2))
            buttons.append(('reach','Left grip' if self.left else 'Right grip',(x,y,12,4)))
        elif self.mode=='bottom':
            label='Climb back' if self.finish_action=='climb' else 'Ride again'
            buttons.append((self.finish_action,label,(half-7,h-5,14,4)))
        else:
            buttons.extend([('brake','Brake' if self.mode=='ski' else 'Glide',(half,h-5,w-half,5)),
                            ('assist','Assist '+('on' if self.assist else 'off'),(0,h-5,half,5))])
        return buttons

    def action(self,key):
        if self.room and (not self.room.running or key in ('course','reset')):return
        if key=='reset':self.reset()
        elif key=='course' and self.mode in ('ready','bottom'):
            self.course=self.courses[(self.courses.index(self.course)+1)%len(self.courses)]
            self.reset()
        elif key=='assist':self.assist=not self.assist
        elif key=='brake' and self.mode in ('ready','ski','braked'):
            if self.air_y is not None:
                self.brake_on_landing=True
                return
            self.mode='braked' if self.mode=='ski' else 'ski'
            self.speed=0.
        elif key=='climb' and self.mode=='bottom' and self.course==COURSES[0]:
            self.mode='climb'
            self.goal=self.distance
            self.climb_lane=self.lane
        elif key=='reach' and self.mode=='climb' and self.distance<=self.goal+.05:
            self.goal=max(0.,self.distance-10.)
            self.left=not self.left
            self.hold+=1

    def tap_slope(self,u,v):
        if self.room and not self.room.running:return
        if self.mode not in ('ready','ski','braked'):return
        starting=self.mode!='ski'
        if starting:self.action('brake')
        offset=2.*u-1.
        self.tap_lane=max(-10.,min(10.,self.lane+10.*offset))
        if self.assist and starting:self.tap_lane=None
        self.manual_time=0. if starting else 1.5
        self.tap_point=(u,v)
        self.cue_time=0.

    def advance(self,dt,height):
        if self.room:
            self.room.step(self.distance,self.lane)
            if self.room.running and self.mode=='ready':self.action('brake')
            elif not self.room.running and self.mode!='ready':self.reset()
        self.cue_time+=dt
        d=self.distance
        if self.mode=='ski':
            turn=self.steer
            self.manual_time=max(0.,self.manual_time-dt)
            if abs(turn)>.12:
                self.tap_lane=None
                self.manual_time=.65
            if self.assist and self.manual_time==0.:self.tap_lane=None
            if self.tap_lane is not None:
                turn=max(-1.,min(1.,(self.tap_lane-self.lane)*.55))
            elif self.tilt and abs(turn)<.04:turn=self.tilt.turn
            ahead=min(self.course.length,d+1.)
            grade=(height(*self.course.location(d,self.lane))-height(*self.course.location(ahead,self.lane)))/max(.01,ahead-d)
            acceleration=9.81*grade/math.hypot(1.,grade)-.25-.0035*self.speed**2
            self.speed=min(28.,max(1.2,self.speed+dt*acceleration))
            self.speed=min(self.speed,math.sqrt(2.*1.3*(self.course.length-d))+.35)
            if self.assist:
                # Small drags command a lateral speed, independent of downhill speed.
                travel=max(0.,(abs(turn)-.12)/.88)
                target=math.copysign(2.*travel+4.*travel**3,turn)
                if self.manual_time==0. and abs(turn)<=.12:
                    lane,slope=self.course.gate_line(d)
                    target=max(-14.,min(14.,self.speed*slope+2.5*(lane-self.lane)))
                response=7. if target==0. else 3.
                self.side_speed+=(target-self.side_speed)*(-math.expm1(-response*dt))
                self.angle=math.asin(max(-.48,min(.48,self.side_speed/self.speed)))
            else:
                self.angle+=(turn*.73-self.angle)*min(1.,dt*4.)
                self.side_speed=self.speed*math.sin(self.angle)
            self.distance=min(self.course.length,d+self.speed*dt*math.cos(self.angle))
            self.lane=max(-10.,min(10.,self.lane+self.speed*dt*math.sin(self.angle)))
            if not self.assist and self.tap_lane is not None and abs(self.tap_lane-self.lane)<.25:
                self.angle=self.side_speed=0.
            for gate,side in self.course.gates:
                if d<gate<=self.distance and abs(self.lane-side)<2.7:self.score+=1
            ground=height(*self.course.location(self.distance,self.lane))
            self.lift=0.
            for lip,lane in self.course.jumps:
                if abs(self.lane-lane)>HALF_WIDTH:continue
                if lip-RAMP_LENGTH<=self.distance<=lip:
                    self.lift=LIP_HEIGHT*(1.+(self.distance-lip)/RAMP_LENGTH)
                if d<lip<=self.distance and self.air_y is None:
                    self.air_y=height(*self.course.location(lip,self.lane))+LIP_HEIGHT
                    self.vertical=1.8+self.speed*(LIP_HEIGHT/RAMP_LENGTH)
            if self.air_y is not None:
                self.air_y+=self.vertical*dt-.5*9.81*dt*dt
                self.vertical-=9.81*dt
                self.lift=max(0.,self.air_y-ground)
                if self.lift==0.:
                    self.air_y=None
                    self.landings+=1
                    if self.brake_on_landing:
                        self.mode='braked'
                        self.speed=0.
                        self.brake_on_landing=False
            if self.air_y is None and (not self.tracks or self.distance-self.tracks[-1][0]>=1.5):self.tracks.append((self.distance,self.lane))
            if self.distance>=self.course.length:self.mode='bottom';self.speed=0.
        elif self.mode=='climb':
            self.distance=max(self.goal,d-9.*dt)
            fraction=self.distance/self.course.length
            self.lane=self.climb_lane*fraction+9.*math.sin(fraction*math.pi)
            if self.distance<=0.:self.reset()
        x,z=self.course.location(self.distance,self.lane)
        uphill=self.mode in ('bottom','climb')
        yaw=self.course.bearing(self.distance)+(math.pi if uphill else self.angle)
        ahead=self.course.location(max(0.,self.distance-2.) if uphill else min(self.course.length,self.distance+2.),self.lane)
        pitch=math.atan2(height(x,z)-height(*ahead),2.)*.75+.08
        if self.mode=='ski' and self.view_pitch is not None:
            pitch=self.view_pitch+(pitch-self.view_pitch)*(-math.expm1(-5.*dt))
        self.view_pitch=pitch
        return x,z,yaw,pitch

    def draw(self,ink,w,h,camera,aspect,height):
        # Ground marks project through the same camera as the slope.
        for d,lane in self.tracks:
            if abs(d-self.distance)>65:continue
            for side in (-.22,.22):
                x,z=self.course.location(d,lane+side)
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
        if self.mode in ('ready','braked') or (self.mode=='ski' and self.tap_point and self.cue_time<.65):
            demo=self.mode!='ski'
            phase=self.cue_time%1.5 if demo else self.cue_time
            u,v=(.53,.47) if demo else self.tap_point
            x,y=u*w,v*h
            radius=.6+min(1.,phase/.65)*1.6
            for i in range(24):
                a=i*math.tau/24
                ink.fill((x+radius*math.cos(a),y+.5*radius*math.sin(a),.28,.17),0x168EACFF)
            if demo:
                # Pixel-art pointing hand. Move the fingertip onto the ripple.
                step=max(0.,phase-.65)*1.8
                for row,bits in enumerate(('0110000','0110000','0110000','0111110','1111111','1111111','0111111','0011110')):
                    for col,bit in enumerate(bits):
                        if bit=='1':
                            ink.fill((x+(col-1)*.46+step,y+row*.24+step,.48,.26),0x253C4AFF)
        if self.mode=='climb':
            d=max(0.,self.distance-10.)
            x,z=self.course.location(d,9.*math.sin(d*math.pi/self.course.length))
            side=-1 if self.left else 1
            x+=side*1.25
            z-=side*.48
            self.grip_uv=project_subject(camera,aspect,1.,('',x,height(x,z)+.26,z,.8))
        label=(f'{round(self.speed*3.6)} km/h   {self.score}/4 gates' if self.mode=='ski'
               else 'Runout   '+str(self.score)+'/4 gates' if self.mode=='bottom'
               else f'{self.hold}/15 grips' if self.mode=='climb' else 'Tap snow to ski')
        if self.course.jumps:
            label=(f'{round(self.distance)}/{int(self.course.length)} m   '+('Air!' if self.air_y is not None else f'{self.landings} jumps'))
            if self.mode=='bottom':label=f'{self.score}/{len(self.course.gates)} gates   {self.landings} jumps'
        if self.mode in ('ready','braked'):label='Tap snow to ski'
        y=7 if self.mode in ('ready','bottom') else 4
        if self.room and not self.room.running:
            label=f'Room {self.room.code} - waiting for family' if self.room.ready else 'Tap Room to get ready'
        elif self.room and self.mode=='bottom':
            finished=sum(d>=self.course.length*10 for d,_ in self.room.roster.values())
            label=f'{finished}/{len(self.room.roster)} at the finish'
        ink.fill((.6,y-.3,len(label)+.8,1.5),0x243E42E8)
        ink.label(1,y,label,0xFFF4D7)


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
