"""Mount Fremont lookout on the prepared Rainier grid. Dimensions are approximate."""
from geometry import Vec

# NPS Mount Rainier lahar detection EA, Fremont installation site.
LATITUDE,LONGITUDE=46.9340,-121.6756
DECK=3.0


def location(field,latitude=LATITUDE,longitude=LONGITUDE):
    from terrain_elevation import grid
    meta,_=grid()
    col=(longitude-meta['longitude_first'])/meta['longitude_step']
    row=(latitude-meta['latitude_first'])/meta['latitude_step']
    if not (0<=col<field.nx-1 and 0<=row<field.nz-1):return None
    return field.origin.x+col*field.dx,field.origin.z+row*field.dz


def base_level(height,x,z):
    return max(height(x+i,z+j) for i in (-3,3) for j in (-3,3))


def build(height,face,x,z):
    base=base_level(height,x,z)
    wood=(161,142,108); trim=(218,211,183); glass=(87,126,141)
    def quad(a,b,c,d,color):
        pts=[Vec(x+i,base+j,z+k) for i,j,k in (a,b,c,d)]
        face(*pts[:3],color);face(pts[0],pts[2],pts[3],color)
    def box(left,right,bottom,top,near,far,color):
        for a,b,c,d in ((left,near,right,near),(right,near,right,far),
                        (right,far,left,far),(left,far,left,near)):
            quad((a,bottom,b),(a,top,b),(c,top,d),(c,bottom,d),color)
        quad((left,top,near),(left,top,far),(right,top,far),(right,top,near),color)

    low=min(height(x+i,z+j) for i in (-3,3) for j in (-3,3))-base-.2
    box(-2.13,2.13,low,DECK,-2.13,2.13,wood)
    box(-3.2,3.2,DECK-.20,DECK,-3.2,3.2,wood)
    box(-2.13,2.13,DECK,4.,-2.13,2.13,wood)
    box(-2.12,2.12,4.,5.35,-2.12,2.12,glass)
    for course in range(5):
        y=DECK+.17*course
        box(-2.15,2.15,y,y+.035,-2.15,2.15,(139,120,92))
    box(.5,1.4,DECK,DECK+2.05,-2.18,-2.13,trim)
    box(.57,1.33,DECK,DECK+1.96,-2.20,-2.18,(109,91,67))
    box(.65,1.25,DECK+1.,DECK+1.84,-2.22,-2.20,glass)
    box(-.48,.48,low,low+2.1,-2.17,-2.13,(108,91,71))
    for side in (-1,1):
        for t in (-2.13,-1.06,0,1.06,2.13):
            box(t-.05,t+.05,4.,5.36,side*2.12-.05,side*2.12+.05,trim)
            box(side*2.12-.05,side*2.12+.05,4.,5.36,t-.05,t+.05,trim)
        edge=side*3.15
        for t in (-3.15,0.,3.15):
            if side>0 or t:box(t-.05,t+.05,DECK,4.,edge-.05,edge+.05,wood)
            box(edge-.05,edge+.05,DECK,4.,t-.05,t+.05,wood)
        spans=((-3.2,-.7),(.7,3.2)) if side<0 else ((-3.2,3.2),)
        for left,right in spans:box(left,right,3.94,4.04,edge-.06,edge+.06,wood)
        box(edge-.06,edge+.06,3.94,4.04,-3.2,3.2,wood)
    corners=[(-2.6,-2.6),(-2.6,2.6),(2.6,2.6),(2.6,-2.6)]
    for (i,j),(a,b) in zip(corners,corners[1:]+corners[:1]):
        face(Vec(x+i,base+5.36,z+j),Vec(x+a,base+5.36,z+b),Vec(x,base+6.9,z),(93,101,88))
    for step in range(14):
        near=-7.4+.3*step
        top=DECK-(13-step)*((DECK+base-height(x,z-7.4))/14)
        box(-.7,.7,top-.16,top,near,near+.32,wood)
        if step in (0,4,8,13):
            for side in (-.68,.68):box(side-.05,side+.05,top,top+.83,near,near+.09,wood)
    for side in (-.68,.68):
        start=height(x,z-7.4)-base+.85
        quad((side,start,-7.4),(side,start+.10,-7.4),
             (side,DECK+.95,-3.2),(side,DECK+.85,-3.2),wood)
