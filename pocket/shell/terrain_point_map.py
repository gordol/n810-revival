"""Terrain overlays on the shared Station Map navigation and renderer."""
import math
from pathlib import Path
from app_widgets import Canvas
from station_workspace import StationMap,Context
from offline_map import Plane
from paint import ink,terminal_background

def visible_path(a,b,width,height):
    """Clip before rasterizing so distant endpoints cannot thin the visible line."""
    lo,hi=0.,1.
    for origin,delta,maximum in ((a[0],b[0]-a[0],width-1),(a[1],b[1]-a[1],height-1)):
        if delta==0:
            if not 0<=origin<=maximum:return []
        else:
            left,right=sorted((-origin/delta,(maximum-origin)/delta))
            lo=max(lo,left);hi=min(hi,right)
            if lo>hi:return []
    start=tuple(a[i]+(b[i]-a[i])*lo for i in (0,1))
    end=tuple(a[i]+(b[i]-a[i])*hi for i in (0,1))
    steps=max(1,math.ceil(max(abs(end[i]-start[i]) for i in (0,1))))
    return [(round(start[0]+(end[0]-start[0])*i/steps),round(start[1]+(end[1]-start[1])*i/steps)) for i in range(steps+1)]

class PointMap:
    def __init__(self,select,show_profile,maps=None,base=None):
        self.base=base or StationMap(Context(),Path(__file__).with_name('vendor')/'packet-console',lambda:None,maps=maps)
        self.owns_base=base is None;self.select=select;self.show_profile=show_profile
        self.minimum_span=.01;self.base.minimum_span=.01;self.base.target_box.minimum_span=.01
        self.coverage=None;self.coverage_mode='los';self.nearby=None;self.show_los=None
        self.change_band=None;self.change_radius=None;self.open_heights=None;self.toggle_mode=None;self.toggle_clearance=None;self.clear=None
        self.height_label='2 / 10 m';self.radius_km=5;self.band_label='144.39 MHz';self.mode='path';self.origin_label='LOS origin'
        self.end=False;self.points=[None,None];self.candidates=[];self._layer=None;self._overlay_key=None;self.header_hits=[]
        self.notice='Select From, then To';self._contact=None
        self.qth=None;self.qth_label='QTH';self.inspect_point=None;self.open_call=None;self.go_qth=None;self.fit_path=None;self.inspect_obstruction=None
    def __getattr__(self,name):return getattr(self.base,name)
    @property
    def width(self):return self.base.width
    @width.setter
    def width(self,value):self.base.width=value
    @property
    def height(self):return self.base.height
    @height.setter
    def height(self,value):self.base.height=value
    @property
    def center(self):return self.base.center
    @center.setter
    def center(self,value):self.base.center=value
    @property
    def span(self):return self.base.span
    @span.setter
    def span(self,value):self.base.span=value
    @property
    def image(self):return self.base._shown_image or self.base._image
    @property
    def image_view(self):return self.base._image_view
    def bind_wakeup(self,callback):self.renderer.completion_wakeup=callback
    def position_at(self,x,y):
        image=self.image
        if image is None:return None
        px=(x+.5)*image.width/max(1,self.width)-.5
        py=(y-2+.5)*image.height/max(1,self.height-3)-.5
        projection=image.projection
        if callable(getattr(projection,'unproject',None)):return projection.unproject(px,py)
        center,span=self.image_view or (self.center,self.span)
        aspect=2
        if projection is not None:center,span,aspect=projection.center,projection.span,projection.cell_aspect
        step=span/max(1,image.width-1)/111.32
        return center[0]-(py-(image.height-1)/2)*step*aspect,center[1]+(px-(image.width-1)/2)*step/max(.000001,math.cos(math.radians(center[0])))
    def choose(self,position):
        end=self.end if self.mode=='path' else False
        self.points[int(end)]=tuple(position);self.select(position,end=end)
        if self.mode=='area':self.notice='LOS origin selected · H antenna height'
        elif not end:self.end=True;self.notice='From selected. Tap destination for To'
        else:self.notice='Endpoints selected · P profile'
    def key(self,key):
        if key=='t' and self.toggle_mode:self.toggle_mode();return True
        if key in ('c','delete','backspace') and self.clear:self.clear();return True
        if key in ('a','b') and self.mode=='path':self.end=key=='b';return True
        if key=='p':self.show_profile();return True
        return self.base.key(key)
    def pointer_event(self,event,width):
        _,button,x,y,released=event
        if y==1 and button==0 and not released:
            self._contact=None
            for left,right,callback in self.header_hits:
                if left<=x<right and callback:callback();return True
            return True
        locator=self.base.locator_hit(x,y)
        if not released and button==0 and 2<=y<self.height-1 and not locator and not self.base.full_overview:
            self._contact=(x,y,self.span,False,self.base.target_box.revision)
        elif self._contact and button&32:
            sx,sy,span,moved,revision=self._contact
            left,top,right,bottom=event.bounds
            self._contact=(sx,sy,span,moved or max(abs(left-sx),abs(right-sx),abs(top-sy),abs(bottom-sy))>1,revision)
        contact=self._contact
        position=self.position_at(x,y) if released and contact else None
        handled=self.base.pointer_event(event,width)
        if released:
            self._contact=None
            if self.mode=='path' and contact and position and not contact[3] and abs(x-contact[0])<=1 and abs(y-contact[1])<=1 and self.span==contact[2] and self.base.target_box.revision==contact[4] and self.base.target_box.view is None and self.base._detail_request is None and not locator and not self.base.full_overview:
                self.choose(position)
        return handled
    def pointer(self,x,y,width,button=0,released=False):
        from pointer_events import PointerEvent
        return self.pointer_event(PointerEvent(('mouse',button,x,y,released)),width)
    @property
    def pointer_captured(self):return self.base.pointer_captured
    def cancel_pointer(self):self._contact=None;self.base.cancel_pointer()
    def lines(self):
        previous_layer=self._layer
        lines=list(self.base.lines());layer=self.base.layer();self._layer=layer
        c=Canvas(self.width,self.height)
        if self.mode=='area':
            controls=[('[LOS radius T]',self.toggle_mode),(('[Fresnel 60% J]' if self.coverage_mode=='fresnel' else '[Ground LOS J]'),self.toggle_clearance),('[Clear C]',self.clear),('[Heights H]',self.open_heights),(f'[{self.band_label} F]',self.change_band),(f'[Radius {self.radius_km:g} km R]',self.change_radius),('[LOS L]',self.show_los)]
        else:
            controls=[('[Point path T]',self.toggle_mode),('[From A]',lambda:setattr(self,'end',False)),('[To B]',lambda:setattr(self,'end',True)),('[Clear C]',self.clear),('[Profile P]',self.show_profile),('[Obstruction X]',self.inspect_obstruction),('[QTH Q]',self.go_qth),('[Call G]',self.open_call),('[Fit W]',self.fit_path)]
        x=0;self.header_hits=[]
        if sum(len(label)+1 for label,_ in controls)>self.width:
            replacements={'[LOS radius T]':'[Radius T]','[Clear C]':'[C]','[Heights H]':'[Hts H]','[Band F]':'[Band F]','[LOS L]':'[Calc L]','[Ground LOS J]':'[LOS J]','[Fresnel 60% J]':'[F60% J]'}
            controls=[(replacements.get(label,label),callback) for label,callback in controls]
        for label,callback in controls:
            c.put(x,1,label);self.header_hits.append((x,x+len(label),callback));x+=len(label)+1
        lines[1]=c.lines()[1]
        if self.mode=='area':lines[-1]=(f'{self.radius_km:g} km · roof/remote {self.height_label} · {self.band_label} · '+self.notice)[:self.width].ljust(self.width)
        else:lines[-1]=(self.notice+' · O overview · V direct/preview · S sidebar')[:self.width].ljust(self.width)
        if self.coverage:lines[-1]=(f'{self.coverage_mode.upper()}: red = sampled clear cells/points · gaps untested · J LOS/Fresnel · terrain only')[:self.width].ljust(self.width)
        if layer and self.image:
            key=(id(layer[4]),id(self.coverage),self.coverage_mode,self.mode,tuple(self.points),self.qth,self.qth_label,self.origin_label,id(self.inspect_point),id(self.candidates),
                 self.base.side_overview,self.base.full_overview,self.base.target_box.revision,tuple(self.base._locator_rect[:4]) if self.base._locator_rect else None)
            if key==self._overlay_key:
                if self.inspect_point:lines[-1]=self._inspection_footer
                self._layer=previous_layer;return tuple(lines)
            self._overlay_key=key
            image=self.image;x0,y0,w,h,base=layer;overlay={}
            projection=image.projection or self.renderer.module.Viewport(*(self.image_view or (self.center,self.span)),image.width,image.height)
            # Project overlays into the displayed plane, including scaled overviews.
            class Projection:
                def project(_,lon,lat):
                    x,y=projection.project(lon,lat)
                    return (x+.5)*w/image.width-.5,(y+.5)*h/image.height-.5
            view=Projection()
            if self.coverage:
                house_lat,house_lon=self.coverage.get('center',self.center)
                cx,cy=view.project(house_lon,house_lat)
                px=max(.000001,abs(view.project(house_lon+1/(111.32*math.cos(math.radians(house_lat))),house_lat)[0]-cx))
                py=max(.000001,abs(view.project(house_lon,house_lat+1/111.32)[1]-cy))
                for cell in self.coverage['cells']:
                    lat,lon=cell['position'];x,y=view.project(lon,lat)
                    status=cell['los'] if self.coverage_mode=='los' else cell['fresnel']
                    if status!='clear':continue
                    xx,yy=round(x),round(y)
                    raster=cell.get('raster_km')
                    if raster:
                        # Display a classified raster cell only at its native screen scale.
                        # On further zoom, show its tested centre until refinement arrives.
                        dx=abs(view.project(lon+raster[0]/111.32/max(.1,math.cos(math.radians(lat))),lat)[0]-x)/2
                        dy=abs(view.project(lon,lat+raster[1]/111.32)[1]-y)/2
                        if dx<=2 and dy<=2:
                            for ry in range(max(0,math.ceil(y-dy)),min(h,math.ceil(y+dy))):
                                for rx in range(max(0,math.ceil(x-dx)),min(w,math.ceil(x+dx))):
                                    char,style=base[ry*w+rx]
                                    overlay[ry*w+rx]=terminal_background(' ',ink(180,35,45,background=(180,35,45)),char,style,.55)
                            continue
                    if 0<=xx<w and 0<=yy<h:
                        overlay[yy*w+xx]=('•',ink(255,235,235,background=(155,30,40)))
            if self.mode=='path' and all(self.points):
                a,b=[view.project(point[1],point[0]) for point in self.points]
                for x,y in visible_path(a,b,w,h):
                    if 0<=x<w and 0<=y<h:
                        overlay[y*w+x]=('•',ink(255,240,110,background=(35,30,10)))
            for i,candidate in enumerate(self.candidates[:9]):
                x,y=map(round,view.project(candidate['position'][1],candidate['position'][0]))
                if 0<=x<w and 0<=y<h:
                    overlay[y*w+x]=(str(i+1),ink(255,255,255,background=(35,80,55)))
            if self.qth:
                x,y=map(round,view.project(self.qth[1],self.qth[0]))
                if 0<=x<w and 0<=y<h:
                    for i,char in enumerate(self.qth_label):
                        if x+i<w:overlay[y*w+x+i]=(char,ink(255,255,255,background=(120,30,75)))
            for label,point in zip(('A','B') if self.mode=='path' else (self.origin_label,),self.points if self.mode=='path' else self.points[:1]):
                if point:
                    x,y=map(round,view.project(point[1],point[0]))
                    if 0<=x<w and 0<=y<h:
                        if self.qth and abs(point[0]-self.qth[0])+abs(point[1]-self.qth[1])<1e-5:
                            label='A '+self.qth_label if self.mode=='path' else self.qth_label
                        for i,char in enumerate(label):
                            if x+i<w:overlay[y*w+x+i]=(char,ink(255,255,255,background=(150,30,30)))
            if self.inspect_point:
                lat,lon=self.inspect_point['coordinate'];x,y=map(round,view.project(lon,lat))
                offscreen=not (0<=x<w and 0<=y<h)
                distance=self.inspect_point['distance_m'];margin=self.inspect_point['fresnel_clearance_m']
                lines[-1]=(f"X F60 limiting sample {distance:.1f}m from A · margin {margin:+.2f}m · "+('OFF-SCREEN · W fit path' if offscreen else 'X marked on map'))[:self.width].ljust(self.width)
                self._inspection_footer=lines[-1]
                if offscreen:
                    # Keep an explicit edge marker when inspecting a different part of the path.
                    cx,cy=(w-1)/2,(h-1)/2;dx,dy=x-cx,y-cy
                    scale=min((cx-1)/max(abs(dx),.001),(cy-1)/max(abs(dy),.001))
                    x,y=round(cx+dx*scale),round(cy+dy*scale)
                if 0<=x<w and 0<=y<h:
                    text=f"X {'OFFSCREEN ' if offscreen else 'F60 '}{distance:.0f}m"
                    for dx,dy,char in ((-1,0,'─'),(0,-1,'│'),(0,1,'│')):
                        if 0<=x+dx<w and 0<=y+dy<h:overlay[(y+dy)*w+x+dx]=(char,ink(255,255,255,background=(160,35,0)))
                    overlay[y*w+x]=('X',ink(255,255,255,background=(180,35,0)))
                    label_x=max(0,min(x+2,w-len(text)));label_y=y-2 if y>=2 else min(h-1,y+2)
                    for i,char in enumerate(text):
                        if label_x+i<w:overlay[label_y*w+label_x+i]=(char,ink(255,255,255,background=(160,35,0)))
            rect=self.base._locator_rect
            if rect and self.base.side_overview and not self.base.full_overview:
                left,top,width,height,_=rect
                overlay={i:value for i,value in overlay.items() if not (left-1<=i%w<=left+width and top-1<=i//w+y0<=top+height)}
            self._layer=(x0,y0,w,h,Plane(base,overlay))
        if self.base._detail_request is not None:
            lines[-1]=self.base.zoom_feedback()[:self.width].ljust(self.width)
        return tuple(lines)
    def layer(self):return self._layer
    def close(self):
        self.cancel_pointer()
        if self.owns_base:self.renderer.completion_wakeup=None;self.base.close();self.renderer.close()
