"""Seeded illustrative vegetation rooted in terrain; no per-frame simulation."""
import math
from functools import lru_cache
from geometry import Vec,Mesh,Triangle,merge,cone


@lru_cache(maxsize=8192)
def lattice(a,b):
    h=(a*374761393+b*668265263+1013904223)&0xffffffff
    h=((h^(h>>13))*1274126177)&0xffffffff
    return ((h^(h>>16))&65535)/65535


def noise(x,z,scale=1):
    # Continuous world-space variation, independent of terminal dimensions.
    x,z=x/scale,z/scale
    ix,iz=math.floor(x),math.floor(z);u=x-ix;v=z-iz
    u=u*u*(3-2*u);v=v*v*(3-2*v)
    return (lattice(ix,iz)*(1-u)+lattice(ix+1,iz)*u)*(1-v)+(lattice(ix,iz+1)*(1-u)+lattice(ix+1,iz+1)*u)*v


def ground_color(point,normal):
    from lighting import mix,smooth
    broad=noise(point.x,point.z,1800);fine=noise(point.x,point.z,190)
    forest=(1-smooth(1500,2150,point.y))*smooth(.50,.90,normal.y)
    meadow=mix((87,99,66),(118,112,90),broad)
    canopy=noise(point.x,point.z,90)
    woodland=mix((23,47,34),(43,76,48),broad)
    woodland=tuple(c*(.78+.42*canopy) for c in woodland)
    base=mix(meadow,woodland,forest)
    rock=1-smooth(.65,.91,normal.y)
    base=mix(base,(105,106,103),rock*.8)
    snowline=2850+(broad-.5)*280
    snow=smooth(snowline-160,snowline+240,point.y)*smooth(.40,.88,normal.y)
    base=mix(base,(205,214,213),snow)
    texture=.85+.20*fine+.07*noise(point.x,point.z,35)
    return tuple(c*texture for c in base)


@lru_cache(maxsize=1)
def forest(field):
    """Bounded conifers: grouped crowns and species variation, not tree sprites."""
    meshes=[]
    # Fixed world placement; resolution changes do not plant a different forest.
    peak=field.values.index(max(field.values))
    eye_x=field.origin.x+(peak%field.nx)*field.dx
    eye_z=(peak//field.nx)*field.dz-24000
    for i in range(448):
        # Low-discrepancy candidates avoid a visible planting grid.
        u=(.5+i*.61803398875)%1;v=(.5+i*.75487766625)%1
        x=field.origin.x+u*(field.nx-1)*field.dx
        z=field.origin.z+v*(field.nz-1)*field.dz
        if i>=320:
            x=eye_x+(u-.5)*6000
            z=max(0,eye_z)+400+v*5000
        y=field.height(x,z)
        if y>1850 or noise(x,z,2200)<.30:continue
        h=28+noise(x,z,85)*36
        material='fir' if i%3 else 'cedar'
        # Three overlapping crowns give the silhouette broken taper, cheaply.
        for level,(offset,size) in enumerate(((.18,.82),(.43,.62),(.65,.35))):
            meshes.append(cone(Vec(x,y+h*offset,z),h*(.38 if material=='fir' else .48)*size,h*size,material,f'tree:{i}'))
    return merge(meshes)
