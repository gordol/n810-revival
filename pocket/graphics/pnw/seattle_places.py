"""Registered Seattle landmarks in the Sound heightfield's coordinate system."""
import csv
from functools import lru_cache
import math
from pathlib import Path

DECK_HEIGHT=520*.3048
TIP_HEIGHT=605*.3048

@lru_cache(maxsize=1)
def places():
    from pnw.terrain import location
    with (Path(__file__).resolve().parents[1]/'assets/seattle/places.csv').open() as source:
        return {row['name']:location('sound',float(row['latitude']),float(row['longitude']))
                for row in csv.DictReader(source)}

@lru_cache(maxsize=1)
def arcade_origin():
    from pnw.pike_market import offset
    return offset(places()['Pike Place Fish Market'],-2.7,-5.)

def space_needle(height,quad):
    x,z=places()['Space Needle']
    y=height(x,z)
    def ring(cx,cz,h,r,n):
        return [(cx+r*math.cos(i*math.tau/n),y+h,cz+r*math.sin(i*math.tau/n)) for i in range(n)]
    def loft(rings,colors):
        for a,b,color in zip(rings,rings[1:],colors):
            for i in range(len(a)):
                j=(i+1)%len(a)
                light=.79+.19*math.cos(i*math.tau/len(a)-.6)
                quad((a[i],a[j],b[j],b[i]),tuple(light*c for c in color))
    ivory=(.89,.88,.82)
    steel=(.48,.52,.51)
    glass=(.25,.37,.41)
    loft([ring(x,z,h,r,20) for h,r in ((0,5.4),(145,4.0))],[steel])
    for i in range(3):
        angle=i*math.tau/3
        for offset in (-.08,.08):
            rings=[ring(x+r*math.cos(angle+offset),z+r*math.sin(angle+offset),h,width,8)
                   for h,r,width in ((0,17,1.8),(25,13,1.5),(78,6.2,1.35),(110,7.2,1.35),(148,15,1.7))]
            loft(rings,[ivory]*4)
    # Published visitor deck and tip heights are 520 and 605 feet.
    profile=((0,16),(4,17),(7,8))
    loft([ring(x,z,h,r,48) for h,r in profile],[glass,ivory])
    profile=((141,4),(148,16),(151.7,21),(154,19.7),(DECK_HEIGHT,18),(160,18.1),
             (162.7,13),(164.2,6),(166.7,3),(TIP_HEIGHT,.12))
    loft([ring(x,z,h,r,64) for h,r in profile],[steel,ivory,ivory,glass,ivory,ivory,ivory,steel,ivory])

    loft([ring(x,z,DECK_HEIGHT-.3,21.3,64),ring(x,z,DECK_HEIGHT,21.3,64),
          ring(x,z,DECK_HEIGHT,17.9,64)],[steel,ivory])
    loft([ring(x,z,DECK_HEIGHT+1.00,21.3,64),ring(x,z,DECK_HEIGHT+1.04,21.3,64)],[steel])
    for i in range(64):
        a=i*math.tau/64
        px,pz=x+21.3*math.cos(a),z+21.3*math.sin(a)
        loft([ring(px,pz,DECK_HEIGHT,.045,4),ring(px,pz,DECK_HEIGHT+1,.045,4)],[steel])


@lru_cache(maxsize=1)
def delivery_route():
    from pnw.terrain import location
    points=[]
    with (Path(__file__).resolve().parents[1]/'assets/seattle/delivery.csv').open() as source:
        for row in csv.DictReader(source):
            pos=location('sound',float(row['latitude']),float(row['longitude']))
            if not points or points[-1]!=pos:points.append(pos)
    return tuple(points)


@lru_cache(maxsize=2)
def street_lines(city):
    from pnw.terrain import location
    import json
    source=Path(__file__).resolve().parents[1]/'assets/seattle'/('tacoma-streets.json' if city=='tacoma' else 'streets.json')
    return tuple((name,kind,tuple(location('sound',lat/1e7,lon/1e7) for lon,lat,*_ in coords),
                  {'primary':8.,'secondary':7.,'tertiary':5.5,'pedestrian':3.}.get(kind,4.4),tuple(len(c)==3 for c in coords))
                 for name,kind,coords in json.loads(source.read_text()).values())

@lru_cache(maxsize=1)
def tacoma_corridor():
    import json
    from pnw.terrain import location
    source=Path(__file__).resolve().parents[1]/'assets/seattle/seattle-tacoma.json'
    lines=[]
    for name,coords in json.loads(source.read_text()):
        points=tuple(location('sound',lat,lon) for lon,lat in coords)
        freeway=name=='I 5'
        lines.append((name,'freeway' if freeway else 'connector',points,6.2 if freeway else 3.6,(False,)*len(points)))
    return tuple(lines)

@lru_cache(maxsize=2)
def driving_lanes(corridor_only=False):
    cells={}
    lines=tacoma_corridor() if corridor_only else (*street_lines('seattle'),*street_lines('tacoma'),*tacoma_corridor(),('Delivery','access',delivery_route(),3.,()))
    if not corridor_only:
        lines=(*lines,*((name,kind,list(reversed(before))+points+after,width,())
                        for name,kind,width,points,before,after in overpasses() if kind!='footway'))
    for _,kind,points,width,_ in lines:
        if kind=='pedestrian':continue
        for (x,z),(ex,ez) in zip(points,points[1:]):
            dx,dz=ex-x,ez-z
            length2=dx*dx+dz*dz
            if not length2:continue
            segment=(x,z,dx,dz,length2,width)
            for i in range(math.floor((min(x,ex)-width)/32),math.floor((max(x,ex)+width)/32)+1):
                for j in range(math.floor((min(z,ez)-width)/32),math.floor((max(z,ez)+width)/32)+1):
                    cells.setdefault((i,j),[]).append(segment)
    return cells

@lru_cache(maxsize=8)
def nearby_driving_segments(cx,cz,reach,corridor_only):
    cells=driving_lanes(corridor_only)
    return tuple({segment for i in range(cx-reach,cx+reach+1) for j in range(cz-reach,cz+reach+1)
                  for segment in cells.get((i,j),())})

def on_road(x,z):
    for ox,oz,dx,dz,length2,width in driving_lanes().get((math.floor(x/32),math.floor(z/32)),()):
        t=max(0.,min(1.,((x-ox)*dx+(z-oz)*dz)/length2))
        if math.hypot(x-ox-t*dx,z-oz-t*dz)<=width:return True
    return False

@lru_cache(maxsize=1)
def corridor_path():
    """Centreline chainage in metres, indexed for nearby traffic and guidance."""
    spans=[];ends=[];cells={};distance=0.
    for name,kind,points,width,_ in tacoma_corridor():
        for (x,z),(ex,ez) in zip(points,points[1:]):
            length=math.hypot(ex-x,ez-z)
            if not length:continue
            span=(distance,x,z,(ex-x)/length,(ez-z)/length,length,name,kind,width)
            for i in range(math.floor((min(x,ex)-24)/64),math.floor((max(x,ex)+24)/64)+1):
                for j in range(math.floor((min(z,ez)-24)/64),math.floor((max(z,ez)+24)/64)+1):
                    cells.setdefault((i,j),[]).append(span)
            spans.append(span);distance+=length;ends.append(distance)
    return spans,ends,cells

@lru_cache(maxsize=1)
def corridor_milestones():
    distance=0.;marks=[]
    for name,kind,points,_,_ in tacoma_corridor():
        if name=='Ramp' and not marks:marks.append((distance,points[0],'I-5 ramp'))
        distance+=sum(math.dist(a,b) for a,b in zip(points,points[1:]))
        if name=='Ramp':marks.append((distance,points[-1],'Merge onto I-5' if len(marks)==1 else 'Ramp end'))
        if kind=='freeway':marks.append((distance,points[-1],'I-5 S · Exit'))
    marks.append((distance,points[-1],'Dock Street'))
    return tuple(marks)

def corridor_position(x,z):
    _,_,cells=corridor_path()
    best=None;gap=math.inf
    for start,ox,oz,dx,dz,length,name,kind,width in cells.get((math.floor(x/64),math.floor(z/64)),()):
        t=max(0.,min(length,(x-ox)*dx+(z-oz)*dz))
        error=math.hypot(x-ox-t*dx,z-oz-t*dz)
        if error<gap and error<=width+2:
            best=(start+t,name,kind);gap=error
    return best

def corridor_sample(distance,lane):
    from bisect import bisect_left
    spans,ends,_=corridor_path()
    start,x,z,dx,dz,*_=spans[min(bisect_left(ends,distance),len(ends)-1)]
    along=distance-start
    return x+dx*along+dz*lane,z+dz*along-dx*lane,math.atan2(dx,dz)

def streets(height,quad,field=None):
    def pavement(points,color,material,lift):
        # Split where the DEM changes slope, including the diagonal inside each cell.
        faces=[points]
        if field:
            origin=field.origin;step=field.dx
            for a,b,offset in ((1,0,origin.x),(0,1,origin.z),(1,1,origin.x+origin.z)):
                values=[a*x+b*z-offset for x,z in points]
                for k in range(math.floor(min(values)/step)+1,math.ceil(max(values)/step)):
                    split=[]
                    for face in faces:
                        parts=([],[])
                        for (x,z),(ex,ez) in zip(face,face[1:]+face[:1]):
                            d=a*x+b*z-offset-k*step;e=a*ex+b*ez-offset-k*step
                            if d<=0:parts[0].append((x,z))
                            if d>=0:parts[1].append((x,z))
                            if d*e<0:
                                t=d/(d-e);point=(x+t*(ex-x),z+t*(ez-z))
                                for part in parts:part.append(point)
                        split.extend(part for part in parts if len(part)>=3)
                    faces=split
        for face in faces:
            vertices=[(x,height(x,z)+lift,z) for x,z in face]
            if len(vertices)==4:quad(vertices,color,material)
            else:
                for i in range(1,len(vertices)-1):
                    quad((vertices[0],vertices[i],vertices[i+1],vertices[i+1]),color,material)
    junctions={}
    for name,kind,points,half,crossings in (*tacoma_corridor(),*street_lines('seattle'),*street_lines('tacoma')):
        for pt in (points[0],points[-1]):junctions.setdefault(pt,set()).add(name)
        # Adjacent road strips share a cross-section, through each bend.
        def normal(a,b):
            dx,dz=b[0]-a[0],b[1]-a[1]
            length=math.hypot(dx,dz)
            return (dz/length,-dx/length) if length else (0.,0.)
        normals=[normal(a,b) for a,b in zip(points,points[1:])]
        def join(a,b):
            divisor=1+a[0]*b[0]+a[1]*b[1]
            if divisor<.25:return b
            return ((a[0]+b[0])/divisor,(a[1]+b[1])/divisor)
        edges=[normals[0],*(join(a,b) for a,b in zip(normals,normals[1:])),normals[-1]]
        for i,((x,z),(ex,ez)) in enumerate(zip(points,points[1:])):
            length=math.hypot(ex-x,ez-z)
            if length<.2:continue
            dx,dz=(ex-x)/length,(ez-z)/length
            def offset_point(d,w):
                f=d/length
                a,b=edges[i:i+2]
                return (x+d*dx+w*(a[0]+f*(b[0]-a[0])),
                        z+d*dz+w*(a[1]+f*(b[1]-a[1])))
            def band(left,right,t,end,lift,color,material=0.):
                corners=[]
                for d,w in ((t,left),(end,left),(end,right),(t,right)):
                    px,pz=offset_point(d,w)
                    corners.append((px,pz))
                pavement(corners,color,.249 if left==-half and right==half else material,lift)
            for t in range(0,math.ceil(length),16):
                end=min(length,t+16)
                if kind in ('freeway','connector'):
                    band(-half,half,t,end,.032,(.25,.26,.265))
                    band(-half,-half+.13,t,end,.039,(.86,.76,.45))
                    band(half-.14,half,t,end,.039,(.85,.85,.80))
                    if kind=='freeway':
                        # A profiled concrete median follows the grade at each end.
                        profile=((-half-.75,0.),(-half-.63,.40),(-half-.57,.84),
                                 (-half-.36,.84),(-half-.31,.40),(-half-.12,0.))
                        for (u,h),(v,k),shade in zip(profile,profile[1:],(.43,.54,.67,.58,.49)):
                            wall=[]
                            for along,lateral,rise in ((t,u,h),(end,u,h),(end,v,k),(t,v,k)):
                                px,pz=offset_point(along,lateral)
                                wall.append((px,height(px,pz)+rise,pz))
                            quad(wall,(shade,shade*.99,shade*.95),0.)
                        for stripe in (-half/3,half/3):
                            band(stripe,stripe+.14,t,min(t+4,end),.039,(.84,.84,.8))
                    continue
                band(-half,half,t,end,.045,(.25,.26,.255))
                for side in (-1,1):
                    band(side*half,side*(half+1.8),t,end,.14,(.57,.55,.50),.260)
                if kind in ('primary','secondary'):
                    band(-.07,.07,t,min(end,t+5),.068,(.83,.68,.35))
            if crossings[i]:
                for n in range(-int(half),int(half)):
                    band(n+.12,n+.54,0.,min(2.8,length),.092,(.79,.78,.71))
    from pnw.market_visit import lettering
    entrance,merge,exit_mark,*_=corridor_milestones()
    signs=[(entrance[0]-35,'I-5 SOUTH'),(merge[0]+65,'SOUTH  I-5'),
           (exit_mark[0]-300,'TACOMA  EXIT')]
    signs.extend((along,'I-5  TACOMA') for along in range(5500,int(exit_mark[0])-500,12000))
    for along,label in signs:
        x,z,angle=corridor_sample(along,9.4)
        py=height(x,z)
        dx,dz=math.sin(angle),math.cos(angle)
        def sign_face(points,color):
            quad([(x+u*dz+offset*dx,py+h,z-u*dx+offset*dz) for u,h,offset in points],color)
        for lateral in (-1.3,1.3):
            sign_face([(lateral-.06,0,.06),(lateral+.06,0,.06),(lateral+.06,4,.06),
                       (lateral-.06,4,.06)],(.46,.49,.47))
        for width,bottom,top,offset,color in ((2.,2.4,4.,0.,(.85,.88,.83)),
                (1.94,2.46,3.94,-.01,(.035,.25,.15))):
            sign_face([(-width,bottom,offset),(width,bottom,offset),(width,top,offset),
                       (-width,top,offset)],color)
        lettering(label,-1.76,2.94,-.025,.48,sign_face,(.96,.97,.88),board_width=3.52)
    for (x,z),names in junctions.items():
        if '2nd Avenue' not in names or len(names)<2:continue
        name=next(iter(sorted(names-{'2nd Avenue'})))
        x+=6.6;y=height(x,z)
        quad(((x-.05,y,z),(x+.05,y,z),(x+.05,y+2.9,z),(x-.05,y+2.9,z)),(.39,.43,.40))
        quad(((x-1.1,y+2.50,z),(x+1.1,y+2.50,z),(x+1.1,y+2.89,z),(x-1.1,y+2.89,z)),(.11,.29,.22))
        lettering(name,x-.97,y+2.60,z-.012,.23,quad,(.92,.92,.84),board_width=1.94)


@lru_cache(maxsize=1)
def overpasses():
    import json
    from pnw.terrain import location
    source=Path(__file__).resolve().parents[1]/'assets/seattle/overpasses.json'
    spans=[]
    project=lambda coords:[location('sound',*p) for p in coords]
    for name,kind,lanes,coords,before,after in json.loads(source.read_text()).values():
        points=[location('sound',*p) for p in coords]
        width=1.5 if kind=='footway' else (int(lanes)*3.45+2.)*.5
        spans.append((name,kind,width,points,project(before),project(after)))
    return spans


def bridge_spans(height):
    for bridge,(_,kind,half,points,before,after) in enumerate(overpasses()):
        lengths=[math.dist(a,b) for a,b in zip(points,points[1:])]
        total=sum(lengths)
        grade=max(-.045,min(.045,(height(*points[-1])-height(*points[0]))/total))
        along=0.;base=height(*points[0])
        for point,length in zip(points,lengths+[0.]):
            base=max(base,height(*point)-grade*along)
            along+=length
        lead,road,tail=before,points,after
        path=list(reversed(lead))+road+tail
        chain=-sum(math.dist(a,b) for a,b in zip([road[0]]+lead,lead))
        start=chain
        end=total+sum(math.dist(a,b) for a,b in zip([road[-1]]+tail,tail))
        def elevation(point,d):
            deck=base+5.8+grade*min(total,max(0.,d))
            weight=(d-start)/(-start) if d<0 and start<0 else (end-d)/(end-total) if d>total and end>total else 1.
            bed=height(*point)+.055
            return bed+(deck-bed)*max(0.,min(1.,weight))
        for a,b in zip(path,path[1:]):
            length=math.dist(a,b)
            if length<.01:continue
            y=elevation(a,chain);top=elevation(b,chain+length)
            yield bridge,kind,half,a,b,length,y,(top-y)/length
            chain+=length


class BridgeRoads:
    """Track which road surface a car entered at a stacked crossing."""
    def __init__(self,height):
        self.cells={}
        for span in bridge_spans(height):
            _,kind,w,(x,z),(u,v),_,_,_=span
            if kind=='footway':continue
            for i in range(math.floor((min(x,u)-w)/32),math.floor((max(x,u)+w)/32)+1):
                for j in range(math.floor((min(z,v)-w)/32),math.floor((max(z,v)+w)/32)+1):
                    self.cells.setdefault((i,j),[]).append(span)
        self.deck=None

    def sample(self,x,z,ground,update=False):
        best=None
        for bridge,_,width,(ax,az),(bx,bz),length,y,grade in self.cells.get((math.floor(x/32),math.floor(z/32)),()):
            dx,dz=(bx-ax)/length,(bz-az)/length
            along=max(0.,min(length,(x-ax)*dx+(z-az)*dz))
            gap=math.hypot(x-ax-dx*along,z-az-dz*along)
            top=y+grade*along
            if gap<=width and (bridge==self.deck or update and abs(top-ground)<.85):
                candidate=(bridge!=self.deck,gap,bridge,top)
                if best is None or candidate<best:best=candidate
        if update:self.deck=best[2] if best else None
        return best[3] if best else ground


def bridge_mesh(height,quad,box):
    for _,kind,half,(x,z),(ex,ez),length,base,grade in bridge_spans(height):
        dx,dz=(ex-x)/length,(ez-z)/length
        def strip(left,h1,right,h2,color,material=0.):
            quad([(x+dx*t+dz*u,base+t*grade+h,z+dz*t-dx*u)
                  for t,u,h in ((0,left,h1),(length,left,h1),(length,right,h2),(0,right,h2))],color,material)
        strip(-half,0,half,0,(.30,.31,.31),.249)
        strip(-half,-.8,half,-.8,(.27,.28,.27))
        for side in (-1,1):
            edge=side*half
            strip(edge,-.8,edge,.75,(.48,.48,.45))
            strip(edge,.75,edge-side*.24,.75,(.63,.63,.59))
            strip(edge-side*.24,.75,edge-side*.24,0,(.54,.54,.51))
        if kind!='footway':strip(half-.55,.012,half-.42,.012,(.89,.87,.77))
        for offset in range(16,math.ceil(length),32):
            px,pz=x+dx*offset,z+dz*offset
            if not on_road(px,pz):
                y=height(px,pz)-.2
                box(px,pz,y,1.3,half,max(.1,base-.8+grade*offset-y),(.49,.48,.45),rotation=(dx,dz))


def roadside_trees(height,quad):
    import json
    import random
    from pnw.terrain import location
    source=Path(__file__).resolve().parents[1]/'assets/seattle/freeway-trees.json'
    trees,woods=json.loads(source.read_text())
    project=lambda point:location('sound',point[1]/1e7,point[0]/1e7)
    positions=[project(point) for point in trees]
    rng=random.Random(3205)
    for ring in woods:
        points=[project(point) for point in ring]
        xs,zs=zip(*points)
        for gx in range(math.floor(min(xs)),math.ceil(max(xs)),11):
            for gz in range(math.floor(min(zs)),math.ceil(max(zs)),11):
                x,z=gx+rng.uniform(0,11),gz+rng.uniform(0,11)
                crossings=sum((az>z)!=(bz>z) and x<ax+(bx-ax)*(z-az)/(bz-az)
                              for (ax,az),(bx,bz) in zip(points,points[1:]))
                if crossings%2:positions.append((x,z))
    for x,z in positions:
        if on_road(x,z):continue
        base=height(x,z)
        h=rng.uniform(5.,13.)
        spread=rng.uniform(.20,.35)*h
        green=rng.uniform(.25,.39)
        angle=rng.uniform(0,math.tau)
        previous=None
        for rise,radius in ((0,.18),(.44,.14),(.35,spread*.48),(.58,spread),(.81,spread*.78),(1.,.12)):
            ring=[]
            for j in range(7):
                a=angle+math.tau*j/7
                r=radius*rng.uniform(.83,1.12)
                ring.append((x+r*math.cos(a),base+h*rise+rng.uniform(-.04,.04)*radius,z+r*math.sin(a)))
            if previous:
                for j in range(7):
                    k=(j+1)%7
                    light=.65+.22*math.cos(angle+math.tau*j/7)+rise*.22
                    tone=(.23,.18,.13) if radius==.14 else (.15,green,.14)
                    quad((previous[j],previous[k],ring[k],ring[j]),tuple(c*light for c in tone),0. if radius==.14 else .512)
            previous=ring


def buildings(height,quad):
    from pnw.terrain import location
    import json
    source=Path(__file__).resolve().parents[1]/'assets/seattle/buildings.json'
    arcade=arcade_origin()
    for way,(metric,value,outline,roof) in json.loads(source.read_text()).items():
        if way=='12903132':continue  # Render the observation tower separately.
        points=[location('sound',lat/1e7,lon/1e7) for lon,lat in outline]
        cx=sum(x for x,_ in points)/len(points)
        cz=sum(z for _,z in points)/len(points)
        if math.dist((cx,cz),arcade)<65:continue
        levels=value if metric=='building:levels' else None
        rise=levels*3.15 if levels else value
        base=height(cx,cz)
        top=base+rise
        facade=.229 if rise>=45 else .228
        tone=((.47,.54,.56),(.62,.56,.48),(.53,.43,.36),(.63,.64,.61))[int(way)%4]
        for (x,z),(ex,ez) in zip(points,points[1:]+points[:1]):
            norm=math.hypot(ex-x,ez-z)
            if norm==0:continue
            light=.82+.13*(ex-x)/norm+.09*(ez-z)/norm
            quad(((x,height(x,z)-1,z),(ex,height(ex,ez)-1,ez),(ex,top,ez),(x,top,z)),
                 tuple(light*c for c in tone),facade if abs(ex-x)>=abs(ez-z) else facade-.002)
        for a,b,c in zip(roof[::3],roof[1::3],roof[2::3]):
            quad([(points[k][0],top,points[k][1]) for k in (a,b,c,c)],(.47,.48,.46))

@lru_cache(maxsize=1)
def market_shops():
    from pnw.pike_market import offset
    shops={k:v for k,v in places().items() if k not in ('Space Needle','Ballard Clay')}
    # Bearings lead to the reconstructed shop fronts inside the playable arcade.
    shops['Flower farm table']=offset(arcade_origin(),-4,4.5)
    shops['Sunny Honey Company']=offset(arcade_origin(),8,4.5)
    for name,u in (('MarketSpice',-12),('Pure Food Fish',12),("Sosio's Produce",20),('Chukar Cherries',24)):
        shops[name]=offset(arcade_origin(),u,4.5)
    return shops

class MarketDirectory:
    def __init__(self,view):
        self.view=view
        self.names=list(market_shops())

    def lines(self,width):
        return ('Market directory','','Choose a shop for a bearing.','',
                *self.names,'','Clear bearing','Back')

    def tap_xy(self,x,y):
        labels=self.lines(80)
        label=labels[int(y)] if 0<=y<len(labels) else ''
        if label in self.names:self.view.shop_target=label
        elif label=='Clear bearing':self.view.shop_target=None
        elif label!='Back':return True
        return False

def bearing_label(name,x,z):
    tx,tz=market_shops()[name]
    degrees=math.degrees(math.atan2(tx-x,tz-z))%360.
    compass=('N','NE','E','SE','S','SW','W','NW')[int((degrees+22.5)//45)%8]
    return f'{name}  {round(math.hypot(tx-x,tz-z))} m {compass}'
