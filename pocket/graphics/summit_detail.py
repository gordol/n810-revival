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
    panorama: bool=False


def attach(field,meta,*,approach=False):
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
    if approach:
        import subprocess
        import summit_approach as patch
        try:data=patch.samples()
        except (OSError,ValueError,ImportError,KeyError,subprocess.SubprocessError) as error:
            print(f'Using standard summit detail: {error}',file=sys.stderr)
        else:
            inset=attach_approach(inset,data)
    return RegionalTerrain(field.nx,field.nz,field.origin,field.dx,field.dz,field.values,field.units,inset)

def attach_approach(parent,data):
    import summit_approach as patch
    dx,dz=parent.dx/patch.DIVISIONS,parent.dz/patch.DIVISIONS
    x0=parent.origin.x+patch.WEST*parent.dx
    z0=parent.origin.z+patch.SOUTH*parent.dz
    for j in range(patch.HEIGHT):
        for i in range(patch.WIDTH):
            k=j*patch.WIDTH+i
            distance=min(i,j,patch.WIDTH-1-i,patch.HEIGHT-1-j)
            u=min(1.,distance/patch.DIVISIONS)
            if u<1:
                coarse=parent.height(x0+i*dx,z0+j*dz)
                data[k]=coarse+(data[k]-coarse)*u*u*(3-2*u)
            # Illustrative shallow wind ridges taper to zero at the join.
            x,z=i*dx,j*dz
            data[k]+=u*.16*math.sin(.29*x+.09*z+1.4*math.sin(z*.047))
    fine=HeightField(patch.WIDTH,patch.HEIGHT,Vec(x0,0,z0),dx,dz,tuple(data),'meters')
    return RegionalTerrain(parent.nx,parent.nz,parent.origin,parent.dx,parent.dz,parent.values,parent.units,fine)
