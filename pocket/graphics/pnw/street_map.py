"""Offline street routing and location labels for the Puget Sound HUD."""
from functools import lru_cache
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
