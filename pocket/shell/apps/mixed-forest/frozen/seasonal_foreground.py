"""Seasonal phenology around the frozen organic art profile, using its coverage.

Summer is an exact delegation. Spring/autumn change low plant structure, ground
cover, and material-local glyphs. Candidate IDs and world anchors stay fixed.
Winter currently delegates to the baseline; winter art is outside this study.
"""
from dataclasses import replace
from functools import lru_cache
import hashlib
import importlib.util
import math
from pathlib import Path

BASE_SHA256 = 'cb0dc7750455e77da067f909352eed0d0ce9080e107e0617faef7fc7462e514a'
SEASONS = ('spring', 'summer', 'autumn', 'winter')
MAX_OVERLAY_CELLS = 8192
MAX_GLYPHS = 1280


@lru_cache(maxsize=1)
def baseline():
    path = Path(__file__).with_name('static_foreground.py')
    if hashlib.sha256(path.read_bytes()).hexdigest() != BASE_SHA256:
        raise ValueError('Seasonal foreground baseline differs from frozen study')
    spec = importlib.util.spec_from_file_location('_seasonal_organic_base', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(season):
    if season not in SEASONS:
        raise ValueError('Unsupported foreground season: ' + str(season))


def build(model, seed=12345, season='summer'):
    validate(season)
    f = baseline()
    organic, meta = f.build(model, seed)
    if season in ('summer', 'winter'):
        return organic, meta
    from geometry import Vec, Mesh, merge
    from landscape_detail import beam
    # The same shrub roots carry different leaf/bud layers, not relocated plants.
    shrubs = [(owner, x, z) for owner, x, z in meta['anchor_xz']
              if owner.startswith('lab-foreground:shrub:')]
    owners = {owner for owner, _, _ in shrubs}
    retained = Mesh(organic.mesh.vertices,
                    tuple(t for t in organic.mesh.triangles if t.owner not in owners))
    parts = [retained]
    for owner, x, z in shrubs:
        identity = int(owner.rsplit(':', 1)[1])
        r = f.random(seed, identity * 3 + 2)
        root = f.surface(model.terrain, x, z)
        # Three persistent woody branches remain visible through sparse leaves.
        for j in range(3):
            angle = j * math.tau / 3 + f.random(seed, identity) * math.tau
            dx, dz = math.cos(angle) * 2.0, math.sin(angle) * 2.0
            tip = Vec(x + dx, root + 1.5 + r, z + dz)
            parts.append(beam(Vec(x, root, z), tip, .12, 'wood', owner))
            if season == 'spring' or j != identity % 3:
                # Spring: separated buds at branch tips. Autumn: fewer drooping
                # leaf masses and open woody gaps instead of a full green cone.
                radius = (.95 + r * .65) if season == 'spring' else (1.2 + r * .7)
                rise = (.6 + r * .55) if season == 'spring' else (.48 + r * .45)
                parts.append(f.crown(Vec(tip.x, tip.y - rise * .3, tip.z),
                                     radius, rise, 'fern', owner, seed, identity * 7 + j))
    result = replace(organic, mesh=merge(parts))
    info = dict(meta, season=season, seasonal_shrubs=len(shrubs),
                seasonal_leaf_layers=3 if season == 'spring' else 2,
                added_triangles=len(result.mesh.triangles) - len(model.mesh.triangles),
                added_vertices=len(result.mesh.vertices) - len(model.mesh.vertices))
    return result, info


def rgb(value):
    return tuple(value >> shift & 255 for shift in (16, 8, 0))


def pack(color):
    return sum(max(0, min(255, round(v))) << shift
               for v, shift in zip(color, (16, 8, 0)))


def tint(value, target, amount):
    color = rgb(value)
    # Keep local illumination and the baseline's sculpted light/shadow contrast.
    exposure = max(.20, min(1.25, sum(color) / max(1, sum(target))))
    return pack(tuple(v * (1 - amount) + t * exposure * amount
                      for v, t in zip(color, target)))


def overlay(model, coverage, cells, width, height, seed=12345, season='summer'):
    validate(season)
    f = baseline()
    result = f.overlay(model, coverage, cells, width, height, seed)
    if season in ('summer', 'winter'):
        return result
    from vegetation import noise
    mesh, normals, materials, samples, depths, _, pw, ph, *_ = coverage
    owners = [''] * len(mesh.vertices)
    for tri in mesh.triangles:
        if tri.material in ('fern', 'fir', 'cedar', 'tree'):
            for index in tri[:3]:
                owners[index] = tri.owner
    # Feather only the seasonal contribution at the existing sparse ground-mask
    # boundary. This does not blur the terrain, silhouettes, or glyph ink.
    ground_mask = set()
    for x, y in result:
        xx = min(pw - 1, int((x + .5) * pw / width))
        pair = [samples[min(ph - 1, int((y + fy) * ph / height)) * pw + xx]
                for fy in (.25, .75)]
        if all(s is not None and materials[s[0]] == 'terrain' for s in pair):
            ground_mask.add((x, y))
    shrub_cells = []
    for y in range(height):
        for x in range(width):
            xx = min(pw - 1, int((x + .5) * pw / width))
            indexes = [min(ph - 1, int((y + fy) * ph / height)) * pw + xx
                       for fy in (.25, .75)]
            pair = [samples[index] for index in indexes]
            if any(sample is None for sample in pair):
                continue
            kinds = [materials[s[0]] for s in pair]
            a, b, c, wa, wb, wc = pair[1]
            px, py, pz = (mesh.vertices[a][j] * wa + mesh.vertices[b][j] * wb
                          + mesh.vertices[c][j] * wc for j in range(3))
            identity = math.floor(px / 18) * 73856093 ^ math.floor(pz / 18) * 19349663
            shrub = all(kind == 'fern' for kind in kinds)
            ground = all(kind == 'terrain' for kind in kinds)
            evergreen = all(kind in ('fir', 'cedar', 'tree') for kind in kinds)
            if not (ground or evergreen or shrub):
                continue
            point = x, y
            if point not in result and not shrub:
                continue
            ch, ink = result.get(point, cells[point])
            upper, lower = ((ink & 0xffffff, ink >> 24 & 0xffffff)
                            if ch == '▄' else (ink >> 24 & 0xffffff, ink & 0xffffff))
            variation = noise(px + py * .3, pz, 45)
            if ground:
                ny = normals[a].y * wa + normals[b].y * wb + normals[c].y * wc
                # Autumn exposes warm litter and dry stalks, spring mixes fresh
                # green shoots with the existing darker moist ground layers.
                low, high = ((47, 84, 57), (79, 115, 54)) if season == 'spring' else ((91, 73, 48), (133, 100, 53))
                blend = f.smooth(.25, .70, variation)
                target = tuple(a * (1 - blend) + b * blend for a, b in zip(low, high))
                amount = .42 if season == 'spring' else .62
                edge = sum((3 - abs(dx)) * (3 - abs(dy))
                           for dy in range(-2, 3) for dx in range(-2, 3)
                           if (x + dx, y + dy) in ground_mask) / 81
                amount *= f.smooth(.25, .96, edge) ** 2
                amount *= f.smooth(.48, .84, ny)
                # Metre-scale variation lets green shaded undergrowth show
                # between dry clumps instead of a uniformly brown carpet.
                amount *= .35 + .65 * f.smooth(.22, .76, noise(px, pz, 24))
                if ch not in ('▄', '▀'):
                    keep = .68 if season == 'spring' else .46
                    if f.random(seed, identity + 91000) > keep:
                        # Reveal the underlying tone rather than a solid glyph.
                        ch = '▄'
                        upper = lower
                    else:
                        ch = ("'", ',', 'v', ';')[identity % 4] if season == 'spring' else ('/', '\\', ',', ';')[identity % 4]
            elif shrub:
                target = (102, 143, 63) if season == 'spring' else ((172, 103, 39) if variation > .42 else (122, 66, 40))
                amount = .70
            else:
                # Conifers keep their green identity. Spring highlights select
                # fresh shoot masses; autumn shifts them only slightly cooler.
                target = (99, 132, 66) if season == 'spring' else (36, 72, 55)
                amount = (.34 * f.smooth(.48, .78, variation)) if season == 'spring' else .10
            upper, lower = tint(upper, target, amount), tint(lower, target, amount)
            if shrub and owners[pair[0][0]] == owners[pair[1][0]]:
                if abs(depths[indexes[0]] - depths[indexes[1]]) < 35:
                    char = ("'", ',', 'v', ';')[identity % 4] if season == 'spring' else (',', ';', '/', "'")[identity % 4]
                    ch = char
                    lower = tint(lower, target, .9)
                    upper = pack(tuple(v * 1.3 for v in rgb(upper)))
            value = (ch, (1 << 48) | (lower << 24) | upper) if ch == '▄' else (ch, (1 << 48) | (upper << 24) | lower)
            if shrub and point not in result:
                shrub_cells.append((depths[indexes[1]], point, value))
            else:
                result[point] = value
    # Bounded new shrub accents; keep sparse text budget across all plant layers.
    for _, point, value in sorted(shrub_cells)[:min(256, MAX_OVERLAY_CELLS - len(result))]:
        result[point] = value
    glyphs = sorted((p for p, (ch, _) in result.items() if ch not in ('▄', '▀')),
                    key=lambda p: (p[1], p[0]))
    for point in glyphs[MAX_GLYPHS:]:
        _, ink = result[point]
        result[point] = ('▄', ink)
    return result
