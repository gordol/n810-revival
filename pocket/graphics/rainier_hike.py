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
    return HeightField(nx,nz,Vec(-(nx-1)*dx/2,0,-(nz-1)*dz/2),dx,dz,values,'meters')


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
        return 2 if self.view.host.window(self.view.name).h>=19 else 1

    def lines(self,width):
        v=self.view
        if self.trip:
            rows=['Camp & sky','Season   '+('Summer','Autumn','Winter','Spring')[v.season],
                  'Weather   '+('Mist' if v.mist else 'Clear')]
            if not v.regional:rows+=['Visit river overlook','Pack tent' if v.tent else 'Pitch tent at camp',
                                    'Bigfoot story   '+('On' if v.story else 'Off')]
            if not v.party:rows.append('Visit Mt Fremont lookout')
            rows.append('Back')
            if self.trip_spacing()==2:return tuple(line for row in rows for line in ('',row))
            return tuple(rows)
        if v.travel_job:return ('Opening terrain…','', 'Preparing the regional elevation map.')
        from rainier_data import installed
        switch='Return to Ohanapecosh' if v.regional else ('Open summit approach' if installed() else 'Download Rainier & hike')
        if v.party:switch='Leave family room to travel'
        return ('Hike','','Pace   '+v.pace_name,'',switch,'','Back to walk','','Camp & sky',v.travel_error[:width])

    def tap_xy(self,x,y):
        v=self.view
        if self.trip:
            y//=self.trip_spacing()
            if y==1:v.season=(v.season+1)%4
            elif y==2:v.mist=not v.mist
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
            elif y==(3 if v.regional else 6)+int(not v.party):self.trip=False
            return True
        if v.travel_job:return True
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
        import ctypes as C
        from river_overlay import Ink
        field=self.view.world[0]
        ink=Ink(ctx,rect)
        w,h=rect[2:]
        ink.fill((0,0,w/8,h/16),0x22352EFF)
        x,y,rw,rh=self.frame(w,h)
        # The source grid has angular cells. Present the overview in metres.
        draw=ctx.lib.pocket_scene_river_map
        draw.argtypes=[C.c_void_p]+[C.c_int]*6+[C.c_void_p]
        ctx.check(draw(ctx.handle,rect[0]+x,rect[1]+y,rw,rh,field.nx,field.nz,self.rgb if self.upload else None))
        self.upload=False
        west,east,south,north=bounds(field)
        px,pz=self.view.camera[:2]
        ink.fill(((x+(px-west)/(east-west)*(rw-1)-2)/8,(y+(north-pz)/(north-south)*(rh-1)-2)/16,.625,.3125),0xFFB52DFF)
        ink.label(0,0,'Tap terrain to start here'[:w//8],0xFFF4CF)
        ink.button((0,h/16-1.5,w//8,1.5),'Back')

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
