"""Travel choices and the full prepared Rainier elevation grid."""
import math

from geometry import HeightField,Vec


def region_field():
    from rainier_data import download
    from terrain_elevation import grid
    download()
    meta,values=grid()
    nx,nz=meta['nx'],meta['nz']
    if nx*nz>257*257:raise ValueError('Regional walk supports the 257 by 257 Rainier export')
    lat=meta['latitude_first']+(nz-1)*meta['latitude_step']/2
    dx=6371000*math.radians(meta['longitude_step'])*math.cos(math.radians(lat))
    dz=6371000*math.radians(meta['latitude_step'])
    from summit_detail import attach
    field=HeightField(nx,nz,Vec(-(nx-1)*dx/2,0,-(nz-1)*dz/2),dx,dz,values,'meters')
    return attach(field,meta,approach=True)


def bounds(field):
    x,z=field.origin.x,field.origin.z
    return x,x+(field.nx-1)*field.dx,z,z+(field.nz-1)*field.dz


def summit_start(field):
    peak=max(range(len(field.values)),key=field.values.__getitem__)
    x=field.origin.x+(peak%field.nx)*field.dx
    z=field.origin.z+(peak//field.nx)*field.dz
    return x,max(field.origin.z,z-2200.)


class HikeMenu:
    def __init__(self,view):
        self.view=view
        self.trip=False

    def trip_spacing(self):
        return 2 if self.view.host.window(self.view.name).h>=23 else 1

    def lines(self,width):
        v=self.view
        if self.trip:
            rows=['Camp & sky','Season   '+('Summer','Autumn','Winter','Spring')[v.season],
                  'Weather   '+('Clear','Mist','Showers')[v.weather]]
            if not v.regional:rows+=['Visit river overlook','Pack tent' if v.tent else 'Pitch tent at camp',
                                    'Bigfoot story   '+('On' if v.story else 'Off')]
            if not v.party:rows.append('Visit Mt Fremont lookout')
            rows.append('Light   '+('Day','Dusk','Night','12-minute cycle')[v.time_mode])
            if not v.regional:rows.append('Visit trout pool')
            rows.append('Back')
            if self.trip_spacing()==2:return tuple(line for row in rows for line in ('',row))
            return tuple(rows)
        if v.travel_job:return ('Opening terrain…','', 'Preparing the regional elevation map.')
        from rainier_data import installed
        switch='Return to Ohanapecosh' if v.regional else ('Open summit approach' if installed() else 'Download Rainier & hike')
        if v.party:switch='Leave family room to travel'
        outings=('Fish at trout pool','Gather camp supplies','Hot Springs Trail','Silver Falls Loop Trail')
        if v.regional:
            world=getattr(v,'world',None)
            detail=world and getattr(world[0],'inset',None)
            outings=('Put on skis','Climb summit ice') if detail else ()
        return ('Hike','','Pace   '+v.pace_name,'',switch,'','Back to walk','Paradise meadows' if not v.party else '','Camp & sky','Debug overlay   '+('On' if v.debug_overlay else 'Off'),*outings,v.travel_error[:width])

    def tap_xy(self,x,y):
        v=self.view
        if self.trip:
            y//=self.trip_spacing()
            if y==1:v.season=(v.season+1)%4
            elif y==2:v.weather=(v.weather+1)%3
            elif not v.regional and y==3:v.move_to_view();return False
            elif not v.regional and y==4:
                v.tent=not v.tent
                if v.tent:v.move_to_view(camp=True);return False
                v.story=False
            elif not v.regional and y==5:
                v.story=not v.story
                if v.story:v.tent=True;v.move_to_view(camp=True);return False
            elif not v.party and y==(3 if v.regional else 6):
                if v.regional:v.visit_lookout();return False
                self.trip=False
                v.start_region(lookout_arrival=True)
            elif y==(3 if v.regional else 6)+int(not v.party):v.time_mode=(v.time_mode+1)%4
            elif not v.regional and y==7+int(not v.party):v.move_to_view(pool=True);return False
            elif y==(4 if v.regional else 8)+int(not v.party):self.trip=False
            return True
        if v.travel_job:return True
        if v.regional and y==10 and 'Put on skis' in self.lines(40):
            v.start_ski()
            return False
        if v.regional and y==11 and 'Climb summit ice' in self.lines(40):
            v.start_climb()
            return False
        if not v.regional and 10<=y<=13:
            if y==10:v.move_to_view(pool=True)
            elif y==11:v.gathering=True;v.move_to_view(camp=True)
            else:v.visit_trail(('Hot Springs Trail','Silver Falls Loop Trail')[y-12])
            return False
        if y==9:v.debug_overlay=not v.debug_overlay;return False
        if y==7 and not v.party:
            if v.regional:v.visit_meadow();return False
            v.start_region(meadow_arrival=True)
            return True
        if y==8:self.trip=True;return True
        if 1<=y<=2:
            v.pace_index=(v.pace_index+1)%len(v.paces)
        elif 3<=y<=4 and not v.party:
            if v.regional:
                v.return_to_valley()
                return False
            v.start_region()
        elif 5<=y<=7:return False
        return True


class ReliefMap:
    """North-up elevation overview. The terrain image itself is the touch target."""
    def __init__(self,view):
        self.view=view
        self.upload=True
        field=view.world[0]
        nx,nz=field.nx,field.nz
        self.rgb=bytearray()
        for j in reversed(range(nz)):
            for i in range(nx):
                k=j*nx+i
                y=field.values[k]
                slope=(field.values[j*nx+max(i-1,0)]-y)/field.dx
                shade=max(.55,min(1.25,.9+slope*.65))
                base=(63,98,75) if y<1500 else (147,142,103) if y<2600 else (222,226,225)
                self.rgb.extend(min(255,int(c*shade)) for c in base)
        self.rgb=bytes(self.rgb)

    def lines(self,width):return ()

    def frame(self,w,h):
        west,east,south,north=bounds(self.view.world[0])
        scale=min(w/(east-west),(h-48)/(north-south))
        rw=max(1,int((east-west)*scale));rh=max(1,int((north-south)*scale))
        return (w-rw)//2,20+(h-48-rh)//2,rw,rh

    def draw(self,ctx,rect):
        from river_overlay import Ink
        field=self.view.world[0]
        ink=Ink(ctx,rect)
        w,h=rect[2:]
        ink.fill((0,0,w/8,h/16),0x22352EFF)
        x,y,rw,rh=self.frame(w,h)
        self.draw_image(ctx,rect,x,y,rw,rh,field.nx,field.nz)
        west,east,south,north=bounds(field)
        if self.view.meadow_site:
            mx,mz=self.view.meadow_site
            sx=(x+(mx-west)/(east-west)*(rw-1))/8
            sy=(y+(north-mz)/(north-south)*(rh-1))/16
            ink.fill((sx-.25,sy-.125,.5,.25),0xFFABCAFF)
            ink.label(max(0,min(w//8-8,sx+1)),sy-.5,'Paradise',0xFFE0EC)
        px,pz=self.view.camera[:2]
        ink.fill(((x+(px-west)/(east-west)*(rw-1)-2)/8,(y+(north-pz)/(north-south)*(rh-1)-2)/16,.625,.3125),0xFFB52DFF)
        ink.label(0,0,'Tap terrain to start here'[:w//8],0xFFF4CF)
        ink.button((0,h/16-1.5,w//8,1.5),'Back')

    def draw_image(self,ctx,rect,x,y,rw,rh,nx,nz):
        import ctypes as C
        draw=ctx.lib.pocket_scene_river_map
        draw.argtypes=[C.c_void_p]+[C.c_int]*6+[C.c_void_p]
        ctx.check(draw(ctx.handle,rect[0]+x,rect[1]+y,rw,rh,nx,nz,self.rgb if self.upload else None))
        self.upload=False

    def tap_xy(self,x,y):
        window=self.view.host.window(self.view.name)
        w,h=(window.w-2)*8,(window.h-3)*16
        left,top,rw,rh=self.frame(w,h)
        px,py=(x+.5)*8,(y+.5)*16
        if py>=h-24:return False
        if left<=px<left+rw and top<=py<top+rh:
            west,east,south,north=bounds(self.view.world[0])
            self.view.map_position=(west+(east-west)*(px-left)/rw,north-(north-south)*(py-top)/rh)
            return False
        return True


class SummitClimb:
    """A fictional final pitch ending at the highest sample of the summit inset."""
    pitches=10
    stride=8.

    # Bearings from Columbia Crest to the central Sound and neighboring ranges.
    vistas=(('Puget Sound',47.31,-122.50),('Olympics',47.80,-123.71),
            ('Mount St Helens',46.19,-122.19),('Mount Hood',45.37,-121.70),
            ('Mount Adams',46.20,-121.49))

    def next_vista(self):
        self.vista=(self.vista+1)%len(self.vistas)

    def __init__(self,detail,panorama=False):
        self.panorama=panorama
        self.vista=0
        peak=max(range(len(detail.values)),key=detail.values.__getitem__)
        self.x=detail.origin.x+(peak%detail.nx)*detail.dx
        self.z=detail.origin.z+(peak//detail.nx)*detail.dz
        length=self.pitches*self.stride
        headings=[a*math.pi/4 for a in range(8)]
        self.elevation=round(detail.values[peak])
        self.heading=min(headings,key=lambda a:detail.height(
            self.x-length*math.sin(a),self.z-length*math.cos(a)))
        self.grips=0
        self.distance=0.
        self.raised=False
        self.wave=0.

    @property
    def arrived(self):
        return self.distance>=self.pitches*self.stride

    def reach(self):
        if self.raised and self.panorama:self.next_vista()
        elif self.arrived:self.raised=True
        elif self.distance>=self.grips*self.stride:self.grips+=1

    def advance(self,dt,height):
        self.distance=min(self.grips*self.stride,self.distance+dt*10.)
        remaining=self.pitches*self.stride-self.distance
        dx,dz=math.sin(self.heading),math.cos(self.heading)
        x,z=self.x-remaining*dx,self.z-remaining*dz
        if self.raised:
            self.wave+=dt
            if self.panorama:
                _,lat,lon=self.vistas[self.vista]
                yaw=math.atan2((lon+121.7603)*math.cos(math.radians(46.8523)),lat-46.8523)
                return x,z,yaw,.042
            return x,z,self.heading+math.pi,.08
        pitch=-math.atan2(height(x+dx*2,z+dz*2)-height(x,z),2.)
        return x,z,self.heading,pitch*.75

    def controls(self,w,h):
        buttons=[('exit_climb','Walk',(0,0,9,3))]
        if self.raised:
            if self.panorama:buttons.append(('vista','Next view',(w-13,h-5,13,5)))
            return buttons
        if self.arrived:
            buttons.append(('reach','Raise flag',(w//2-7,h-6,14,5)))
        else:
            right=self.grips%2
            buttons.append(('reach','Grip >' if right else '< Grip',
                            (w-15 if right else 1,h//2,14,5)))
        return buttons

    def draw(self,ink,w,h):
        if not self.raised:
            # The planted pick stays high while the other hand swings forward.
            progress=1-(self.grips*self.stride-self.distance)/self.stride
            for side in (0,1):
                active=side==self.grips%2
                x=w*(.2 if side==0 else .8)
                y=h*(.72+.08*math.cos(math.pi*progress) if active else .78)
                lean=1 if side==0 else -1
                for j in range(10):
                    ink.fill((x+lean*j*.13,y+j*.43,.52,.52),0xD88642FF)
                ink.fill((x-1.5,y-.18,3.4,.4),0x617987FF)
                ink.fill((x+lean*1.4,y+.16,.42,.48),0x8CA7B5FF)
            label=f'{self.grips} / {self.pitches}'
            ink.label(w-len(label)-1,1,label,0xFFF6DA)
            return
        # The pennant rises in the foreground, leaving the downhill view open.
        x,y=w*.18,h*.68-min(1.,self.wave)*h*.12
        ink.fill((x,y,.42,h-y),0x654A33FF)
        for i in range(16):
            flutter=.22*math.sin(i*.5-self.wave*5)
            ink.fill((x+.4+i*.5,y+flutter,.52,3*(1-i/16)),0xEC8141FF)
        title=f'Summit!  {self.elevation} m'
        ink.fill(((w-len(title))/2-1,2,len(title)+2,2),0x244B4CE8)
        ink.label((w-len(title))/2,2.5,title,0xFFF2CC)
        if self.panorama:
            label=self.vistas[self.vista][0]
            ink.fill(((w-len(label))/2-1,4,len(label)+2,1.7),0x244B4CE8)
            ink.label((w-len(label))/2,4.2,label,0xFFF2CC)
