"""Registered Seattle landmarks in the Sound heightfield's coordinate system."""
import csv
from functools import lru_cache
import math
from pathlib import Path

DECK_HEIGHT=520*.3048
TIP_HEIGHT=605*.3048

@lru_cache(maxsize=1)
def places():
    from pnw_outings import location
    with (Path(__file__).parent/'assets/seattle/places.csv').open() as source:
        return {row['name']:location('sound',float(row['latitude']),float(row['longitude']))
                for row in csv.DictReader(source)}

@lru_cache(maxsize=1)
def arcade_origin():
    from pike_market import offset
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

@lru_cache(maxsize=1)
def delivery_route():
    from pnw_outings import location
    points=[]
    with (Path(__file__).parent/'assets/seattle/delivery.csv').open() as source:
        for row in csv.DictReader(source):
            pos=location('sound',float(row['latitude']),float(row['longitude']))
            if not points or points[-1]!=pos:points.append(pos)
    return tuple(points)
    loft([ring(x,z,DECK_HEIGHT-.3,21.3,64),ring(x,z,DECK_HEIGHT,21.3,64),
          ring(x,z,DECK_HEIGHT,17.9,64)],[steel,ivory])
    loft([ring(x,z,DECK_HEIGHT+1.00,21.3,64),ring(x,z,DECK_HEIGHT+1.04,21.3,64)],[steel])
    for i in range(64):
        a=i*math.tau/64
        px,pz=x+21.3*math.cos(a),z+21.3*math.sin(a)
        loft([ring(px,pz,DECK_HEIGHT,.045,4),ring(px,pz,DECK_HEIGHT+1,.045,4)],[steel])


def buildings(height,quad):
    from pnw_outings import location
    import json
    source=Path(__file__).parent/'assets/seattle/buildings.json'
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
        tone=((.47,.54,.56),(.62,.56,.48),(.53,.43,.36),(.63,.64,.61))[int(way)%4]
        for (x,z),(ex,ez) in zip(points,points[1:]+points[:1]):
            norm=math.hypot(ex-x,ez-z)
            if norm==0:continue
            light=.82+.13*(ex-x)/norm+.09*(ez-z)/norm
            quad(((x,height(x,z)-1,z),(ex,height(ex,ez)-1,ez),(ex,top,ez),(x,top,z)),
                 tuple(light*c for c in tone),.228)
        for a,b,c in zip(roof[::3],roof[1::3],roof[2::3]):
            quad([(points[k][0],top,points[k][1]) for k in (a,b,c,c)],(.47,.48,.46))

class MarketDirectory:
    def __init__(self,view):
        self.view=view
        self.names=[name for name in places() if name not in ('Space Needle','Ballard Clay')]

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
    tx,tz=places()[name]
    degrees=math.degrees(math.atan2(tx-x,tz-z))%360.
    compass=('N','NE','E','SE','S','SW','W','NW')[int((degrees+22.5)//45)%8]
    return f'{name}  {round(math.hypot(tx-x,tz-z))} m {compass}'
