"""Illustrative river stage along the connected Ohanapecosh NHD flowlines."""
from dataclasses import replace
from math import ceil, floor, hypot
from typing import NamedTuple

from geometry import Vec


TROUT_POOL=(15.,8.)


class Section(NamedTuple):
    x:float
    z:float
    nx:float
    nz:float
    stage:float
    station:float


def _ordered_centres(segments):
    # NHD digitizes downstream, but feature records can arrive in any order.
    links={}
    ends=set()
    for x,z,u,v,length in segments:
        start=(round(x,5),round(z,5))
        end=(round(x+length*u,5),round(z+length*v,5))
        links[start]=end
        ends.add(end)
    heads=links.keys()-ends
    if len(heads)!=1:raise ValueError('Expected one connected river reach')
    centres=[heads.pop()]
    while centres[-1] in links:centres.append(links.pop(centres[-1]))
    if links:raise ValueError('Disconnected river reach')
    return centres


def _downstream_stage(samples):
    # Isotonic fit of DEM elevations to the downstream profile. Pool uphill
    # stretches rather than letting a single low DEM cell drain a whole reach.
    pools=[]
    for y,station in samples:
        pools.append((y+.001*station,1))
        while len(pools)>1 and pools[-2][0]/pools[-2][1]<pools[-1][0]/pools[-1][1]:
            total,count=pools.pop()
            prev,n=pools.pop()
            pools.append((prev+total,n+count))
    fitted=(total/count for total,count in pools for _ in range(count))
    return [y-.001*station for y,(_,station) in zip(fitted,samples)]


class RiverChannel:
    def __init__(self,field,segments):
        centres=_ordered_centres(segments)
        normals=[];stations=[0.]
        for (x,z),(ex,ez) in zip(centres,centres[1:]):
            length=hypot(ex-x,ez-z)
            normals.append(((ez-z)/length,(x-ex)/length))
            stations.append(stations[-1]+length)
        offsets=[]
        for i in range(len(centres)):
            a,b=normals[max(0,i-1)],normals[min(i,len(normals)-1)]
            scale=1+a[0]*b[0]+a[1]*b[1]
            nx,nz=(a[0]+b[0])/scale,(a[1]+b[1])/scale
            offsets.append((nx,nz))
        # At very tight bends, stop the outside edge of either section before
        # it could cross the neighbouring section (including the gravel lip).
        widths=[1.]*len(offsets)
        for i,(a,b) in enumerate(zip(offsets,offsets[1:])):
            dx=centres[i+1][0]-centres[i][0]
            dz=centres[i+1][1]-centres[i][1]
            cross=12*abs(a[0]*b[1]-a[1]*b[0])
            if cross:
                widths[i]=min(widths[i],.9*abs(dx*b[1]-dz*b[0])/cross)
                widths[i+1]=min(widths[i+1],.9*abs(dx*a[1]-dz*a[0])/cross)
        offsets=[(nx*w,nz*w) for (nx,nz),w in zip(offsets,widths)]
        rows=[]
        for i,((x,z),(ex,ez)) in enumerate(zip(centres,centres[1:])):
            length=stations[i+1]-stations[i]
            count=ceil(length/3)
            for j in range(count):
                t=j/count
                nx,nz=offsets[i];mx,mz=offsets[i+1]
                rows.append(Section(x+(ex-x)*t,z+(ez-z)*t,nx+(mx-nx)*t,nz+(mz-nz)*t,0.,stations[i]+length*t))
        rows.append(Section(*centres[-1],*offsets[-1],0.,stations[-1]))
        stages=_downstream_stage([(field.height(r.x,r.z),r.station) for r in rows])
        self.rows=[r._replace(stage=y) for r,y in zip(rows,stages)]
        # Index short strips for local surface queries such as fish and rings.
        self.cells={}
        for a,b in zip(self.rows,self.rows[1:]):
            for ix in range(floor((min(a.x,b.x)-12)/16),floor((max(a.x,b.x)+12)/16)+1):
                for iz in range(floor((min(a.z,b.z)-12)/16),floor((max(a.z,b.z)+12)/16)+1):
                    self.cells.setdefault((ix,iz),[]).append((a,b))

    def water_height(self,x,z):
        for a,b in self.cells.get((floor(x/16),floor(z/16)),()):
            left=(a.x-6*a.nx,a.z-6*a.nz)
            right=(a.x+6*a.nx,a.z+6*a.nz)
            end_left=(b.x-6*b.nx,b.z-6*b.nz)
            end_right=(b.x+6*b.nx,b.z+6*b.nz)
            for p,q,r,yp,yq,yr in ((left,right,end_left,a.stage,a.stage,b.stage),
                                     (end_right,end_left,right,b.stage,b.stage,a.stage)):
                ux,uz=q[0]-p[0],q[1]-p[1]
                vx,vz=r[0]-p[0],r[1]-p[1]
                dx,dz=x-p[0],z-p[1]
                det=ux*vz-uz*vx
                if abs(det)<1e-9:continue
                u,v=(dx*vz-dz*vx)/det,(ux*dz-uz*dx)/det
                if min(u,v)>=-1e-8 and u+v<=1.00000001:return yp+u*(yq-yp)+v*(yr-yp)
        return None

    def bed_field(self,field):
        # Shape the coarse DEM triangles beneath the water and blend back to
        # the measured slopes outside the channel. Keep the source grid intact.
        values=list(field.values)
        inner=8+hypot(field.dx,field.dz)
        outer=inner+field.dx
        nearest={}
        ceiling={}
        for r in self.rows:
            ix=(r.x-field.origin.x)/field.dx;iz=(r.z-field.origin.z)/field.dz
            for j in range(max(0,ceil(iz-outer/field.dz)),min(field.nz,floor(iz+outer/field.dz)+1)):
                for i in range(max(0,ceil(ix-outer/field.dx)),min(field.nx,floor(ix+outer/field.dx)+1)):
                    d=hypot((i-ix)*field.dx,(j-iz)*field.dz)
                    if d>=outer:continue
                    k=j*field.nx+i
                    if k not in nearest or d<nearest[k][0]:nearest[k]=(d,r.stage)
                    # All coarse vertices supporting a wet triangle must
                    # clear the surface, even where the thalweg turns sharply.
                    if d<6*hypot(r.nx,r.nz)+hypot(field.dx,field.dz)+1.6:
                        ceiling[k]=min(ceiling.get(k,r.stage),r.stage-.06)
        for k,(d,y) in nearest.items():
            px=field.origin.x+(k%field.nx)*field.dx
            pz=field.origin.z+(k//field.nx)*field.dz
            hollow=max(0.,1.-hypot((px-TROUT_POOL[0])/13.,(pz-TROUT_POOL[1])/19.))
            depth=.12+.65*max(0.,1.-d/6.)+1.25*hollow*hollow
            blend=min(1.,(outer-d)/(outer-inner))
            values[k]=min(values[k]+blend*(y-depth-values[k]),ceiling.get(k,float('inf')))
        return replace(field,values=tuple(values))

    def triangles(self,height):
        previous=None
        for r in self.rows:
            row=[]
            for side in (-12,-7,-6,6,7,12):
                x,z=r.x+side*r.nx,r.z+side*r.nz
                y=height(x,z)+.04 if abs(side)==12 else r.stage+(.24 if abs(side)==7 else 0.)
                row.append((Vec(x,y,z),side,r.station))
            if previous:
                for j in range(len(row)-1):
                    for tri in ((previous[j],row[j],previous[j+1]),(row[j+1],previous[j+1],row[j])):
                        yield tri,j==2
            previous=row

    def mesh(self,height,face,water_vertex):
        for tri,is_water in self.triangles(height):
            if is_water:
                for p,side,station in tri:water_vertex(p,side,station)
            else:face(*(v[0] for v in tri),(122,116,95),.53)


class RiverFloor:
    """Index the drawn gravel and water triangles above the carved DEM."""
    def __init__(self,channel,height):
        self.cells={}
        for triangle,_ in channel.triangles(height):
            a,b,c=(v[0] for v in triangle)
            ux,uz=b.x-a.x,b.z-a.z
            vx,vz=c.x-a.x,c.z-a.z
            det=ux*vz-uz*vx
            if abs(det)<1e-9:continue
            plane=(a,vz/det,-vx/det,-uz/det,ux/det,b.y-a.y,c.y-a.y)
            for i in range(floor(min(a.x,b.x,c.x)/16),floor(max(a.x,b.x,c.x)/16)+1):
                for j in range(floor(min(a.z,b.z,c.z)/16),floor(max(a.z,b.z,c.z)/16)+1):
                    self.cells.setdefault((i,j),[]).append(plane)

    def height(self,x,z,terrain):
        for a,ux,uz,vx,vz,dy_b,dy_c in self.cells.get((floor(x/16),floor(z/16)),()):
            dx,dz=x-a.x,z-a.z
            u,v=dx*ux+dz*uz,dx*vx+dz*vz
            if min(u,v)>=-1e-8 and u+v<=1.00000001:
                terrain=max(terrain,a.y+u*dy_b+v*dy_c)
        return terrain
