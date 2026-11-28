"""Page nearby buildings, trees and places from the offline regional inventory."""
from array import array
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import sqlite3
import zlib
from pnw.terrain import location

ASSETS=Path(__file__).resolve().parents[1]/'assets/seattle'

@lru_cache(maxsize=1)
def authored_sites():
    sites=set()
    for _,_,outline,_ in json.loads((ASSETS/'buildings.json').read_text()).values():
        points=[location('sound',lat/1e7,lon/1e7) for lon,lat in outline]
        x,z=map(lambda c:sum(c)/len(c),zip(*points))
        sites.add((round(x/4),round(z/4)))
    return sites

def roof_faces(points):
    # Ear clipping keeps L-shaped roofs out of streets and adjacent courtyards.
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    ring=list(dict.fromkeys(points))
    if sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(ring,ring[1:]+ring[:1]))<0:ring.reverse()
    while len(ring)>=3:
        for i,b in enumerate(ring):
            a,c=ring[i-1],ring[(i+1)%len(ring)]
            if cross(a,b,c)<=0:continue
            if any(p not in (a,b,c) and min(cross(a,b,p),cross(b,c,p),cross(c,a,p))>0 for p in ring):continue
            yield a,b,c
            ring.pop(i);break
        else:return

def database_path():
    configured=os.environ.get('POCKET_REGION_SCENERY')
    folder=Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')
    full=Path(configured) if configured else folder/'pocket/rainier-walk/puget-sound-scenery.sqlite'
    return full if full.is_file() else ASSETS/'neighborhoods.sqlite'


@lru_cache(maxsize=1)
def airport_road_cells():
    from pnw.seattle_places import street_lines
    cells={}
    for _,kind,points,width,_ in street_lines('airports'):
        for (x,z),(ex,ez) in zip(points,points[1:]):
            length=math.hypot(ex-x,ez-z)
            if length<.1:continue
            side_x=(ez-z)*width/length
            side_z=(x-ex)*width/length
            count=math.ceil(length/16)
            for i in range(count):
                a,b=i/count,(i+1)/count
                ax,az=x+a*(ex-x),z+a*(ez-z)
                bx,bz=x+b*(ex-x),z+b*(ez-z)
                tile=math.floor((ax+bx)/1024),math.floor((az+bz)/1024)
                cells.setdefault(tile,[]).append(((ax-side_x,az-side_z),(bx-side_x,bz-side_z),
                                                   (bx+side_x,bz+side_z),(ax+side_x,az+side_z)))
    return cells


class Neighborhood:
    def __init__(self):
        self.db=sqlite3.connect(f'{database_path().resolve().as_uri()}?mode=ro',uri=True)
        self.cell=None
        self.places=[]
        self.signals=[]
        self.parking={}

    def close(self):self.db.close()

    def update(self,x,z,ground):
        cell=(math.floor(x/512),math.floor(z/512))
        if self.cell==cell:return None
        self.cell=cell
        mesh=array('f');self.places=[];self.signals=[];self.parking={}
        def face(vertices,color,material):
            for px,py,pz in vertices:mesh.extend((px,py,pz,*color,material))
        services=service_signs(x,z,ground,face)
        for tx,tz in sorted(((cell[0]+dx,cell[1]+dz) for dx in (-1,0,1) for dz in (-1,0,1)),
                            key=lambda ij:math.hypot(x-(ij[0]+.5)*512,z-(ij[1]+.5)*512)):
            from pnw.regional_roads import tile
            road_quads=list(airport_road_cells().get((tx,tz),()))
            for ax,az,dx,dz,l2,w in tile(database_path().resolve(),tx,tz):
                length=math.sqrt(l2)
                nx,nz=dz*w/length,-dx*w/length
                bx,bz=ax+dx,az+dz
                road_quads.append(((ax-nx,az-nz),(bx-nx,bz-nz),(bx+nx,bz+nz),(ax+nx,az+nz)))
            for corners in road_quads:
                if len(mesh)//7>=246000:break
                a,b,c,d=((u,ground(u,v)+.095,v) for u,v in corners)
                face((a,b,c,a,c,d),(.27,.28,.28),.249)
            for kind,blob in self.db.execute('SELECT model,data FROM features WHERE tx=? AND tz=?',(tx,tz)):
                row=json.loads(zlib.decompress(blob))
                if kind=='signal':
                    self.signals.append((row[0]/10,row[1]/10));continue
                if kind=='place':
                    px,pz,name=row;self.places.append((px/10,pz/10,name));continue
                if len(mesh)//7>247000:continue
                if kind=='tree':
                    px,pz=row[0]/10,row[1]/10;y=ground(px,pz);r=2.1
                    foliage=(.17,.32+(row[0]%12)*.006,.17)
                    for i in range(5):
                        a=i*math.tau/5;b=(i+1)*math.tau/5
                        e=(px+r*math.cos(a),y+3.6,pz+r*math.sin(a))
                        f=(px+r*math.cos(b),y+3.6,pz+r*math.sin(b))
                        face(((px,y+.35,pz),e,f,e,f,(px,y+7,pz)),foliage,.512)
                    continue
                height,ring,cx,cz,roof=row
                px,pz=cx/10,cz/10
                if (kind!='garage' and (round(px/4),round(pz/4)) in authored_sites()) or len(ring)>250:continue
                points=[(px+a/10,pz+b/10) for a,b in ring]
                top=ground(px,pz)+height
                if kind=='garage':
                    # Open ground floor with support columns around the perimeter.
                    floor=ground(px,pz)
                    top=floor+max(4.,height)
                    for a,b in zip(points,points[1:]+points[:1]):
                        length=math.dist(a,b)
                        for j in range(max(1,math.ceil(length/9))):
                            f=j/max(1,math.ceil(length/9))
                            u,v=a[0]+f*(b[0]-a[0]),a[1]+f*(b[1]-a[1])
                            corners=[(u+i,v+k) for i,k in ((0,0),(.5,0),(.5,.5),(0,.5))]
                            for l,r in zip(corners,corners[1:]+corners[:1]):
                                lo=(l[0],ground(*l)-.25,l[1]);ro=(r[0],ground(*r)-.25,r[1])
                                lt=(l[0],top,l[1]);rt=(r[0],top,r[1])
                                face((lo,ro,rt,lo,rt,lt),(.48,.49,.47),0.)
                    for tri in roof_faces(points):
                        face([(u,top,v) for u,v in tri],(.49,.49,.48),0.)
                    # Require all four corners of a stall to lie inside the outline.
                    def inside(u,v):
                        return sum((a[1]>v)!=(b[1]>v) and u<a[0]+(b[0]-a[0])*(v-a[1])/(b[1]-a[1])
                                   for a,b in zip(points,points[1:]+points[:1]))%2
                    for j,(du,dv) in enumerate(((-4,0),(0,0),(4,0),(0,7))):
                        u,v=px+du,pz+dv
                        if all(inside(u+i,v+k) for i in (-1.3,1.3) for k in (-2.8,2.8)):
                            self.parking[cx,cz,j]=(u,v)
                    continue
                palette=((.63,.59,.53),(.49,.51,.53),(.51,.41,.34),(.60,.62,.60))
                tone=palette[(cx+cz)%4]
                for a,b in zip(points,points[1:]+points[:1]):
                    av=(a[0],ground(*a)-1,a[1]);bv=(b[0],ground(*b)-1,b[1])
                    at=(a[0],top,a[1]);bt=(b[0],top,b[1])
                    material=.229 if height>28 else .228
                    if abs(a[1]-b[1])>abs(a[0]-b[0]):material-=.002
                    face((av,bv,bt,av,bt,at),tone,material)
                # Attach the bay to the footprint that actually contains the POI.
                for shop,curb in services:
                    sx,sz=shop
                    if not (min(a for a,_ in points)<=sx<=max(a for a,_ in points)
                            and min(b for _,b in points)<=sz<=max(b for _,b in points)):continue
                    inside=sum((a[1]>sz)!=(b[1]>sz) and sx<a[0]+(b[0]-a[0])*(sz-a[1])/(b[1]-a[1])
                               for a,b in zip(points,points[1:]+points[:1]))%2
                    if inside:service_bay(points,curb,ground,face)
                if roof:
                    for tri in roof_faces(points):face([(u,top,v) for u,v in tri],(.42,.43,.42),0.)
        return mesh

    def nearby(self,x,z):
        distance,name=min(((math.hypot(x-u,z-v),label) for u,v,label in self.places),default=(math.inf,''))
        return name if distance<32 else ''


def service_signs(x,z,ground,face):
    from pnw.market_visit import lettering
    from pnw.seattle_places import repair_shops,service_frontage
    services=[]
    for name,point in repair_shops():
        if math.dist((x,z),point)>630:continue
        (u,v),(nx,nz)=service_frontage(point)
        services.append((point,(u,v)))
        y=ground(u,v)
        # Place the sign behind the curb; leave the service stop clear.
        def panel(vertices,color):
            pts=[(u+nx*(3+d)+nz*t,y+h,v+nz*(3+d)-nx*t) for t,h,d in vertices]
            face((pts[0],pts[1],pts[2],pts[0],pts[2],pts[3]),color,0.)
        def rect(l,b,r,t,d,color):panel(((l,b,d),(r,b,d),(r,t,d),(l,t,d)),color)
        rect(-.12,-.35,.12,3.9,0,(.38,.40,.42))
        rect(-2.4,2.0,2.4,4.1,-.02,(.05,.16,.25))
        rect(-2.4,2.0,2.4,2.18,-.04,(.89,.48,.08))
        lettering('AUTO SERVICE',-2.3,3.05,-.05,.65,panel,(.96,.96,.86),board_width=4.6)
        lettering(name.upper()[:32],-2.2,2.38,-.05,.39,panel,(.95,.83,.46),board_width=4.4)
    return services


def service_bay(points,curb,ground,face):
    walls=[(a,b) for a,b in zip(points,points[1:]+points[:1]) if math.dist(a,b)>4.5]
    if not walls:return
    def midpoint(wall):
        a,b=wall
        return (a[0]+b[0])/2,(a[1]+b[1])/2
    a,b=min(walls,key=lambda wall:math.dist(midpoint(wall),curb))
    u,v=midpoint((a,b))
    length=math.dist(a,b)
    dx,dz=(b[0]-a[0])/length,(b[1]-a[1])/length
    side=math.copysign(1.,(curb[0]-u)*dz-(curb[1]-v)*dx)
    width=min(3.4,length/2-.25)
    def panel(left,bottom,right,top,offset,color):
        pts=[]
        for t,h in ((left,bottom),(right,bottom),(right,top),(left,top)):
            x,z=u+t*dx+side*dz*offset,v+t*dz-side*dx*offset
            pts.append((x,ground(x,z)+h,z))
        face((pts[0],pts[1],pts[2],pts[0],pts[2],pts[3]),color,0.)
    panel(-width-.12,.03,width+.12,3.9,.12,(.13,.19,.22))
    panel(-width,.06,width,3.65,.16,(.58,.62,.62))
    for i in range(1,12):panel(-width,i*.30,width,i*.30+.035,.18,(.33,.37,.38))
    for i in (-.62,0,.62):panel((i-.22)*width,2.63,(i+.22)*width,3.06,.20,(.18,.29,.36))
