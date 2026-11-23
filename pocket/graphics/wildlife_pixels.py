"""Pixel presentation of the existing wildlife meshes on the SDL scene backend."""
from array import array
import ctypes as C
import gzip
import json
from pathlib import Path
import struct
import sys
from functools import lru_cache
import math

from geometry import Vec
from wildlife_app import Wildlife
from marmot_art import ellipsoid
from geometry import merge
from wildlife_models import NAMES, mammal, raptor

PHOTOS=Path(__file__).with_name('wildlife_photos')


@lru_cache(maxsize=2)
def reference_photo(species):
    with gzip.open(PHOTOS/(species+'.rgb565.gz'),'rb') as stream:
        width,height=struct.unpack('<HH',stream.read(4))
        if not (0<width<=720 and 0<height<=720):raise ValueError('Invalid wildlife photograph dimensions')
        pixels=stream.read(width*height*2+1)
    if len(pixels)!=width*height*2:raise ValueError('Invalid wildlife photograph length')
    if sys.byteorder!='little':
        words=array('H');words.frombytes(pixels);words.byteswap();pixels=words.tobytes()
    return width,height,pixels


@lru_cache(maxsize=9)
def pose(species,index,obstacle):
    model=raptor(index) if species=='eagle' else mammal(species,index)
    if obstacle:
        model=merge((model,ellipsoid(Vec(.13,.055,-.19) if species!='eagle' else Vec(-.45,-.95,-1.1),
                                     (.1,.065,.07) if species!='eagle' else (.22,.55,.12),'rock','rock')))
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
        color=material if isinstance(material,int) else 0x868477
        faces.extend((a,b,c,color))
    return points,faces


class PixelWildlife(Wildlife):
    def __init__(self,host):
        super().__init__(host)
        self.photo=True
        self.credits=json.loads((PHOTOS/'sources.json').read_text())
        self.pixel_dirty=True
        self.pixel_frames=self.pixel_jobs=0

    def poll_interval(self):
        return 1/30 if self._sync() and (self.playing and not self.photo or self.dirty) else None

    def poll(self):
        if self._sync() and (self.dirty or self.playing and not self.photo and self.clock()>=self.next_poll):
            self.pixel_dirty=True
            self.dirty=False
            self.next_poll=self.clock()+1/30

    def key(self,key):
        if key not in ('tab','\t','p','P'):return super().key(key)
        if not self._sync():return False
        if key in ('p','P'):
            self.photo=not self.photo
        else:
            species=list(NAMES)
            self.species=species[(species.index(self.species)+1)%len(species)]
            self.age=self.yaw=0.;self.zoom=1.
        self.dirty=self.pixel_dirty=True
        return True

    def controls(self):
        if self.photo:return (('Animal','tab'),('Model','p'))
        return (('Animal','tab'),('Photo','p'),('Turn','right'),('Zoom','up'),('Pause' if self.playing else 'Play','space'))

    def lines(self):
        controls=self.controls()
        footer=''.join(label.center((i+1)*self.width//len(controls)-i*self.width//len(controls))
                       for i,(label,_) in enumerate(controls))
        return (NAMES[self.species],)+('',)*max(0,self.height-2)+(footer,)

    def help_pages(self):
        credit=self.credits[self.species]
        return (('Wildlife',('Animal or Tab cycles species. Photo or P switches between the animated study and a field photograph.',
                            'In the model: arrows turn and zoom, Space pauses, O toggles the obstacle.')),
                ('Photo credit',(credit['title'],credit['author'],credit['source'],credit['license'],
                                 credit['license_url'],'Resized and converted to RGB565.')))

    def pointer(self,x,y,width,button=0,released=False):
        if button or released or y!=self.height-1:return False
        controls=self.controls()
        action=controls[min(len(controls)-1,max(0,x*len(controls)//width))][1]
        if action=='up' and self.zoom<=.61:self.zoom=1.2
        return self.key(action)

    def draw_wildlife(self,context):
        x,y,cols,rows=self.host.bounds(self.host.window(self.name))
        ox,oy=self.host.origin
        x,y=(x+ox+1)*8,(y+oy+2)*16
        width,height=(cols-2)*8,(rows-4)*16
        if min(width,height)<=0:return ()
        if self.photo:
            pw,ph,pixels=reference_photo(self.species)
            texture=context.upload(pixels,pw,ph,self.name)
            ratio=min(width/pw,height/ph)
            w,h=max(1,round(pw*ratio)),max(1,round(ph*ratio))
            fn=context.lib.pocket_scene_wildlife_photo
            fn.argtypes=[C.c_void_p,C.c_void_p]+[C.c_int]*4
            context.check(fn(context.handle,texture,x+(width-w)//2,y+(height-h)//2,w,h))
            if self.pixel_dirty:self.pixel_frames+=1
            self.pixel_dirty=False
            return x+(width-w)//2,y+(height-h)//2,w,h
        phase=self.age/(1.8 if self.species=='eagle' else 2.5)
        index=int(phase)%3
        blend=phase%1
        blend=blend*blend*(3-2*blend)
        points,faces=pose(self.species,index,self.obstacle)
        next_points,_=pose(self.species,(index+1)%3,self.obstacle)
        flight=self.species=='eagle'
        yaw=self.yaw+(1.08 if flight else .23)
        elevation=-.84 if flight else .12
        # Centre the inspection camera on the anatomy as the user orbits.
        scale=min(width/(2.55 if flight else 1.3),height/(1.65 if flight else 1.08))/self.zoom
        bob=math.sin(self.age*(2.7 if flight else 1.9))*(.04 if flight else .006)
        context.check(context.lib.pocket_scene_wildlife(context.handle,x,y,width,height,
            points.buffer_info()[0],next_points.buffer_info()[0],len(points)//4,faces.buffer_info()[0],len(faces)//4,
            blend,yaw,elevation,scale,bob,int(flight)))
        if self.pixel_dirty:self.pixel_frames+=1
        self.pixel_dirty=False
        self.pixel_jobs+=1
        return x,y,width,height
