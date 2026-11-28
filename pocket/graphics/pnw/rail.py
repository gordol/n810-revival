"""Passenger rides along published Sound Transit and Amtrak route shapes."""
from bisect import bisect_right
from functools import lru_cache
import json
import math
from pathlib import Path
from pnw.terrain import location

RIDES={'Sounder S · King Street to Tacoma Dome':'sounder',
       'Link 1 · Westlake to Federal Way':'link',
       'Tacoma Link · Tacoma Dome to St Joseph':'tline',
       'Cascades · Olympia–Lacey to Everett':'cascades'}

@lru_cache(maxsize=1)
def routes():
    data=json.loads((Path(__file__).resolve().parents[1]/'assets/seattle/rail.json').read_text())
    routes={}
    for key,row in data.items():
        points=[location('sound',lat/1e6,lon/1e6) for lat,lon in row['points']]
        distances=[0.]
        for a,b in zip(points,points[1:]):distances.append(distances[-1]+math.dist(a,b))
        speed={'link':17.,'tline':9.,'sounder':30.,'cascades':36.}[key]
        stations=[(distances[i]/speed+j*8,distances[i],name,i) for j,(i,name) in enumerate(row['stops'])]
        routes[key]=(points,distances,stations,speed)
    return routes

def sample(key,elapsed):
    points,distances,stations,speed=routes()[key]
    station=max(0,bisect_right([s[0] for s in stations],elapsed)-1)
    arrival,at,name,_=stations[station]
    progress=max(0.,elapsed-arrival-8)
    next_stop=stations[min(station+1,len(stations)-1)]
    at=min(next_stop[1],at+progress*speed)
    i=min(len(points)-2,bisect_right(distances,at)-1)
    x,z=points[i];xx,zz=points[i+1]
    f=(at-distances[i])/max(.001,distances[i+1]-distances[i])
    pose=(x+(xx-x)*f,z+(zz-z)*f,math.atan2(xx-x,zz-z),.035,2.5)
    return pose,(name if not progress or station==len(stations)-1 else 'Next · '+next_stop[2]),next_stop[0]

def mesh(height,quad,box):
    for points,_,stations,_ in routes().values():
        for a,b in zip(points,points[1:]):
            length=math.dist(a,b)
            if length<.01:continue
            dx,dz=(b[0]-a[0])/length,(b[1]-a[1])/length
            def track(u,v,t,end,h,color):
                vertices=[]
                for side,d in ((u,t),(v,t),(v,end),(u,end)):
                    x=a[0]+d*dx+side*dz;z=a[1]+d*dz-side*dx
                    vertices.append((x,height(x,z)+h,z))
                quad(vertices,color)
            for start in range(0,math.ceil(length),45):
                end=min(start+45,length)
                track(-1.8,1.8,start,end,.08,(.31,.29,.27))
                for rail in (-.72,.72):track(rail-.045,rail+.045,start,end,.14,(.64,.65,.63))
        for _,_,_,i in stations:
            x,z=points[i];a,b=points[max(0,i-1)],points[min(i+1,len(points)-1)]
            heading=math.atan2(b[0]-a[0],b[1]-a[1])
            c,s=math.cos(heading),-math.sin(heading)
            px,pz=x+4.1*c,z+4.1*s;y=height(px,pz)
            box(px,pz,y,4.,32.,.8,(.65,.64,.58),rotation=(c,s))
            for offset in (-6,6):box(px-offset*s,pz+offset*c,y+.8,.25,.25,2.9,(.23,.31,.31))
            box(px,pz,y+3.7,4.2,16.,.25,(.29,.39,.41),rotation=(c,s))
