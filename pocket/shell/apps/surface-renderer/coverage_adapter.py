"""Read existing geometry coverage; no projection/raster/light/compositor work."""
import math
from surface_renderer import Sample, SurfaceCell, SurfaceFrame, rgb


def frame(model, coverage, cells, width, height, *, coordinates=None):
    """coordinates(owner,point,normal) optionally maps world -> material space.

    Ownership is admitted only when all three visible triangle vertices agree.
    Sampling follows geometry.cell_samples, including capped raster footprints.
    """
    mesh, normals, materials, samples, depths, _, pw, ph, *_ = coverage
    if (pw, ph) != (width, height * 2):
        raise ValueError('surface adapter requires native half-cell coverage; retain base cells for capped/resampled coverage')
    vertices=mesh.vertices
    focal=model.camera.focal
    sample_span=max(model.camera.span_x/width,model.camera.span_y/(height*2))
    owners = [None] * len(mesh.vertices)
    for tri in mesh.triangles:
        for index in tri[:3]:
            previous = owners[index]
            owners[index] = tri.owner if previous is None or previous == tri.owner else False
    def point(index, color):
        hit = samples[index]
        if hit is None:
            return None
        a, b, c, wa, wb, wc = hit
        owner = owners[a]
        if not owner or owners[b] != owner or owners[c] != owner or materials[a] != materials[b] or materials[a] != materials[c]:
            return None
        va,vb,vc=vertices[a],vertices[b],vertices[c]
        position=(va[0]*wa+vb[0]*wb+vc[0]*wc,
                  va[1]*wa+vb[1]*wb+vc[1]*wc,
                  va[2]*wa+vb[2]*wb+vc[2]*wc)
        na,nb,nc=normals[a],normals[b],normals[c]
        normal=(na[0]*wa+nb[0]*wb+nc[0]*wc,
                na[1]*wa+nb[1]*wb+nc[1]*wc,
                na[2]*wa+nb[2]*wb+nc[2]*wc)
        if coordinates is not None:
            position, normal = coordinates(owner, position, normal)
        depth = float(depths[index])
        scale = depth / focal if focal else 1.0
        footprint = sample_span * scale
        return Sample(owner, materials[a], position, normal, depth, rgb(color), footprint)
    def records():
        for y in range(height):
            row=y*2*pw
            for x in range(width):
                char, style = cells[x, y]
                if char not in ('▀', '▄'):
                    continue
                fore, back = style >> 24 & 0xffffff, style & 0xffffff
                upper, lower = (fore, back) if char == '▀' else (back, fore)
                yield SurfaceCell(x, y, point(row+x, upper), point(row+pw+x, lower), (char, style))
    return SurfaceFrame(width, height, records())
