"""Cheap registration; Runtime decides any canonical registry integration."""
from pathlib import Path
from math import dist
from held_motion import MotionStep
from hike_camera import ViewGrab
import importlib.util

def app_module():
    import sys
    directory=Path(__file__).resolve().parent
    if str(directory) not in sys.path:sys.path.insert(0,str(directory))
    spec=importlib.util.spec_from_file_location('_surface_room_app',directory/'app.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def create(host,**options):
    return app_module().SurfaceRoom(host,**options)


def descriptor():
    return dict(id='surface-room',title='Surface room',preferred_size=(82,29),minimum_size=(22,12),category='Experiments',
        description='Framework-native room with material-anchored glyph surfaces',
        help=(('Explore',('W/S walk; A/D strafe; arrows turn.','One moving object; isolated rendering proof.')),),factory=create)


WAYPOINT='Tap to walk'
TWIN_THUMB='Two thumbs'

def create_outdoors(host,*,pixel_scene=None,app_context=None,**options):
    # The saved overview cameras belong to Scenery; expose that existing app
    # rather than creating another camera library in the walking demo.
    class RainierWalk(app_module().SurfaceRoom):
        def __init__(self,*args,**options):
            super().__init__(*args,**options)
            from rainier_data import installed
            self.needs_grid=pixel_scene is None and installed() is None
            self.drag_start=None
            self.drag_axes=(0.,0.)
            self.drag_moved=False
            self.contacts={}
            self.optic_fingers={}
            self.pinch=None
            self.grab=None
            self.touch_walk=(0.,0.)
            self.controls=app_context.preferences['touch-controls'] if app_context else WAYPOINT
            self.pixel_scene=pixel_scene
            self.download_pool=None
            self.download_job=None
            self.download_message='USGS elevation is required for this walk.'

        def lines(self):
            if self.needs_grid:
                return ('Rainier walk',self.download_message,'[ Download Rainier terrain ]' if not self.download_job else 'Downloading…')
            if self.pixel_scene:return self.pixel_scene.lines()
            return super().lines()

        def poll_interval(self):
            if not self.needs_grid:
                if not self.pixel_scene:return super().poll_interval()
                if not self._sync() or self.pixel_scene.error:return None
                if self.pixel_scene.world is None:return .1
                moving=any(self.drag_axes) or self.held_motion.held
                changed=self.pixel_scene.camera!=(self.x,self.z,self.yaw,self.pitch)
                return 1/35 if moving or changed else 1/20
            return .2 if self.download_job and self._active() else None

        def poll(self,force=False):
            if not self.needs_grid:
                if not self._sync():return
                self.advance_drag()
                if self.pixel_scene:
                    now=self.clock()
                    self._apply_motion(self.held_motion.advance(now),now)
                    return self.pixel_scene.poll(self)
                return super().poll(force)
            if self.download_job and self.download_job.done():
                try:self.download_job.result();self.needs_grid=False
                except Exception as error:self.download_message=str(error)
                self.download_job=None

        @property
        def pointer_captured(self):return self.drag_start is not None

        def movement_bounds(self):
            if self.pixel_scene and isinstance(getattr(self.pixel_scene,'world',None),tuple):
                from rainier_hike import bounds
                return bounds(self.pixel_scene.world[0])
            return super().movement_bounds()

        def _translate(self,forward,sideways,distance,heading=None):
            super()._translate(forward,sideways,distance*getattr(self.pixel_scene,'pace',1.),heading)

        def preferences_changed(self,preferences):
            self.cancel_pointer()
            self.controls=preferences['touch-controls']

        def begin_grab(self,x,y,width,height):
            scene=self.pixel_scene
            aspect=width*8/(height*16)
            camera=getattr(scene,'frame_camera',None)
            if camera:
                (ex,ey,ez,yaw,pitch),_=camera
                self.grab_eye=(ex,ey,ez)
            else:
                yaw,pitch=self.yaw,self.pitch
                self.grab_eye=(self.x,0.,self.z)
            zoom=getattr(scene,'zoom',1.)
            self.grab=ViewGrab(.5+(x/width-.5)/zoom,.5+(y/height-.5)/zoom,aspect,yaw,pitch)
            self.grab_aspect=aspect

        def drag_view(self,x,y,width,height):
            if not self.grab:return
            zoom=getattr(self.pixel_scene,'zoom',1.)
            u,v=.5+(x/width-.5)/zoom,.5+(y/height-.5)/zoom
            if self.controls==TWIN_THUMB:
                # Keep the alternate layout's camera-steering direction.
                u,v=2*self.grab.start[0]-u,2*self.grab.start[1]-v
            scene=self.pixel_scene
            if self.controls==WAYPOINT and self.grab.cursor is None and getattr(scene,'frame_camera',None):
                self.grab.point=scene.grab_point(self.grab_eye,self.grab.direction)
            self.grab.cursor=(u,v)
            self.grab_aspect=width*8/(height*16)
            scene.trail.free_look=True
            self.update_grab()

        def update_grab(self):
            if not self.grab or self.grab.cursor is None:return
            eye=self.pixel_scene.eye_position(self.x,self.z) if self.grab.point is not None else self.grab_eye
            angles=self.grab.aim(eye,self.grab_aspect,self.yaw)
            if angles:self.yaw,self.pitch=angles

        def world_touch(self,slot,x,y,width,height,button,released):
            scene=self.pixel_scene
            optics=getattr(scene,'lens',False) or getattr(scene,'binoculars',False)
            if slot and (slot in self.optic_fingers or (optics and not button and not released
                    and not scene.notebook and not scene.album and 0<=x<width and 0<=y<height)):
                self.optic_fingers[slot]=(x*8,y*16)
                if self.pinch is None and len(self.optic_fingers)==2:
                    a,b=self.optic_fingers
                    self.pinch=(a,b,max(1.,dist(self.optic_fingers[a],self.optic_fingers[b])),scene.zoom)
                    self.contacts.clear()
                    self.grab=None
                    self.touch_walk=(0.,0.)
                if self.pinch:
                    a,b,start,zoom=self.pinch
                    if a in self.optic_fingers and b in self.optic_fingers:
                        scene.zoom=max(1.,min(8.,zoom*dist(self.optic_fingers[a],self.optic_fingers[b])/start))
                        scene.pixel_dirty=True
                    if released:del self.optic_fingers[slot]
                    if not self.optic_fingers:self.pinch=None
                    return True
                if released:del self.optic_fingers[slot]
            if slot==0 and self.controls==TWIN_THUMB:return False
            if slot not in self.contacts:
                if button or released or not scene or not scene.world or scene.notebook or scene.album:return False
                if not (0<=x<width and 0<=y<height):return False
                side=('walk' if x<width/2 else 'look') if self.controls==TWIN_THUMB else 'pan'
                if any(contact[0]==side for contact in self.contacts.values()):side='ignore'
                if side in ('pan','look'):self.begin_grab(x,y,width,height)
                self.contacts[slot]=[side,x,y,bool(self.contacts)]
                if len(self.contacts)>1:
                    for contact in self.contacts.values():contact[3]=True
                self.touch_time=self.clock()
                return True
            contact=self.contacts[slot]
            side,start_x,start_y,_=contact
            dx,dy=x-start_x,y-start_y
            dragged=abs(dx)>1 or abs(dy)>.6
            if side in ('pan','look'):dragged=(dx*8)**2+(dy*16)**2>9
            if released:
                del self.contacts[slot]
                if side in ('pan','look'):
                    if dragged or (self.grab and self.grab.cursor is not None):self.drag_view(x,y,width,height)
                    self.grab=None
                if side=='walk':self.touch_walk=(0.,0.)
                if not contact[3] and not dragged:scene.scene_tap(int(x),int(y),width,height)
            else:
                if dragged:contact[3]=True
                if contact[3] and side!='ignore':
                    if side!='pan':scene.destination=None
                    if side=='walk':
                        scene.cruise=scene.trail.guiding=False
                        self.touch_walk=(max(-1.,min(1.,-dy/max(2,height*.15))),max(-1.,min(1.,dx/max(3,width*.15))))
                    else:self.drag_view(x,y,width,height)
            return True

        def cancel_pointer(self):
            self.grab=None
            self.contacts.clear()
            self.optic_fingers.clear()
            self.pinch=None
            self.touch_walk=(0.,0.)
            self.drag_start=None
            self.drag_axes=(0.,0.)
            self.drag_moved=False

        def cancel_keys(self,now=None):
            self.cancel_pointer()
            super().cancel_keys(now)

        def advance_drag(self):
            if self.contacts:
                now=self.clock()
                dt=min(.1,max(0.,now-self.touch_time))
                self.touch_time=now
                self._apply_motion(MotionStep(dt,*self.touch_walk,0.,0.),now)
            if self.drag_start is None:return
            now=self.clock()
            dt=min(.1,max(0.,now-self.drag_time))
            self.drag_time=now
            forward,turn=self.drag_axes
            self._apply_motion(MotionStep(dt,forward,0.,turn*1.35,0.),now)

        def pointer(self,x,y,width,button=0,released=False):
            if self.needs_grid:
                return self.key('d') if not released and button==0 and y==2 else False
            if not self._sync():return False
            if released or button==32:
                if not self.pointer_captured:return False
                self.advance_drag()
                dx,dy=x-self.drag_start[0],self.drag_start[1]-y
                self.drag_moved |= abs(dx)>1 or abs(dy)>1
                if released:
                    tap=not self.drag_moved
                    if not tap and self.pixel_scene and abs(dx)>=max(3,width*.12) and abs(dx)>abs(dy)*2:
                        book=getattr(self.pixel_scene,'notebook',None)
                        step=1 if dx<0 else -1
                        if hasattr(book,'turn_page'):
                            book.turn_page(step)
                            self.pixel_scene.pixel_dirty=True
                            self.cancel_pointer()
                            return True
                        if self.pixel_scene.album:
                            self.pixel_scene.album_index=(self.pixel_scene.album_index+step)%len(self.pixel_scene.album)
                            self.pixel_scene.pixel_dirty=True
                            self.cancel_pointer()
                            return True
                    if not tap and self.grab:self.drag_view(x+.5,y+.5,width,self.host.window(self.name).h-3)
                    self.cancel_pointer()
                    if tap and self.pixel_scene:
                        book=getattr(self.pixel_scene,'notebook',None)
                        if book:
                            stay=book.tap_xy(x,y) if hasattr(book,"tap_xy") else book.tap(y)
                            if not stay:self.pixel_scene.notebook=None
                            self.pixel_scene.pixel_dirty=True
                            return True
                        if y>=self.host.window(self.name).h-3:return self.pixel_scene.footer(x,width)
                        return self.pixel_scene.scene_tap(x,y,width,self.host.window(self.name).h-3)
                    if tap:return self.key('left' if x<width//3 else 'right' if x>=2*width//3 else 'up')
                else:
                    if self.pixel_scene and (self.pixel_scene.notebook or self.pixel_scene.album):return True
                    def axis(delta,reach):
                        magnitude=min(1.,max(0,abs(delta)-1)/reach)
                        return -magnitude if delta<0 else magnitude
                    if self.pixel_scene and self.controls==WAYPOINT:
                        height=self.host.window(self.name).h-3
                        if self.drag_moved and self.drag_start[1]<height and not self.pixel_scene.notebook and not self.pixel_scene.album:
                            self.drag_view(x+.5,y+.5,width,height)
                        return True
                    if self.pixel_scene and self.drag_moved:self.pixel_scene.destination=None
                    if self.pixel_scene and self.drag_start[0]>=width/2:
                        if self.drag_moved:
                            self.drag_view(x+.5,y+.5,width,self.host.window(self.name).h-3)
                        return True
                    if self.pixel_scene and self.drag_moved:
                        self.pixel_scene.trail.guiding=False
                        self.pixel_scene.cruise=False
                    self.drag_axes=(axis(dy,max(3,(self.host.window(self.name).h-2)*.20)),
                                    axis(dx,max(4,width*.20)))
                return True
            if button!=0:return False
            self.drag_start=(x,y)
            height=self.host.window(self.name).h-3
            if self.pixel_scene and y<height and not self.pixel_scene.notebook and not self.pixel_scene.album:
                if self.controls==WAYPOINT or x>=width/2:self.begin_grab(x+.5,y+.5,width,height)
            self.drag_time=self.clock()
            self.drag_axes=(0.,0.)
            self.drag_moved=False
            return True

        def on_close(self):
            if self.pixel_scene:
                if self.pixel_scene.valley_pose:
                    self.x,self.z,self.yaw,self.pitch=self.pixel_scene.valley_pose
                self.pixel_scene.reset_hike()
                self.pixel_scene.leave_party()
                self.pixel_scene.release()
            super().on_close()

        def close(self):
            if self.pixel_scene:self.pixel_scene.close()
            if self.download_pool:self.download_pool.shutdown(wait=False,cancel_futures=True)
            super().close()

        def key(self,key,now=None):
            if self.pixel_scene and key=='?' and self.pixel_scene.world is not None:
                from river_notebook import RiverNotebook
                self.pixel_scene.notebook=RiverNotebook()
                self.pixel_scene.destination=None
                self.pixel_scene.trail.guiding=self.pixel_scene.cruise=False
                return True
            if self.pixel_scene and key in ('space',' ','enter','\r'):return self.pixel_scene.guide()
            if key.lower()=='o' and self._sync():
                self.cancel_keys();self.host.activate('Scenery');return True
            if self.needs_grid and key in ('d','D','\r','\n'):
                if not self.download_job:
                    from concurrent.futures import ThreadPoolExecutor
                    from rainier_data import download
                    if not self.download_pool:self.download_pool=ThreadPoolExecutor(max_workers=1)
                    self.download_job=self.download_pool.submit(download)
                return True
            return super().key(key,now)
    form=RainierWalk(host,outdoors=True,name='Rainier walk',**options)
    if pixel_scene:
        form.help=(('Blueberry trail',('Tap the ground to explore, or tap Berries for the guided fox hunt.',
                    'Drag the scenery to look around. Choose Two thumbs in Rainier walk settings for split controls.')), )
        return form
    form.help+=(('Touch movement',('Drag up or down to walk forward or backward. Drag sideways to turn. Diagonal drags combine both.',
        'Hold your finger away from the starting point to keep moving. Lift to stop. Tap the centre for one step.')),('Terrain viewpoints',('O opens Scenery: original, wide, elevated and valley cameras.',
        'Scenery is a separate overview; returning here keeps your walking position.')),)
    return form


def outdoor_descriptor():
    """Optional app reference; Runtime owns canonical discovery/menu inclusion."""
    return dict(id='rainier-walk',title='Rainier walk',preferred_size=(90,32),minimum_size=(22,12),category='Experiments',
        description='Explore Rainier terrain and wildlife. On mobile, follow the Ohanapecosh blueberry trail.',
        settings=(dict(id='touch-controls',label='Touch controls',kind='choice',choices=(WAYPOINT,TWIN_THUMB),default=WAYPOINT),),
        help=(('Explore',('W/S walk; A/D strafe; arrows turn.','I/K look up/down; ground follows metre-scale terrain.','O opens saved terrain viewpoints in Scenery.',
                          'Fictional ruins; real elevation data; existing Lab marmot/eagle.')),),factory=create_outdoors)
