"""Offline north-up field map for the playable Ohanapecosh valley."""
import math

from rainier_hike import ReliefMap, bounds
from river_camp import CAMP, OVERLOOK
from river_channel import TROUT_POOL
from river_overlay import Ink
from river_walk import hiking_paths, site

TRAIL_COLORS={'Hot Springs Trail':(254,200,104),'Silver Falls Loop Trail':(250,153,155)}
RIVER=(79,177,210)
SIZE=257


class ValleyMap(ReliefMap):
    def __init__(self,view):
        self.view=view
        self.local=True
        self.previous_destination=view.destination
        self.selected=view.destination
        self.prepare(view.camera[:2])

    def prepare(self,center):
        field=self.view.world[0]
        west,east,south,north=bounds(field)
        self.span=224. if self.local else east-west
        self.west=max(west,min(east-self.span,center[0]-self.span/2))
        self.north=min(north,max(south+self.span,center[1]+self.span/2))
        step=self.span/(SIZE-1)
        rgb=bytearray()
        for row in range(SIZE):
            j=round((self.north-row*step-south)/field.dz)
            for col in range(SIZE):
                i=round((self.west+col*step-west)/field.dx)
                k=j*field.nx+i
                slope=(field.values[j*field.nx+max(0,i-1)]-field.values[k])/field.dx
                shade=max(.67,min(1.42,1.+.65*slope))
                rgb.extend(int(c*shade) for c in (60,88,72))

        def line(a,b,color,radius):
            ax,ay=self.normalized(*a)
            bx,by=self.normalized(*b)
            if max(ax,bx)<0 or min(ax,bx)>1 or max(ay,by)<0 or min(ay,by)>1:return
            steps=max(1,math.ceil(max(abs(bx-ax),abs(by-ay))*(SIZE-1)))
            for n in range(steps+1):
                x=round((ax+(bx-ax)*n/steps)*(SIZE-1))
                y=round((ay+(by-ay)*n/steps)*(SIZE-1))
                for j in range(max(0,y-radius),min(SIZE,y+radius+1)):
                    left,right=max(0,x-radius),min(SIZE,x+radius+1)
                    if right>left:rgb[(j*SIZE+left)*3:(j*SIZE+right)*3]=bytes(color)*(right-left)

        for x,z,u,v,length in site()[1]:
            line((x,z),(x+u*length,z+v*length),RIVER,max(1,round(5/step)))
        for path in hiking_paths():
            for a,b in zip(path['xz'],path['xz'][1:]):
                line(a,b,TRAIL_COLORS[path['name']],1)
        self.rgb=bytes(rgb)
        self.upload=True

    def normalized(self,x,z):
        return (x-self.west)/self.span,(self.north-z)/self.span

    def frame(self,w,h):
        side=max(1,min(w-8,h-124))
        return (w-side)//2,28+(h-124-side)//2,side,side

    def draw(self,ctx,rect):
        w,h=rect[2:]
        ink=Ink(ctx,rect)
        ink.fill((0,0,w/8,h/16),0x1A302AFF)
        x,y,rw,rh=self.frame(w,h)
        self.draw_image(ctx,rect,x,y,rw,rh,SIZE,SIZE)
        ink.label(.5,.25,'Ohanapecosh',0xFFF4CF)
        ink.label(w/8-5,.25,'N up',0xD4EBDB)

        def screen(point):
            u,v=self.normalized(*point)
            if 0<=u<=1 and 0<=v<=1:return (x+u*(rw-1))/8,(y+v*(rh-1))/16

        places=(('Camp',CAMP),('Trout pool',TROUT_POOL),('Overlook',OVERLOOK[:2])) if self.local else (
            ('Camp area',CAMP),('Overlook',OVERLOOK[:2]))
        for label,place in places:
            p=screen(place)
            if p:
                px,py=p
                ink.fill((px-.25,py-.125,.5,.25),0xFFF6DFFF)
                left=px-len(label)-.5 if label=='Camp' else px+.5
                left=max(.25,min(w/8-len(label)-.25,left))
                ink.fill((left,py-.45,len(label),1),0x233B31EE)
                ink.label(left,py-.45,label,0xFFF6DF)
        p=screen(self.view.camera[:2])
        if p:
            px,py=p
            yaw=self.view.camera[2]
            for i in range(6):
                ink.fill((px+i*math.sin(yaw)/8-.25,py-i*math.cos(yaw)/16-.125,.5,.25),0xFFBD3DFF)
        if self.selected:
            p=screen(self.selected)
            if p:ink.label(p[0]-.5,p[1]-.5,'+',0xFFFFFF)
        bottom=h/16
        metres=25 if self.local else 250
        bar=rw*metres/self.span/8
        if w//8>=30:
            ink.fill((w/8-bar-1,bottom-4.95,bar,.14),0xD4EBDBFF)
            scale=f'{metres} m'
            ink.label(w/8-len(scale)-1,bottom-6,scale,0xD4EBDB)
        ink.label(.5,bottom-5.8,'Hot Springs Trail',0xFEC868)
        ink.label(.5,bottom-4.8,'Silver Falls Loop Trail',0xFA999B)
        message='Tap map to mark a waypoint'
        if self.selected:message=f'{math.dist(self.selected,self.view.camera[:2]):.0f} m to waypoint'
        ink.label(.5,bottom-3.5,message[:w//8],0xFFF4CF)
        for i,label in enumerate(('Valley' if self.local else 'Zoom in','Walk here' if self.selected else '','Back')):
            left,right=i*(w//8)//3,(i+1)*(w//8)//3
            if label:ink.button((left,bottom-2.3,right-left,2.3),label)

    def tap_xy(self,x,y):
        window=self.view.host.window(self.view.name)
        w,h=(window.w-2)*8,(window.h-3)*16
        px,py=(x+.5)*8,(y+.5)*16
        if py>=h-2.3*16:
            if px>=8*(2*(w//8)//3):
                self.view.destination=self.previous_destination
                return False
            if px<8*((w//8)//3):
                self.local=not self.local
                self.prepare(self.selected or self.view.camera[:2])
            elif self.selected:
                self.view.destination=self.selected
                self.view.trail.free_look=False
                return False
            return True
        left,top,rw,rh=self.frame(w,h)
        if left<=px<left+rw and top<=py<top+rh:
            self.selected=(self.west+self.span*(px-left)/rw,self.north-self.span*(py-top)/rh)
        return True
