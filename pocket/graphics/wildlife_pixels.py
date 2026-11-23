"""Pixel presentation of the existing wildlife meshes on the SDL scene backend."""
import math

from wildlife_app import Wildlife
from wildlife_models import FOX_ASSETS, FOX_FRAMES, NAMES, pose

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

    def key(self,key):
        if key not in ('tab','\t'):return super().key(key)
        if not self._sync():return False
        species=list(NAMES)
        self.species=species[(species.index(self.species)+1)%len(species)]
        self.age=self.yaw=0.;self.zoom=1.
        self.dirty=self.pixel_dirty=True
        return True

    def controls(self):
        return (('Animal','tab'),('Turn','right'),('Zoom','up'),('Pause' if self.playing else 'Play','space'))

    def lines(self):
        controls=self.controls()
        footer=''.join(label.center((i+1)*self.width//len(controls)-i*self.width//len(controls))
                       for i,(label,_) in enumerate(controls))
        return (NAMES[self.species],)+('',)*max(0,self.height-2)+(footer,)

    def help_pages(self):
        return (('Wildlife',('Animal or Tab cycles through the animated species.',
                            'Arrows turn and zoom. Space pauses motion. O toggles the obstacle.')),
                ('Fox credits',('Model by PixelMannen (CC0). Rig and walk by tomkranis (CC BY 4.0).',
                                'glTF conversion by AsoboStudio and scurest (CC BY 4.0).',
                                'Pocket adapted the geometry, colors and animation. See graphics/red_fox_credits.md.')))

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
        phase=self.age/(1.8 if self.species=='eagle' else 2.5)
        frames=3
        if self.species in FOX_ASSETS:
            frames=FOX_FRAMES
            phase=self.age*frames/(17/24)
        index=int(phase)%frames
        blend=phase%1
        if self.species not in FOX_ASSETS:blend=blend*blend*(3-2*blend)
        points,faces=pose(self.species,index,self.obstacle)
        next_points,_=pose(self.species,(index+1)%frames,self.obstacle)
        flight=self.species=='eagle'
        yaw=self.yaw+(-.79 if flight else -.47)
        elevation= .61 if flight else -.14
        # Centre the inspection camera on the anatomy as the user orbits.
        span=2.55 if flight else 1.70 if self.species in FOX_ASSETS else 1.3
        scale=min(width/span,height/(1.65 if flight else 1.08))/self.zoom
        bob=math.sin(self.age*(2.7 if flight else 1.9))*(.04 if flight else .006)
        appearance=2 if self.species=='arctic_fox' else int(flight)
        context.check(context.lib.pocket_scene_wildlife(context.handle,x,y,width,height,
            points.buffer_info()[0],next_points.buffer_info()[0],len(points)//4,faces.buffer_info()[0],len(faces)//4,
            blend,yaw,elevation,scale,bob,appearance,
            (list(NAMES).index(self.species)*FOX_FRAMES+index)*2+int(self.obstacle)))
        if self.pixel_dirty:self.pixel_frames+=1
        self.pixel_dirty=False
        self.pixel_jobs+=1
        return x,y,width,height
