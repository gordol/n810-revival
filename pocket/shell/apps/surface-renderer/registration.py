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
            self.ski_contacts={}
            self.optic_fingers={}
            self.pinch=None
            self.grab=None
            self.touch_walk=(0.,0.)
            self.controls=app_context.preferences['touch-controls'] if app_context else WAYPOINT
            self.pixel_scene=pixel_scene
            if pixel_scene and app_context:self.set_flight_controls(app_context.preferences)
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
                if getattr(self.pixel_scene,'outing',None) and not self.pixel_scene.notebook:return 1/45
                moving=any(self.drag_axes) or self.held_motion.held
                changed=self.pixel_scene.camera!=(self.x,self.z,self.yaw,self.pitch)
                return 1/35 if moving or changed else 1/20
            return .2 if self.download_job and self._active() else None

        def poll(self,force=False):
            if not self.needs_grid:
                if not self._sync():return
                if getattr(getattr(self.pixel_scene,'notebook',None),'button',None):return
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
        def pointer_captured(self):
            flight=getattr(self.pixel_scene,'glider',None) or getattr(self.pixel_scene,'road',None)
            return self.drag_start is not None or bool(flight and flight.contact)

        def movement_bounds(self):
            if self.pixel_scene and isinstance(getattr(self.pixel_scene,'world',None),tuple):
                from pnw.hiking import bounds
                return bounds(self.pixel_scene.world[0])
            return super().movement_bounds()

        def _translate(self,forward,sideways,distance,heading=None):
            super()._translate(forward,sideways,distance*getattr(self.pixel_scene,'pace',1.),heading)

        def set_flight_controls(self,preferences):
            if self.pixel_scene:
                self.pixel_scene.horizon_range=preferences.get('flight-horizon','Auto')
                self.pixel_scene.ground_source=preferences.get('ground-source','Aerial')
                self.pixel_scene.southpaw=preferences.get('stick-layout')=='Southpaw'
                self.pixel_scene.look_gain={'Gentle':.65,'Standard':1.,'Quick':1.4}[preferences.get('look-speed','Standard')]
                self.pixel_scene.pitch_sign=1. if preferences.get('flight-pitch')=='Push to climb' else -1.
                self.pixel_scene.roll_gain={'Gentle':.6,'Standard':1.,'Quick':1.35}[preferences.get('flight-roll','Standard')]

        def preferences_changed(self,preferences):
            self.set_flight_controls(preferences)
            self.cancel_pointer()
            self.controls=preferences['touch-controls']

        def begin_grab(self,x,y,width,height):
            scene=self.pixel_scene
            aspect=width*8/(height*16)
            camera=getattr(scene,'frame_camera',None)
            if camera:
                yaw,pitch=camera[0][3:]
            else:
                yaw,pitch=self.yaw,self.pitch
            zoom=getattr(scene,'zoom',1.)
            self.grab=ViewGrab(.5+(x/width-.5)/zoom,.5+(y/height-.5)/zoom,aspect,yaw,pitch)

        def drag_view(self,x,y,width,height):
            if not self.grab:return
            zoom=getattr(self.pixel_scene,'zoom',1.)
            u,v=.5+(x/width-.5)/zoom,.5+(y/height-.5)/zoom
            if self.controls==TWIN_THUMB:
                # Keep the alternate layout's camera-steering direction.
                u,v=2*self.grab.start[0]-u,2*self.grab.start[1]-v
            scene=self.pixel_scene
            if self.controls==WAYPOINT and getattr(scene,'cruise',False) and scene.cruise_heading is None:
                scene.cruise_heading=self.yaw
            self.grab.cursor=(u,v)
            scene.trail.free_look=True
            angles=self.grab.aim(width*8/(height*16),self.yaw)
            if angles:self.yaw,self.pitch=angles

        def ski_touch(self,slot,x,y,width,height,released):
            scene=self.pixel_scene
            start=self.ski_contacts.setdefault(slot,(x,y,False))
            dx=x-start[0]
            moved=start[2] or abs(dx)>1 or abs(y-start[1])>1
            if released:
                del self.ski_contacts[slot]
                if moved:scene.ski.steer=0.
                elif y>=height:scene.footer(x,width)
                else:scene.scene_tap(x,y,width,height)
            elif moved:
                scene.ski.steer=max(-1.,min(1.,dx/max(2,width*.22)))
                self.ski_contacts[slot]=(start[0],start[1],True)
            return True

        def flight_touch(self,slot,x,y,width,height,button,released):
            scene=self.pixel_scene
            flight=scene.glider or scene.road
            if flight.contact is None:
                if button or released or not (0<=x<width and 0<=y<height+1):return False
                flight.contact=(slot,x,y,False)
                return True
            owner,start_x,start_y,moved=flight.contact
            if slot!=owner:return True
            dx,dy=x-start_x,start_y-y
            moved=moved or abs(dx)>.65 or abs(dy)>.45
            if released:
                flight.contact=None
                flight.drag=(0.,0.)
                if not moved:
                    if y>=height:scene.footer(x,width)
                    else:scene.scene_tap(x,y,width,height)
            elif moved:
                flight.contact=(slot,start_x,start_y,True)
                if not flight.menu:
                    flight.drag=(dx/max(1,width*.22),dy/max(1,height*.18))
            return True

        def world_touch(self,slot,x,y,width,height,button,released):
            scene=self.pixel_scene
            if (getattr(scene,'glider',None) or getattr(scene,'road',None)) and not scene.notebook:
                return self.flight_touch(slot,x,y,width,height,button,released)
            if getattr(scene,'ski',None) and not scene.notebook:
                if slot not in self.ski_contacts and (button or released or not (0<=x<width and 0<=y<height)):
                    return False
                return self.ski_touch(slot,x,y,width,height,released)
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
            flight=getattr(self.pixel_scene,'glider',None)
            if flight:flight.cancel_input()
            if getattr(self.pixel_scene,'road',None):self.pixel_scene.road.cancel_input()
            self.grab=None
            self.contacts.clear()
            self.ski_contacts.clear()
            self.optic_fingers.clear()
            self.pinch=None
            self.touch_walk=(0.,0.)
            self.drag_start=None
            self.drag_axes=(0.,0.)
            self.drag_moved=False

        def cancel_keys(self,now=None):
            self.cancel_pointer()
            if hasattr(self.pixel_scene,"shift_keys"):self.pixel_scene.shift_keys.clear()
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
            if (getattr(self.pixel_scene,'glider',None) or getattr(self.pixel_scene,'road',None)) and not self.pixel_scene.notebook:
                return self.flight_touch(-1,x,y,width,self.host.window(self.name).h-3,button,released)
            if getattr(self.pixel_scene,'ski',None) and not self.pixel_scene.notebook:
                self.drag_start=None if released else (x,y)
                return self.ski_touch(-1,x,y,width,self.host.window(self.name).h-3,released)
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

        def ground_key(self,key):
            scene=self.pixel_scene
            if not scene or getattr(scene,'notebook',None) or getattr(scene,'album',None):return False
            if key=='e' and (getattr(scene,'road',None) or getattr(scene,'outing',None) in ('market','tacoma')):
                return scene.change_car()
            if key=='?' and getattr(scene,'road',None):
                scene.pause_game()
                scene.notebook.page='Driving controls'
                return True
            if key=='0' and hasattr(scene,'toggle_ground_view'):
                return scene.toggle_ground_view()
            if key=='0' and getattr(scene,'road',None) and scene.road.has_car_camera:
                scene.road.overhead=not scene.road.overhead
                scene.pixel_dirty=True
                return True
            if getattr(scene,'outing',None)=='hangar' and key in ('e','enter','\r'):
                scene.controller_button(0)
                return True
            if getattr(scene,'bike',None) and key in ('space',' ','enter','\r'):
                scene.bike.pedaling=not scene.bike.pedaling
                return True
            return False

        def flight_key(self,key):
            flight=getattr(self.pixel_scene,'glider',None)
            if getattr(self.pixel_scene,'outing',None) in ('skydive','balloon','scuba') and key in ('space',' ','enter','\r') and flight:
                flight.action();return True
            if flight and key.lower()=='f':flight.toggle_speed();return True
            if flight and flight.powered and key.lower()=='p':
                flight.toggle_motor();return True
            if flight and key in ('space',' ','enter','\r'):
                flight.descending=not flight.descending
                return True
            return False

        def pause_key(self,key,press=True):
            scene=self.pixel_scene
            menu=getattr(scene,'notebook',None)
            paused=hasattr(menu,'button')
            if paused or hasattr(menu,'menu_button'):
                button={'up':11,'down':12,'left':13,'right':14,'enter':0,'\r':0,'space':0,' ':0,'escape':1,'\x1b':1,'pause':6}.get(key)
                if press and button is not None:scene.controller_button(button)
                return True
            if key in ('pause','escape','\x1b') and getattr(scene,'pause_owner',None) and scene.world and not menu:
                if press:scene.controller_button(6)
                return True
            return False

        def key_event(self,key,kind,now):
            if self.pause_key(key,kind=='press'):return True
            scene=self.pixel_scene
            if key=='0' and scene and not getattr(scene,'glider',None):
                if kind=='press':return self.ground_key(key)
                return True
            if key=='e' and (getattr(scene,'road',None) or getattr(scene,'outing',None) in ('market','tacoma')):
                if kind=='press':self.ground_key(key)
                return True
            if getattr(scene,'road',None):
                if key=='?' or (key=='0' and scene.road.has_car_camera):
                    if kind=='press':self.ground_key(key)
                    return True
                road_key={'w':'up','s':'down','a':'left','d':'right'}.get(key,key)
                if road_key in ('left','right','up','down'):
                    if kind=='release':scene.road.keys.discard(road_key)
                    else:scene.road.keys.add(road_key)
                    return True
                if key in (' ','space'):
                    if kind=='press':scene.road.cruise=not scene.road.cruise
                    return True
            if getattr(scene,'outing',None)=='hangar' and key in ('e','enter','\r'):
                if kind=='press':self.ground_key(key)
                return True
            if getattr(scene,'bike',None) and key in ('space',' ','enter'):
                if kind=='press' and self.ground_key(key):return True
            flight=getattr(self.pixel_scene,'glider',None)
            if flight and key in ('left','right','up','down'):
                if kind=='release':flight.keys.discard(key)
                else:flight.keys.add(key)
                return True
            if flight and (key in ('space',' ','enter','f','F') or (flight.powered and key.lower()=='p')):
                if kind=='press':self.flight_key(key)
                return True
            if getattr(self.pixel_scene,'climb',None) and key in ('space',' ','enter'):
                if kind=='press':self.pixel_scene.climb.reach()
                return True
            ski=getattr(self.pixel_scene,'ski',None)
            if ski and key in ('left','right','up','space',' ','enter','r','R','c','C'):
                if kind=='press':self.key(key,now)
                elif kind=='release' and key in ('left','right'):ski.steer=0.
                return True
            return super().key_event(key,kind,now)

        def key(self,key,now=None):
            if self.pause_key(key):return True
            if self.flight_key(key) or self.ground_key(key):return True
            climb=getattr(self.pixel_scene,'climb',None)
            if climb and climb.raised and key.lower()=='g':
                self.pixel_scene.start_glide()
                return True
            if climb and key in (' ','space','enter','\r'):
                climb.reach()
                return True
            ski=getattr(self.pixel_scene,'ski',None)
            if ski:
                if key in ('left','right'):ski.steer=-1. if key=='left' else 1.
                elif key=='up':ski.steer=0.
                elif key in (' ','space','enter','\r'):
                    ski.action({'bottom':ski.finish_action,'climb':'reach'}.get(ski.mode,'brake'))
                elif key.lower()=='r':ski.action('reset')
                elif key.lower()=='c':ski.action('course')
                else:return False
                return True
            if self.pixel_scene and key=='?' and self.pixel_scene.world is not None:
                from pnw.river_notebook import RiverNotebook
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
        settings=(dict(id='touch-controls',label='Touch controls',kind='choice',choices=(WAYPOINT,TWIN_THUMB),default=WAYPOINT),
                  dict(id='flight-horizon',label='Aerial horizon range',kind='choice',choices=('Auto','Local','50 km','80 km','90 km','120 km'),default='Auto'),
                  dict(id='ground-source',label='Local flight surface',kind='choice',choices=('Aerial','Drawn terrain'),default='Aerial'),
                  dict(id='stick-layout',label='Controller sticks',kind='choice',choices=('Standard','Southpaw'),default='Standard'),
                  dict(id='look-speed',label='Controller look',kind='choice',choices=('Gentle','Standard','Quick'),default='Standard'),
                  dict(id='flight-pitch',label='Flight stick pitch',kind='choice',choices=('Pull to climb','Push to climb'),default='Pull to climb'),
                  dict(id='flight-roll',label='Aileron response',kind='choice',choices=('Gentle','Standard','Quick'),default='Standard')),
        help=(('Explore',('W/S walk; A/D strafe; arrows turn.','I/K look up/down; ground follows metre-scale terrain.','O opens saved terrain viewpoints in Scenery.',
                          'Fictional ruins; real elevation data; existing Lab marmot/eagle.')),),factory=create_outdoors)
