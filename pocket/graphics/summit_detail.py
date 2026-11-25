"""Registered USGS summit inset for the standard regional Rainier export."""
from array import array
from dataclasses import dataclass
import math
from pathlib import Path
import sys
import zlib

from geometry import HeightField,Vec

WEST,SOUTH=107,133
CELLS,DIVISIONS=42,6
SIZE=CELLS*DIVISIONS+1


@dataclass(frozen=True)
class RegionalTerrain(HeightField):
    inset: HeightField=None


def attach(field,meta):
    # Other prepared grids may cover different terrain.
    registration=(-122.1+.68/514,46.53+.53/514,.68/257,.53/257)
    keys=('longitude_first','latitude_first','longitude_step','latitude_step')
    if (field.nx,field.nz)!=(257,257) or not all(
            math.isclose(meta[key],value,abs_tol=1e-9,rel_tol=0) for key,value in zip(keys,registration)):
        return field
    raw=array('h')
    raw.frombytes(zlib.decompress((Path(__file__).parent/'assets/summit/elevation.i16.zlib').read_bytes()))
    if sys.byteorder!='little':raw.byteswap()
    values=list(raw)
    x0=field.origin.x+WEST*field.dx
    z0=field.origin.z+SOUTH*field.dz
    dx,dz=field.dx/DIVISIONS,field.dz/DIVISIONS
    # Meet the coarse edge exactly, fading the correction over one coarse cell.
    for j in range(SIZE):
        for i in range(SIZE):
            distance=min(i,j,SIZE-1-i,SIZE-1-j)
            if distance>=DIVISIONS:continue
            k=j*SIZE+i
            coarse=field.height(x0+i*dx,z0+j*dz)
            values[k]=coarse+(values[k]-coarse)*distance/DIVISIONS
    inset=HeightField(SIZE,SIZE,Vec(x0,0,z0),dx,dz,tuple(values),'meters')
    return RegionalTerrain(field.nx,field.nz,field.origin,field.dx,field.dz,field.values,field.units,inset)
