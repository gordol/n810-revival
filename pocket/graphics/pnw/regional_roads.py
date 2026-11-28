"""Tile-local access to the optional region's drivable OSM network."""
from functools import lru_cache
import math
import sqlite3
import struct
import zlib

SEGMENT=struct.Struct('<iiiiB')
WIDTHS={'motorway':8.,'trunk':6.,'primary':6.,'secondary':5.,'tertiary':4.5,
        'residential':3.5,'unclassified':3.5,'service':2.4,'living_street':2.8,
        'track':2.,'road':3.}


@lru_cache(maxsize=1)
def available(path):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='road_tiles'").fetchone())


@lru_cache(maxsize=48)
def tile(path,tx,tz):
    if not available(path):return ()
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT data FROM road_tiles WHERE tx=? AND tz=?',(tx,tz)).fetchone()
    if not row:return ()
    result=[]
    for ax,az,bx,bz,width in SEGMENT.iter_unpack(zlib.decompress(row[0])):
        dx,dz=(bx-ax)/10.,(bz-az)/10.
        result.append((ax/10.,az/10.,dx,dz,dx*dx+dz*dz,width/10.))
    return tuple(result)


def nearby(x,z,radius):
    from pnw.regional_scenery import database_path
    path=database_path().resolve()
    for tx in range(math.floor((x-radius-32)/512),math.floor((x+radius+32)/512)+1):
        for tz in range(math.floor((z-radius-32)/512),math.floor((z+radius+32)/512)+1):
            for seg in tile(path,tx,tz):
                ax,az,dx,dz,_,w=seg
                if (min(ax,ax+dx)-w<=x+radius and max(ax,ax+dx)+w>=x-radius
                        and min(az,az+dz)-w<=z+radius and max(az,az+dz)+w>=z-radius):
                    yield seg
