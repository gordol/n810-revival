"""Playable interpretations of the public DownUnder levels and waterfront landmarks."""
from array import array
import math
import random
from functools import lru_cache

FLOORS={'down5':('Sound View Cafe',"Ruby's Seattle Gift Gallery"),
        'down4':('Golden Age Collectables','Market Magic Shop'),
        'down3':('Gradient Art Gallery','Antique Touch')}
DESTINATIONS={'Belltown walk':'belltown','Colman Dock':'colman','Bainbridge landing':'bainbridge','DownUnder level 5':'down5','DownUnder level 4':'down4','DownUnder level 3':'down3',
              'Post Alley and Gum Wall':'gum','Overlook Walk':'overlook','Lumen Field':'stadiums','T-Mobile Park':'ballpark','Coffee and piroshky':'bakery'}
SITES={'belltown':(47.6140337,-122.3456787),'colman':(47.6028952,-122.3398411),'bainbridge':(47.6221412,-122.5095054),'gum':(47.60836,-122.34027),'overlook':(47.60991,-122.34355),
       'stadiums':(47.5952,-122.3321),'ballpark':(47.5914,-122.3325),'bakery':(47.60993,-122.34246)}

STREETS=frozenset(SITES) | {'market','fishshop','needle'}

@lru_cache(maxsize=None)
def site(key):
    from pnw.terrain import location
    return location('sound',*SITES[key])

@lru_cache(maxsize=1)
def storefront_frame():
    # Adjacent frontage vertices from the bundled OSM way 367894552.
    from pnw.terrain import location
    x,z=location('sound',47.6099559,-122.3425691)
    ex,ez=location('sound',47.6097481,-122.3422163)
    length=math.hypot(ex-x,ez-z)
    return x,z,(ex-x)/length,(ez-z)/length

def storefront_point(across,depth):
    x,z,c,s=storefront_frame()
    return x+c*across-s*depth,z+s*across+c*depth

def deck_height(ground,x,z):
    cx,cz=site('overlook')
    base=ground(cx,cz)+5.
    if -6<=x-cx<=6 and -38<=z-cz<=20:
        return base-max(0.,math.floor((cz-z)/.90))*.13
    return ground(x,z)

def arrival(key):
    if key in FLOORS:return -3.75,-7.,.04,0.
    x,z=site(key)
    if key in ('colman','bainbridge'):
        side=1 if key=='colman' else -1
        return x+side*22,z,-side*math.pi/2,0.
    if key=='belltown':return x,z,-.6,-.02
    if key=='bakery':
        _,_,c,s=storefront_frame()
        return *storefront_point(1,-8),math.atan2(-s,c)+.22,.02
    if key=='gum':return x,z-12,0.,0.
    if key=='overlook':return x-3.1,z+17,math.pi-.14,.09
    if key=='ballpark':return x+245,z-104,-1.17,-.08
    return x-234,z+225,2.32,-.09

@lru_cache(maxsize=1)
def sign_art():
    import json
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parents[1]/'assets/seattle/signs.json').read_text())

@lru_cache(maxsize=1)
def sign_font():
    """Tessellate the shared outlines once. Even-odd spans preserve counters."""
    data=sign_art()
    result={}
    for char,(advance,paths) in data['glyphs'].items():
        edges=[];heights=set()
        for path in paths:
            pts=list(zip(path[::2],path[1::2]))
            for a,b in zip(pts,pts[1:]+pts[:1]):
                if a[1]==b[1]:continue
                if a[1]>b[1]:a,b=b,a
                edges.append((a,b));heights.update((a[1],b[1]))
        spans=[];levels=sorted(heights)
        for lo,hi in zip(levels,levels[1:]):
            cuts=[]
            for (x,y),(xx,yy) in edges:
                if y<=lo and yy>=hi:
                    slope=(xx-x)/(yy-y)
                    cuts.append((x+(lo-y)*slope,x+(hi-y)*slope))
            cuts.sort(key=sum)
            for l,r in zip(cuts[::2],cuts[1::2]):
                spans.append(((l[0],lo),(r[0],lo),(r[1],hi),(l[1],hi)))
        result[char]=advance,spans
    return result

def lettering(text,x,y,z,size,quad,color,board_width=None):
    font=sign_font()
    # Vertical size is cap height. Preserve proportional advances inside
    # the signboard width originally allocated by the scene.
    width=sum(font.get(c,font[' '])[0] for c in text)
    sx=min(size/200,len(text)*size*.80/max(1,width))
    if board_width is not None and width:
        size=min(size,200*board_width/width)
        sx=min(sx,size/200)
        x+=(board_width-width*sx)/2
    for char in text:
        advance,spans=font.get(char,font[' '])
        for span in spans:quad([(x+px*sx,y+py*size/200,z) for px,py in span],color)
        x+=advance*sx

def stairs(key,x,z):
    if z>=-5:return 0.
    steps=min(18,max(0,int((-5-z)/.40)))
    if -2<=x<0:return steps*.095
    if 0<=x<=2 and key!='down3':return -steps*.095
    return 0.

def stair_exit(key,x,z):
    if z> -11.35:return None
    level=int(key[-1])
    if -2<=x<0:return 'market' if level==5 else f'down{level+1}'
    if 0<=x<=2 and level>3:return f'down{level-1}'
    return None

def floor_furniture(key):
    yield (0.,8.5,.20,9.)
    for x in (-4.,4.):
        if key!='down5' or x>0:yield (x,6.4,2.2,.94)
    if key=='down5':
        for x in (-5.8,-2.2):
            for z in (7.,10.8):yield (x,z,1.3,1.55)
    if key=='down4':
        for x in (-6.48,6.48):
            for k in range(5):yield (x,-5+k*2.9,1.3,1.78)

def walk_inside(key,x,z):
    x=max(-7.65,min(7.65,x));z=max(-12.65,min(11.65,z))
    for cx,cz,w,d in floor_furniture(key):
        dx,dz=x-cx,z-cz
        ex,ez=w/2+.18-abs(dx),d/2+.18-abs(dz)
        if ex>0 and ez>0:
            if ex<ez:x+=math.copysign(ex,dx)
            else:z+=math.copysign(ez,dz)
    return x,z

def indoor(key,*,prepare=False):
    from pnw.river_scene_cache import regional_mesh
    from geometry import Vec
    from pnw.summit_detail import RegionalTerrain
    mesh=regional_mesh(key,b'',False,lambda:indoor_mesh(key),prepare=prepare)
    if prepare:return
    field=RegionalTerrain(17,27,Vec(-8,0,-13),1,1,(0,)*(17*27),'meters')
    count=len(mesh)//7
    return field,Vec(0,0,0),mesh,count,array('I',[0]),(),count,None

def indoor_mesh(key):
    mesh=array('f')
    def quad(p,c,m=0.):
        for i in (0,1,2,0,2,3):mesh.extend((*p[i],*c,m))
    def box(x,y,z,w,h,d,c):
        pts=[(x+sx*w/2,y,z+sz*d/2) for sx,sz in ((-1,-1),(1,-1),(1,1),(-1,1))]
        top=[(px,y+h,pz) for px,_,pz in pts];quad(top,c,.253)
        for i in range(4):
            j=(i+1)%4
            quad((pts[i],pts[j],top[j],top[i]),tuple(v*(.82+.04*i) for v in c),.253)
    def vessel(x,y,z,rings,color):
        # Revolved profiles share rims; the open lip shows the shaded interior.
        segments=14
        for k in range(segments):
            a,b=math.tau*k/segments,math.tau*(k+1)/segments
            def rim(t,r,h):return x+r*math.cos(t),y+h,z+r*math.sin(t)
            for (r,h),(rr,hh) in zip(rings,rings[1:]):
                shade=.86+.14*math.cos(a)
                quad((rim(a,r,h),rim(b,r,h),rim(b,rr,hh),rim(a,rr,hh)),
                     tuple(c*shade for c in color))
            r,h=rings[-1]
            quad((rim(a,r,h),rim(b,r,h),rim(b,.78*r,h-.025),rim(a,.78*r,h-.025)),
                 tuple(v*.62 for v in color))
    rng=random.Random(int(key[-1]))
    wood=(.43,.30,.20);cream=(.83,.76,.61)
    for row in range(52):
        for col in range(8):
            x=-7+2*col;z=-12.75+.5*row
            light=rng.uniform(.83,1.)
            if z< -5 and (x==-1 or (x==1 and key!='down3')):continue
            quad(((x-1,0,z-.25),(x+1,0,z-.25),(x+1,0,z+.25),(x-1,0,z+.25)),
                 tuple(v*light for v in wood),.252)
    for dx,direction in ((-1,1),(1,-1)):
        if key=='down3' and direction<0:continue
        for j in range(20):
            z=-5.2-j*.40
            top=stairs(key,dx,z)
            box(dx,top-.15,z,2,.15,.40,(.50,.46,.40))
            box(dx,top,z+.18,1.97,.009,.028,(.75,.68,.54))
        for j in range(18):
            z=-5.2-j*.4
            y=stairs(key,dx,z)
            box(dx+dx*.93,y+.86,z,.055,.06,.42,(.47,.38,.23))
            if j%4==0:box(dx+dx*.93,y,z,.045,.88,.045,wood)
        box(dx,2.1,-4.9,1.98,.52,.10,(.19,.26,.24))
        level=int(key[-1])
        label=('Market' if level==5 else f'Up to {level+1}') if dx<0 else f'Down to {level-1}'
        lettering(label,dx-.85,2.21,-4.82,.20,
                  lambda points,c:quad([(2*dx-x,y,z) for x,y,z in points],c),cream)
    quad(((-8,3.6,-13),(-8,3.6,13),(8,3.6,13),(8,3.6,-13)),cream)
    for x in (-8,8):box(x,0,0,.15,3.6,26,cream)
    for z in (-13,13):box(0,0,z,16,3.6,.15,cream)
    for z in range(-10,12,4):
        box(0,3.34,z,16,.16,.16,wood)
        box(0,3.12,z,.04,.27,.04,wood)
        box(0,3.02,z,.58,.11,.42,(1.,.90,.59))
    for side,name in enumerate(FLOORS[key]):
        x=-4 if not side else 4
        box(x,2.32,4,7.4,.65,.16,(.18,.19,.19))
        size=min(.40,6.8/(len(name)*.8))
        lettering(name,x-len(name)*size*.4,2.48,3.9,size,quad,(.99,.72,.43))
        # A featured display stands just inside each shop entrance.
        if key!='down5' or side:
            box(x,0,6.4,1.82,.77,.68,wood)
            box(x,.77,6.4,2.20,.08,.94,cream)
            if key=='down4' and side:
                for k in range(3):
                    vessel(x-.62+.49*k,.85,6.4,((.13,0),(.066,.20),(.07,.21)),(.70,.51,.28))
                for k in range(5):box(x+.70,.85+.018*k,6.4,.19,.018,.28,(.62,.15,.15))
            elif key=='down3' and side:
                for k in range(3):
                    xx=x-.70+k*.63
                    box(xx,.85,6.4,.45,.39+.04*k,.25,wood)
                    vessel(xx,1.24+.04*k,6.4,((.20,0),(.16,.09),(.06,.14)),(.66,.50,.28))
                    quad(((xx-.15,.91,6.26),(xx+.15,.91,6.26),(xx+.15,1.19,6.26),(xx-.15,1.19,6.26)),cream)
                    lettering('XII',xx-.09,1.09,6.25,.055,quad,wood)
                    box(xx,.98,6.246,.015,.11,.008,wood)
            elif key=='down5':
                for k in range(5):
                    xx=x-.78+k*.38
                    vessel(xx,.85,6.4,((.08,0),(.12,.15),(.08,.24),(.05,.27)),(.18+.09*k,.45,.56))
            else:
                for k in range(4):
                    xx=x-.79+.52*k
                    box(xx,.85,6.4,.43,.55,.045,wood)
                    box(xx,.88,6.365,.39,.49,.012,cream)
                    tone=(.16+.08*k,.35,.48)
                    quad(((xx-.16,.95,6.35),(xx+.16,.95,6.35),(xx+.16,1.30,6.35),(xx-.16,1.30,6.35)),tone)
                    quad(((xx-.16,.98,6.34),(xx+.16,.98,6.34),(xx+.04,1.22,6.34),(xx+.04,1.22,6.34)),(.73,.66,.47))
                    if key=='down4':lettering('COMICS',xx-.14,1.24,6.33,.06,quad,cream)
        else:
            box(-6.8,0,12.25,1.9,.92,.8,wood)
            box(-6.8,.92,12.24,.85,.46,.54,(.26,.46,.43))
            box(-6.8,1.29,11.94,.78,.10,.20,(.62,.65,.61))
            for xx in (-7.02,-6.58):
                vessel(xx,.92,11.97,((.055,0),(.075,.11),(.076,.12)),cream)
        if key=='down5' and side==0:
            for dx in (-1.8,1.8):
                for z in (7.,10.8):
                    box(x+dx,.72,z,1.28,.09,.86,wood)
                    box(x+dx,0,z,.12,.72,.12,wood)
                    vessel(x+dx-.24,.81,z+.12,((.07,0),(.095,.12),(.10,.13)),cream)
                    vessel(x+dx+.23,.81,z-.08,((.09,0),(.16,.025),(.17,.031)),(.74,.77,.68))
                    for dz in (-.65,.65):
                        box(x+dx,.38,z+dz,.52,.08,.48,wood)
                        box(x+dx,0,z+dz,.22,.38,.22,wood)
        else:
            for shelf in range(4):
                y=.42+shelf*.52
                box(x,y,12.25,6.8,.08,.77,wood)
                for k in range(13):
                    color=rng.choice(((.35,.52,.57),(.76,.38,.28),(.67,.61,.39),(.46,.40,.53)))
                    xx=x-3+k*.49
                    if key=='down3' and side or key=='down5':
                        neck=rng.uniform(.045,.095);h=rng.uniform(.21,.37)
                        vessel(xx,y+.08,12.12,((.08,0),(.14,.09),(.12,h*.65),(neck,h*.9),(neck+.012,h)),color)
                    elif key=='down4' and side:
                        # Card decks and nested magician's cups.
                        if k%2:vessel(xx,y+.08,12.12,((.12,0),(.073,.18),(.07,.19)),(.64,.47,.25))
                        else:
                            for j in range(3):
                                box(xx,y+.08+j*.05,12.14,.28,.046,.18,color if j%2 else cream)
                    else:
                        box(xx,y+.08,12.14,.36,rng.uniform(.20,.42),.18,color)
        if key=='down3' and not side:
            # Matted prints and canvases on the gallery wall.
            for k in range(5):
                zz=-7+k*3.45
                wx=x*1.96
                box(wx,1.15,zz,.15,1.2,1.35,wood)
                box(wx-side*.24+.12,1.23,zz,.17,1.02,1.18,cream)
                box(wx-side*.42+.21,1.34,zz,.12,.79,.94,(.23+.06*k,.40,.43))
        elif key=='down4':
            for k in range(5):
                zz=-5+k*2.9
                box(x*1.62,.14,zz,1.3,.8,1.78,wood)
                for j in range(8):
                    box(x*1.62,.94,zz-.7+j*.19,1.,.28,.045,
                        rng.choice(((.76,.35,.28),(.27,.48,.59),(.88,.72,.32))))
        elif side==0:
            for zz in range(-9,12,4):
                box(-7.85,1.14,zz,.17,1.44,3.4,(.40,.57,.63))
                box(-7.74,1.16,zz,.11,1.40,.06,wood)
        if side:
            # Wall displays face into the shop so they read from the aisle.
            for i in range(4):
                zz=3.4+2.3*i
                if key=='down3':
                    def clock_point(angle,r):
                        return (7.81,1.81+r*math.cos(angle),zz+r*math.sin(angle))
                    box(7.89,1.24,zz,.14,1.14,.88,wood)
                    for tick in range(12):
                        a=tick*math.tau/12;b=a+math.tau/12
                        quad(((7.81,1.81,zz),clock_point(a,.37),clock_point(b,.37),(7.81,1.81,zz)),cream)
                        box(7.798,1.79+.31*math.cos(a),zz+.31*math.sin(a),.01,.035,.035,wood)
                    box(7.785,1.81,zz,.012,.23,.022,wood)
                    box(7.785,1.80,zz-.15,.012,.02,.30,wood)
                else:
                    box(7.90,.91,zz,.14,1.22,1.02,wood)
                    box(7.80,1.,zz,.04,1.04,.88,cream)
                    x=7.77
                    if key=='down4':
                        quad(((x,1.14,zz),(x,1.54,zz-.30),(x,1.93,zz),(x,1.54,zz+.30)),(.60,.14,.17))
                    else:
                        quad(((x,1.16,zz-.35),(x,1.16,zz+.35),(x,1.80,zz+.1),(x,1.80,zz+.1)),(.22,.43,.44))
        # Doors into the two bays stay open on either side of the centre post.
    # The return sign faces shoppers as they leave either display bay.
    box(0,2.53,2.7,3.0,.49,.09,(.16,.24,.22))
    lettering('Stairs to Market',-1.31,2.66,-2.76,.19,
              lambda points,c:quad([(-x,y,-z) for x,y,z in points],c),cream)
    box(0,0,8.5,.20,3.35,9.,wood)
    return mesh

@lru_cache(maxsize=4)
def counter_item(kind):
    """Local, metre-scale faces shared by the shop display and held purchase."""
    faces=[]
    def face(points,color):
        faces.append((tuple(points),tuple(color)))
    def ring_surface(profile):
        for (h,r,color),(hh,rr,_) in zip(profile,profile[1:]):
            for i in range(32):
                a,b=i*math.tau/32,(i+1)*math.tau/32
                def point(t,y,r):return r*math.sin(t),y,-r*math.cos(t)
                light=.87+.13*math.cos(a+.65)
                face((point(a,h,r),point(b,h,r),point(b,hh,rr),point(a,hh,rr)),[v*light for v in color])
    if kind=='coffee':
        paper=(.98,.97,.92);lid=(.92,.90,.84)
        ring_surface(((0,.032,paper),(.005,.034,paper),(.119,.045,paper),(.121,.0475,lid),
                      (.126,.0475,lid),(.128,.044,lid),(.136,.042,lid),(.139,.041,lid),
                      (.139,.032,lid),(.135,.030,lid),(.135,0,lid)))
        face(((-.008,.1395,-.038),(.008,.1395,-.038),(.007,.1395,-.035),(-.007,.1395,-.035)),(.14,.12,.10))
        rows=sign_art()['siren']
        def logo(u,v):
            y=.088-.048*v
            a=(u-.5)*1.22
            r=.034+(y-.005)*(.011/.114)+.00035
            return r*math.sin(a),y,-r*math.cos(a)
        for i,row in enumerate(rows):
            for left,right in zip(row[::2],row[1::2]):
                for start in range(left,right,4):
                    end=min(start+4,right)
                    face(tuple(logo(u/64,v/64) for u,v in ((start,i),(end,i),(end,i+1),(start,i+1))),(.00,.39,.25))
        return faces
    # A pinched oval, a fish-shaped salmon pie and a coiled apple bun.
    fish=kind=='salmon';roll=kind=='apple'
    def crust(t,p):
        radius=math.cos(p)
        x=math.cos(t)*radius;z=math.sin(t)*radius
        h=math.sin(p)
        crimp=math.exp(-18*z*z)*(.5+.5*math.cos(31*x+5*z)) if not roll else .5+.5*math.cos(17*radius-2*t)
        return (.102*x,.016+.042*h+.006*crimp*h,.067*z*(1-.32*x*x) if not roll else .078*z),crimp
    for i in range(32):
        for j in range(7):
            pts=[];score=0
            for u,v in ((i,j),(i+1,j),(i+1,j+1),(i,j+1)):
                pt,score=crust(u*math.tau/32,-.38+v*(math.pi/2+.38)/7)
                pts.append(pt)
            glaze=.68+.27*math.sin((j+1)*math.pi/10)+.06*math.cos(i*.59)+.07*score
            face(pts,(.92*glaze,(.49+.13*score)*glaze,(.17+.07*score)*glaze))
    if fish:
        face(((.068,.021,0),(.137,.017,-.047),(.128,.031,0),(.137,.017,.047)),(.78,.42,.13))
        for j in range(3):
            x=-.030+.034*j
            face(((x-.014,.052,-.016),(x,.059,0),(x-.014,.052,.016),(x+.006,.057,0)),(.61,.33,.14))
    return faces

@lru_cache(maxsize=2)
def held_item(kind):
    packed=array('f')
    for points,color in counter_item(kind):
        for i in (0,1,2,0,2,3):packed.extend((*points[i],*color))
    return packed

def storefronts(ground,world_quad,world_box):
    _,_,c,s=storefront_frame()
    def quad(points,color):
        vertices=[]
        for across,y,depth in points:
            x,z=storefront_point(across,depth)
            vertices.append((x,y,z))
        world_quad(vertices,color)
    def box(across,depth,y,w,d,h,color,material=0.):
        x,z=storefront_point(across,depth)
        world_box(x,z,y,w,d,h,color,material,rotation=(c,s))
    for i,(name,color) in enumerate((('Piroshky Piroshky',(.42,.16,.11)),('Starbucks Coffee',(.13,.27,.21)))):
        x,z=4-10.6*i,-.85;y=ground(*storefront_point(x,z))
        box(x,z+2,y-.5,7.2,4.2,4.4,(.44,.36,.28))
        for bay in range(3):
            wx=x-2.28+2.28*bay
            box(wx,z-.24,y+1.13,2.18,.055,1.16,(.31,.40,.38),.244)
            box(wx-1.1,z-.28,y+.96,.075,.10,1.40,color)
            box(wx,z-.29,y+2.10,2.18,.08,.055,(.67,.53,.32))
            box(wx,z-.33,y+2.28,1.88,.09,.045,(.98,.83,.53),.247)
        box(x,z-.18,y+2.36,7.15,.15,.75,color)
        lettering(name,x-3.27,y+2.52,z-.27,.44,quad,(.98,.90,.70))
        # Front counter sits clear of the mapped building shell.
        box(x,z-.98,y,5.4,1.06,.84,(.34,.23,.15))
        box(x,z-.98,y+.84,5.48,1.12,.065,(.66,.54,.40))
        def display(kind,across,depth,base,angle=0.):
            ca,sa=math.cos(angle),math.sin(angle)
            for points,tone in counter_item(kind):
                quad([(across+ca*u+sa*v,base+h,depth-sa*u+ca*v) for u,h,v in points],tone)
        if i==0:
            # Three sheet pans under a brass-framed sloped sneeze guard.
            for k,(product,title) in enumerate((('salmon','Smoked salmon'),('piroshky','Beef & onion'),('apple','Apple cinnamon'))):
                tx=x-1.65+1.65*k
                box(tx,z-1.02,y+.905,1.54,.82,.030,(.54,.54,.50))
                box(tx,z-1.02,y+.936,1.48,.76,.004,(.91,.84,.69))
                for row in range(2):
                    for n in range(5-(row==1 and k==2)):
                        display(product,tx-.56+n*.28,z-1.19+row*.34,y+.94,.09*math.sin(n*7+k))
                box(tx,z-1.48,y+.91,.8,.035,.18,(.96,.91,.76))
                lettering(title,tx-.37,y+.967,z-1.502,.071,quad,(.19,.12,.07))
            for dx in (-2.59,-.83,.83,2.59):
                box(x+dx,z-1.49,y+.905,.032,.035,.42,(.64,.53,.32))
            for depth in (-1.49,-.64):
                box(x,z+depth,y+1.32,5.24,.024,.023,(.72,.64,.47))
            box(x,z-.65,y+1.30,5.14,.034,.018,(1.,.86,.63),.247)
        else:
            steel=(.65,.68,.66);rubber=(.12,.13,.12)
            mx=x-.55
            box(mx,z-.98,y+.905,1.12,.54,.075,steel)
            box(mx,z-.79,y+.98,1.08,.20,.37,(.13,.29,.23))
            box(mx,z-.96,y+1.32,1.15,.48,.17,steel)
            for k in range(3):
                xx=mx-.37+k*.37
                box(xx,z-1.14,y+1.22,.13,.11,.11,steel)
                box(xx+.086,z-1.23,y+1.256,.18,.048,.04,rubber)
                for n in range(3):
                    box(xx-.07+n*.068,z-1.209,y+1.39,.041,.015,.036,(.12,.15,.14))
            for n in range(18):box(mx-.49+n*.056,z-1.10,y+.983,.013,.26,.006,rubber)
            box(mx+.54,z-1.14,y+1.07,.019,.02,.26,steel)
            # Burr grinder with a tapered bean hopper and dosing chute.
            gx=mx-1.
            box(gx,z-.94,y+.905,.26,.29,.36,rubber)
            for k in range(20):
                a,b=k*math.tau/20,(k+1)*math.tau/20
                def hopper(t,r,h):return gx+r*math.cos(t),y+h,z-.94+r*math.sin(t)
                for lo,hi,r,rr,tone in ((1.26,1.33,.066,.13,(.51,.47,.39)),(1.33,1.51,.13,.14,(.32,.22,.16)),(1.51,1.54,.145,.145,rubber),(1.54,1.54,.145,0,rubber)):
                    quad((hopper(a,r,lo),hopper(b,r,lo),hopper(b,rr,hi),hopper(a,rr,hi)),tone)
            for n in range(4):display('coffee',mx+.67+.16*n,z-1.20,y+.905)
            box(x+1.65,z-.93,y+.905,.25,.22,.055,rubber)
            box(x+1.65,z-.93,y+.96,.055,.060,.15,steel)
            box(x+1.65,z-.94,y+1.1,.34,.045,.22,rubber)
            box(x+1.65,z-.97,y+1.13,.30,.008,.16,(.34,.50,.46))

ALLEY_LAMPS=(-10.,0.,10.)

def alley_lamps(ground):
    x,z=site('gum')
    return [(x-1.97,ground(x,z+dz)+3.09,z+dz) for dz in ALLEY_LAMPS]

def outdoor(ground,quad,box):
    storefronts(ground,quad,box)
    for key,side in (('colman',1),('bainbridge',-1)):
        cx,cz=site(key)
        for j in range(24):
            x=cx+side*(j+.5)*3
            y=ground(x,cz)+.18
            box(x,cz,y-.24,3.02,7,.24,(.46,.43,.35))
            for edge in (-3.35,3.35):
                box(x,cz+edge,y,.095,.095,1.,(.44,.49,.49))
                box(x,cz+edge,y+.97,3.02,.07,.065,(.51,.56,.55))
        for j in (3,5,7):
            x=cx+side*j*3
            for edge in (-2.8,2.8):
                box(x,cz+edge,ground(x,cz),.18,.18,3.5,(.24,.33,.32))
        box(cx+side*15,cz,ground(cx+side*15,cz)+3.48,16,7.4,.28,(.22,.34,.32))
    cx,cz=site('gum')
    rng=random.Random(1428)
    for side in (-1,1):
        for j in range(48):
            z=cz-16+j*.65
            y=ground(cx,z)
            for k in range(10):
                x=cx+side*2.55
                zz=z+(.30 if k%2 else 0)
                dense=side<0 and 7<=j<=39 and 1<=k<=8
                box(x,zz,y+k*.24,.36,.63,.225,(rng.uniform(.38,.50),.22,.17),.255 if dense else 0.)
            x=cx+side*2.35
            for _ in range(42):
                zz=z+rng.random()*.63;yy=y+.25+rng.random()*1.88
                r=rng.uniform(.018,.061)
                quad(((x,yy+r,zz),(x,yy,zz+r),(x,yy-r*.74,zz),(x,yy,zz-r)),rng.choice(
                     ((.85,.28,.43),(.31,.66,.70),(.78,.68,.37),(.68,.42,.65),(.80,.75,.66))))
            if side<0 and 9<=j<=38:
                # Gum folds over the projecting sill and stretches into tapered strands.
                box(x+.025,z+.31,y+1.82,.18,.66,.08,(.45,.28,.24),.255)
                for strand in range(6):
                    zz=z+strand*.105+rng.uniform(0,.045)
                    drop=rng.uniform(.035,.25)
                    tone=rng.choice(((.85,.30,.36),(.89,.69,.11),(.21,.65,.50),(.82,.47,.65)))
                    quad(((x+.12,y+1.90,zz-.024),(x+.12,y+1.90,zz+.023),
                          (x+.10,y+1.87-drop,zz+.009),(x+.095,y+1.86-drop,zz)),tone)
    # Upper brickwork, conduit and a canopy of bridges enclose Post Alley.
    for side in (-1,1):
        for j in range(6):
            zz=cz-13.5+j*5
            y=ground(cx,zz)
            box(cx+side*2.60,zz,y+2.37,.38,5.02,4.45,(.39,.26,.22),.251)
            box(cx+side*2.37,zz,y+4.15,.13,5.,.10,(.24,.20,.18))
            box(cx+side*2.35,zz,y+4.42,.11,1.36,1.48,(.21,.28,.29),.244)
            box(cx+side*2.27,zz,y+4.38,.20,1.57,.09,(.55,.48,.42))
            box(cx+side*2.25,zz,y+4.45,.06,.045,1.46,(.24,.22,.19))
            if j%2==0:box(cx+side*2.29,zz+1.93,y,.092,.092,5.9,(.31,.32,.29))
    for x,y,z in alley_lamps(ground):
        box(x-.22,z,y+.24,.48,.055,.06,(.19,.18,.16))
        box(x,z,y+.10,.08,.08,.19,(.24,.23,.19))
        box(x,z,y,.25,.25,.12,(1.,.80,.46),.247)
        box(x,z,y+.12,.33,.33,.055,(.24,.21,.18))
    for dz in (-6.,8.):
        z=cz+dz;y=ground(cx,z)
        box(cx,z,y+4.32,5.22,1.82,.20,(.23,.23,.21))
        for edge in (-.84,.84):
            box(cx,z+edge,y+4.52,5.2,.07,.87,(.26,.25,.23))
    for dz in (-8.,4.):
        z=cz+dz;y=ground(cx,z)
        box(cx+1.74,z,y+.051,.44,1.12,.026,(.12,.14,.14))
        for n in range(10):box(cx+1.74,z-.49+.108*n,y+.077,.40,.028,.011,(.38,.39,.36))
    for row in range(94):
        z=cz-16+row*.33
        for col in range(8):
            x=cx-2.5+(col+.5)*.625
            tone=rng.uniform(.34,.46)
            quad(tuple((px,ground(px,pz)+.033,pz) for px,pz in
                       ((x-.307,z),(x+.307,z),(x+.307,z+.322),(x-.307,z+.322))),
                 (tone,tone*.87,tone*.76),.254)
    cx,cz=site('overlook')
    for i in range(64):
        z=cz+19.6-.90*i
        y=deck_height(ground,cx,z)
        tone=.53+.055*(i%3)
        box(cx,z,y-.23,12,.893,.23,(tone,tone*.95,tone*.87))
        for dx in (-3,0,3):
            box(cx+dx,z,y,.022,.90,.008,(.37,.36,.34))
        for side in (-1,1):
            x=cx+side*5.85
            box(x,z,y+.94,.09,.92,.075,(.40,.42,.39))
            if i%2==0:box(x,z,y,.07,.07,.96,(.42,.44,.40))
        if i in (3,9,15):
            box(cx-4.8,z,y,1.6,2.8,.46,(.53,.36,.22))
            box(cx-5.5,z,y+.46,.12,2.8,.42,(.47,.32,.22))
        if i in (4,10,16):
            box(cx+4,z,y,1.1,2.7,.54,(.47,.38,.29))
            for k in range(65):
                px=cx+4+rng.uniform(-.43,.43);pz=z+rng.uniform(-1.16,1.16)
                dx,dz=rng.uniform(-.21,.21),rng.uniform(-.21,.21)
                top=y+.54+rng.uniform(.25,.52)
                quad(((px-.032,y+.54,pz),(px+.032,y+.54,pz),(px+dx,top,pz+dz),(px+dx,top,pz+dz)),
                     rng.choice(((.33,.45,.21),(.48,.52,.26),(.31,.39,.19))))
    for key,rx,rz in (('stadiums',101,126),('ballpark',105,99)):
        x,z=site(key);y=ground(x,z)
        for j in range(64):
            a,b=j*math.tau/64,(j+1)*math.tau/64
            def rim(t,r,h):return x+r*rx*math.cos(t),y+h,z+r*rz*math.sin(t)
            quad((rim(a,1,0),rim(b,1,0),rim(b,1,22),rim(a,1,22)),(.46,.49,.47))
            quad((rim(a,1,22),rim(b,1,22),rim(b,.71,5),rim(a,.71,5)),(.22,.33,.37))
            if key=='stadiums' and abs(math.cos(a))>.55:
                h=27+19*math.cos(a)**2
                quad((rim(a,1.09,h),rim(b,1.09,h),rim(b,.71,h-2),rim(a,.71,h-2)),(.77,.80,.80))
            box(x+rx*math.cos(a),z+rz*math.sin(a),y,1.6,2.0,23.,(.66,.65,.60))
            if j%2==0:
                quad((rim(a,1.008,4),rim(b,1.008,4),rim(b,1.008,15),rim(a,1.008,15)),(.29,.36,.38))
        if key=='stadiums':
            for side in (-1,1):
                for j in range(32):
                    a,b=j/32,(j+1)/32
                    def arch(t,h):
                        return (x+side*rx*.87,y+25+28*math.sin(math.pi*t)+h,z+(2*t-1)*rz)
                    quad((arch(a,0),arch(b,0),arch(b,2.2),arch(a,2.2)),(.91,.91,.85))
                    quad((arch(a,-6),arch(b,-6),arch(b,-5),arch(a,-5)),(.73,.77,.76))
                    quad((arch(a,-5),arch(a+.006,-5),arch(b,0),arch(b-.006,0)),(.77,.80,.79))
                    quad((arch(a,0),arch(b,0),(arch(b,0)[0]-side*28,arch(b,0)[1]-3,arch(b,0)[2]),
                          (arch(a,0)[0]-side*28,arch(a,0)[1]-3,arch(a,0)[2])),(.81,.82,.80))
        if key=='ballpark':
            for j in range(6):
                box(x+68,z-79+j*29,y+29,86,27,3.6,(.32,.39,.37))

class DistrictMap:
    """Pocket map with a street inset and a cutaway of the shopping floors."""
    # Map coordinates are schematic; vertically stacked shops need a cutaway.
    pins=(('needle','Space Needle',.25,.015),('overlook','Overlook Walk',.13,.29),('bakery','Coffee / bakery',.51,.16),
          ('market','Main Arcade',.69,.38),('gum','Gum Wall',.75,.57),
          ('belltown','Belltown',.83,.035),('colman','Ferry dock',.26,.85),('wheel','Great Wheel',.18,.69),('stadiums','Lumen Field',.71,.80),
          ('ballpark','T-Mobile Park',.78,.94))

    def __init__(self,view):self.view=view
    def lines(self,width):return ()

    def targets(self,w,h):
        top=2;mh=h-10
        for key,label,px,py in self.pins:
            x=min(w-len(label)-1,max(1,int(px*w)-len(label)//2))
            yield key,label,(x,top+int(py*mh),len(label)+1,2)
        for i,key in enumerate(('down3','down4','down5')):
            third=w//3
            yield key,'Level '+key[-1],(i*third,h-5,third,2)
        yield None,'Back',(0,h-2,w,2)

    def draw(self,ctx,rect):
        from pnw.river_overlay import Ink
        ink=Ink(ctx,rect);w,h=rect[2]//8,rect[3]//16
        ink.fill((0,0,w,h),0x243C46FF)
        mh=h-10
        for j in range(mh):
            shore=w*(.21+.15*(1-j/mh))
            ink.fill((shore,2+j,w-shore,1),0x475249FF)
            for k in range(4):
                ink.fill((shore+2+w*.14*k,2+j,w*.085,.76),0x555F54FF)
        ink.label(1,0,'Pike Place & waterfront',0xF7EDCC)
        ink.label(1,h-7,'DownUnder',0xE9CEA4)
        for key,label,box in self.targets(w,h):
            x,y,bw,bh=box
            ink.fill(box,0xAD683FFF if key==self.view.outing else 0x293C34EF)
            ink.label(x+max(0,(bw-len(label))//2),y+.4,label,0xFFF4D8)

    def tap_xy(self,x,y):
        win=self.view.host.window(self.view.name)
        for key,_,(left,top,w,h) in self.targets(win.w-2,win.h-3):
            if left<=x<left+w and top<=y<top+h:
                if key and key!=self.view.outing:self.view.start_outing(key)
                return False
        return True
