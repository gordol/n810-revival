"""Pixel presentation of the existing wildlife meshes on the SDL scene backend."""
from array import array
from functools import lru_cache
import math

from geometry import Vec
from wildlife_app import Wildlife
from marmot_art import marmot, ellipsoid
from eagle_art import eagle
from geometry import merge

POSES={'marmot':('forage','walk','look'),'eagle':('glide','bank','upstroke')}
PALETTES={'marmot':{'fur':0xaf8155,'bird':0x645145,'wood':0xb79062,'glass':0xf8e9b0,'roof':0x382f27},
          'eagle':{'bird':0x574332,'metal':0xf1eee1,'glass':0xefb840,'roof':0x27251f}}


@lru_cache(maxsize=12)
def pose(species,index,obstacle):
    model=(marmot if species=='marmot' else eagle)(Vec(0,0,0),POSES[species][index])
    if obstacle:
        model=merge((model,ellipsoid(Vec(.13,.055,-.19) if species=='marmot' else Vec(-.45,-.95,-1.1),
                                     (.1,.065,.07) if species=='marmot' else (.22,.55,.12),'rock','rock')))
    # Smooth the rounded anatomy by accumulating adjacent triangle normals once
    # per pose. Per-material colours remain independent at triangle boundaries.
    normals=[[0.,0.,0.] for _ in model.vertices]
    for a,b,c,_,_ in model.triangles:
        p,q,r=(model.vertices[i] for i in (a,b,c))
        u,v,w=q.x-p.x,q.y-p.y,q.z-p.z
        i,j,k=r.x-p.x,r.y-p.y,r.z-p.z
        nx,ny,nz=v*k-w*j,w*i-u*k,u*j-v*i
        for vertex in (a,b,c):
            n=normals[vertex];n[0]+=nx;n[1]+=ny;n[2]+=nz
    points=array('f')
    for p,(nx,ny,nz) in zip(model.vertices,normals):
        length=math.sqrt(nx*nx+ny*ny+nz*nz)
        # Light the animal from above and in front of the inspection camera.
        diffuse=(-.35*nx+.78*ny-.51*nz)/length if length else 0
        points.extend((*p,.75+.24*diffuse))
    faces=array('I')
    for a,b,c,material,owner in model.triangles:
        color=PALETTES[species].get(material,0x868477)
        if species=='eagle' and ':primary' in owner:color=0x372e29
        if species=='eagle' and ':feather' in owner:color=0x77614d
        faces.extend((a,b,c,color))
    return points,faces


class PixelWildlife(Wildlife):
    def __init__(self,host):
        super().__init__(host)
        self.pixel_dirty=True
        self.pixel_frames=self.pixel_jobs=0

    def poll_interval(self):
        return 1/30 if self._sync() and (self.playing or self.dirty) else None

    def poll(self):
        if self._sync() and (self.dirty or self.playing and self.clock()>=self.next_poll):
            self.pixel_dirty=True
            self.dirty=False
            self.next_poll=self.clock()+1/30

    def lines(self):
        labels=('Animal','Turn','Zoom','Play' if not self.playing else 'Pause')
        return (self.species.capitalize(),)+('',)*max(0,self.height-2)+(
            ''.join(label.center((i+1)*self.width//4-i*self.width//4) for i,label in enumerate(labels)),)

    def pointer(self,x,y,width,button=0,released=False):
        if button or released or y!=self.height-1:return False
        action=('tab','right','up','space')[min(3,max(0,x*4//width))]
        if action=='up' and self.zoom<=.61:self.zoom=1.2
        return self.key(action)

    def draw_wildlife(self,context):
        x,y,cols,rows=self.host.bounds(self.host.window(self.name))
        ox,oy=self.host.origin
        x,y=(x+ox+1)*8,(y+oy+2)*16
        width,height=(cols-2)*8,(rows-4)*16
        if min(width,height)<=0:return ()
        phase=self.age/(3 if self.species=='marmot' else 1.3)
        index=int(phase)%3
        blend=phase%1
        blend=blend*blend*(3-2*blend)
        points,faces=pose(self.species,index,self.obstacle)
        next_points,_=pose(self.species,(index+1)%3,self.obstacle)
        flight=self.species=='eagle'
        yaw=self.yaw+(-.54 if flight else .12)
        elevation=-.65 if flight else .17
        # Centre the inspection camera on the anatomy as the user orbits.
        scale=min(width/(2.55 if flight else 1.3),height/(1.55 if flight else .72))/self.zoom
        bob=math.sin(self.age*(2.7 if flight else 1.9))*(.04 if flight else .006)
        context.check(context.lib.pocket_scene_wildlife(context.handle,x,y,width,height,
            points.buffer_info()[0],next_points.buffer_info()[0],len(points)//4,faces.buffer_info()[0],len(faces)//4,
            blend,yaw,elevation,scale,bob,int(flight)))
        if self.pixel_dirty:self.pixel_frames+=1
        self.pixel_dirty=False
        self.pixel_jobs+=1
        return x,y,width,height
