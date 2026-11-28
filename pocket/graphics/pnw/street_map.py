"""Offline street routing and location labels for the Puget Sound HUD."""
from functools import lru_cache
import heapq
import json
import math
from pathlib import Path

from pnw.terrain import GRIDS, layout, location

ASSETS=Path(__file__).resolve().parents[1]/'assets/seattle'


def coordinates(x,z):
    _,_,zoom,step,_,_=GRIDS['sound']
    cx,cy,spacing=layout('sound')
    scale=256*(1<<zoom)
    lon=(cx+x*step/spacing)/scale*360-180
    lat=math.degrees(math.atan(math.sinh(math.pi*(1-2*(cy-z*step/spacing)/scale))))
    return lat,lon


@lru_cache(maxsize=1)
def localities():
    return [(name,kind,location('sound',lat/1e7,lon/1e7)) for name,kind,lon,lat in
            json.loads((ASSETS/'localities.json').read_text())]


@lru_cache(maxsize=256)
def neighborhood(tile_x,tile_z):
    here=((tile_x+.5)*32,(tile_z+.5)*32)
    distance,name=min(((math.dist(here,pt),name) for name,kind,pt in localities()
                       if kind in ('suburb','neighbourhood','quarter')),default=(math.inf,''))
    if distance<1350:return name
    distance,name=min(((math.dist(here,pt),name) for name,kind,pt in localities()
                       if kind in ('city','town','village')),default=(math.inf,''))
    return 'Near '+name if distance<5000 else 'Puget Sound region'


@lru_cache(maxsize=1)
def graph():
    from pnw.seattle_places import road_lines,street_lines
    edges={}
    for _,kind,points,_,_ in (*road_lines(),*street_lines('airports')):
        if kind=='pedestrian':continue
        for a,b in zip(points,points[1:]):
            if a==b:continue
            a,b=tuple(round(n,1) for n in a),tuple(round(n,1) for n in b)
            length=math.dist(a,b)
            edges.setdefault(a,{})[b]=length
            back=edges.setdefault(b,{})
            if kind not in ('motorway','motorway_link'):back[a]=length
    return edges


def road_route(origin,destination):
    from pnw.regional_roads import nearby
    local={}
    center=tuple((a+b)/2 for a,b in zip(origin,destination))
    radius=min(4500.,math.dist(origin,destination)*.65+500)
    def rounded(p):return tuple(round(n,1) for n in p)
    for x,z,dx,dz,l2,_ in nearby(*center,radius):
        a,b=(x,z),rounded((x+dx,z+dz))
        local.setdefault(a,{})[b]=math.sqrt(l2)
        local.setdefault(b,{})[a]=math.sqrt(l2)
    base=graph()
    edges=base.copy()
    for node,neighbors in local.items():
        edges[node]={**base.get(node,{}),**neighbors}
    start=min(edges,key=lambda p:math.dist(p,origin))
    goal=min(edges,key=lambda p:math.dist(p,destination))
    if math.dist(origin,start)>500:return ()
    best=start
    queue=[(0.,start)]
    costs={start:0.}
    prev={}
    while queue:
        cost,node=heapq.heappop(queue)
        if cost!=costs[node]:continue
        if math.dist(node,destination)<math.dist(best,destination):best=node
        if node==goal:break
        for point,length in edges[node].items():
            total=cost+length
            if total>=costs.get(point,math.inf):continue
            costs[point]=total
            prev[point]=node
            heapq.heappush(queue,(total,point))
    route=[best]
    while route[-1] in prev:route.append(prev[route[-1]])
    return tuple(reversed(route)) if math.dist(best,destination)<80 else ()
