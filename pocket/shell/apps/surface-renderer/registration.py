"""Cheap registration; Runtime decides any canonical registry integration."""
from pathlib import Path
from held_motion import MotionStep
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

        def pan_view(self,dx,dy,width,height,direction):
            self.pixel_scene.trail.free_look=True
            self.yaw+=direction*dx*3./width
            self.pitch=max(-1.,min(1.,self.pitch+direction*dy*2./max(1,height)))

        def world_touch(self,slot,x,y,width,height,button,released):
            scene=self.pixel_scene
            if slot not in self.contacts:
                if button or released or not scene or not scene.world or scene.notebook or scene.album:return False
                if not (0<=x<width and 0<=y<height):return False
                side=('walk' if x<width/2 else 'look') if self.controls==TWIN_THUMB else 'pan'
                if any(contact[0]==side for contact in self.contacts.values()):side='ignore'
                self.contacts[slot]=[side,x,y,x,y,bool(self.contacts)]
                if len(self.contacts)>1:
                    for contact in self.contacts.values():contact[5]=True
                self.touch_time=self.clock()
                return True
            contact=self.contacts[slot]
            side,start_x,start_y,last_x,last_y,_=contact
            dx,dy=x-start_x,y-start_y
            dragged=abs(dx)>1 or abs(dy)>.6
            if released:
                del self.contacts[slot]
                if side=='walk':self.touch_walk=(0.,0.)
                if not contact[5] and not dragged:scene.scene_tap(int(x),int(y),width,height)
            else:
                if dragged:contact[5]=True
                if contact[5] and side!='ignore':
                    if side!='pan':scene.destination=None
                    if side=='walk':
                        scene.cruise=scene.trail.guiding=False
                        self.touch_walk=(max(-1.,min(1.,-dy/max(2,height*.15))),max(-1.,min(1.,dx/max(3,width*.15))))
                    else:self.pan_view(x-last_x,y-last_y,width,height,-1 if side=='pan' else 1)
                contact[3:5]=[x,y]
            return True

        def cancel_pointer(self):
            self.contacts.clear()
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
                    def axis(delta,reach):
                        magnitude=min(1.,max(0,abs(delta)-1)/reach)
                        return -magnitude if delta<0 else magnitude
                    if self.pixel_scene and self.controls==WAYPOINT:
                        height=self.host.window(self.name).h-3
                        if self.drag_moved and self.drag_start[1]<height and not self.pixel_scene.notebook and not self.pixel_scene.album:
                            last_x,last_y=self.look_last
                            self.pan_view(x-last_x,y-last_y,width,height,-1)
                        self.look_last=(x,y)
                        return True
                    if self.pixel_scene and self.drag_moved:self.pixel_scene.destination=None
                    if self.pixel_scene and self.drag_start[0]>=width/2:
                        if self.drag_moved:
                            last_x,last_y=self.look_last
                            self.pan_view(x-last_x,y-last_y,width,self.host.window(self.name).h,1)
                        self.look_last=(x,y)
                        return True
                    if self.pixel_scene and self.drag_moved:
                        self.pixel_scene.trail.guiding=False
                        self.pixel_scene.cruise=False
                    self.drag_axes=(axis(dy,max(3,(self.host.window(self.name).h-2)*.20)),
                                    axis(dx,max(4,width*.20)))
                return True
            if button!=0:return False
            self.look_last=self.drag_start=(x,y)
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
