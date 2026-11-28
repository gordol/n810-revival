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

class Neighborhood:
    def __init__(self):
        configured=os.environ.get('POCKET_REGION_SCENERY')
        full=Path(configured) if configured else Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')/'pocket/rainier-walk/puget-sound-scenery.sqlite'
        self.db=sqlite3.connect(f'{(full if full.is_file() else ASSETS/"neighborhoods.sqlite").as_uri()}?mode=ro',uri=True)
        self.cell=None
        self.places=[]

    def close(self):self.db.close()

    def update(self,x,z,ground):
        cell=(math.floor(x/512),math.floor(z/512))
        if self.cell==cell:return None
        self.cell=cell
        mesh=array('f');self.places=[]
        def face(vertices,color,material):
            for px,py,pz in vertices:mesh.extend((px,py,pz,*color,material))
        for tx,tz in sorted(((cell[0]+dx,cell[1]+dz) for dx in (-1,0,1) for dz in (-1,0,1)),
                            key=lambda ij:math.hypot(x-(ij[0]+.5)*512,z-(ij[1]+.5)*512)):
            for kind,blob in self.db.execute('SELECT model,data FROM features WHERE tx=? AND tz=?',(tx,tz)):
                row=json.loads(zlib.decompress(blob))
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
                if (round(px/4),round(pz/4)) in authored_sites() or len(ring)>250:continue
                points=[(px+a/10,pz+b/10) for a,b in ring]
                top=ground(px,pz)+height
                palette=((.63,.59,.53),(.49,.51,.53),(.51,.41,.34),(.60,.62,.60))
                tone=palette[(cx+cz)%4]
                for a,b in zip(points,points[1:]+points[:1]):
                    av=(a[0],ground(*a)-1,a[1]);bv=(b[0],ground(*b)-1,b[1])
                    at=(a[0],top,a[1]);bt=(b[0],top,b[1])
                    material=.229 if height>28 else .228
                    if abs(a[1]-b[1])>abs(a[0]-b[0]):material-=.002
                    face((av,bv,bt,av,bt,at),tone,material)
                if roof:
                    for tri in roof_faces(points):face([(u,top,v) for u,v in tri],(.42,.43,.42),0.)
        return mesh

    def nearby(self,x,z):
        distance,name=min(((math.hypot(x-u,z-v),label) for u,v,label in self.places),default=(math.inf,''))
        return name if distance<32 else ''
