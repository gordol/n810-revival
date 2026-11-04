"""Material-space surface marks -> ordinary retained character cells.

No projection, visibility, lighting, font, UI, animation clock or global state.
Producers supply already-visible, already-lit surface samples. Coordinates and
normals are in the same declared material space (world for static surfaces,
object-local for moving surfaces). See CONTRACT.md.
"""
from dataclasses import dataclass
from functools import lru_cache
import math
from typing import Iterable, Mapping, Protocol

RGB = tuple[int, int, int]
Vec3 = tuple[float, float, float]
Cell = tuple[str, int]


def rgb(value: int) -> RGB:
    return value >> 16 & 255, value >> 8 & 255, value & 255


def packed(color: RGB) -> int:
    return color[0] << 16 | color[1] << 8 | color[2]


def ink(fg: RGB, bg: RGB) -> int:
    return (1 << 48) | (packed(fg) << 24) | packed(bg)


def _color(values) -> RGB:
    # Keep arbitrary iterable/error semantics without a resumed generator per
    # channel. The temporary list contains only this color's rounded channels.
    return tuple([max(0, min(255, round(v))) for v in values])


def _identity_uncached(owner: str, seed: int) -> int:
    # Stable across Python processes, unlike hash(str).
    value = (2166136261 ^ seed) & 0xffffffff
    for byte in owner.encode('utf-8'):
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


@lru_cache(maxsize=256)
def _identity_cached(owner: str, seed: int) -> int:
    return _identity_uncached(owner,seed)


def _identity(owner: str, seed: int) -> int:
    # Only immutable exact types enter the cache. In particular int/float keys
    # must never share an entry, nor may a subclass bypass its original errors.
    if type(owner) is str and len(owner)<=256 and type(seed) is int:
        return _identity_cached(owner,seed&0xffffffff)
    return _identity_uncached(owner,seed)


def _mix(value: int) -> int:
    value = ((value ^ (value >> 16)) * 0x7feb352d) & 0xffffffff
    value = ((value ^ (value >> 15)) * 0x846ca68b) & 0xffffffff
    return value ^ (value >> 16)


@dataclass(frozen=True, slots=True)
class Sample:
    owner: str
    material: str
    position: Vec3
    normal: Vec3
    depth: float
    lit_rgb: RGB
    # True world/material-space distance covered by one half-cell, for LOD.
    footprint: float = 0.0


@dataclass(frozen=True, slots=True)
class SurfaceCell:
    x: int
    y: int
    upper: Sample | None
    lower: Sample | None
    base: Cell


@dataclass(frozen=True, slots=True)
class SurfaceFrame:
    width: int
    height: int
    cells: Iterable[SurfaceCell]


@dataclass(frozen=True, slots=True)
class Material:
    scale: float
    glyphs: str
    density: float = .65
    relief: float = .12
    contrast: float = .38
    pattern: str = 'grain'
    fade_start: float = 20.0
    fade_end: float = 80.0

    def __post_init__(self):
        if not math.isfinite(self.scale) or self.scale <= 0:
            raise ValueError('material scale must be finite and positive')
        if not self.glyphs or any(not c.isprintable() or c.isspace() for c in self.glyphs):
            raise ValueError('material needs printable non-space glyphs')
        if not 0 <= self.density <= 1 or not 0 <= self.relief <= .5 or not 0 <= self.contrast <= 1:
            raise ValueError('material density/relief/contrast outside bounds')
        if not 0 <= self.fade_start < self.fade_end or self.pattern not in ('grain', 'fiber', 'stone', 'masonry'):
            raise ValueError('invalid material fade or pattern')


@dataclass(frozen=True, slots=True)
class Mark:
    # Exposed for exact stability checks, independent of camera and frame order.
    anchor: tuple[int, int, int, int, int]
    char: str
    value: float
    admit: float


@dataclass(frozen=True, slots=True)
class SurfacePatch:
    cells: dict[tuple[int, int], Cell]
    glyphs: int
    inspected: int


class Renderer(Protocol):
    def render(self, frame: SurfaceFrame, materials: Mapping[str, Material], *, seed: int = 12345) -> SurfacePatch: ...


class ToneRenderer:
    """Swappable identity implementation: retain the producer's lit cells."""
    def render(self, frame, materials, *, seed=12345):
        return SurfacePatch({}, 0, 0)


class GlyphRenderer:
    def __init__(self, *, max_cells=8192, max_glyphs=1280):
        if not 0 <= max_glyphs <= max_cells <= 65536:
            raise ValueError('invalid surface work/output budget')
        self.max_cells, self.max_glyphs = max_cells, max_glyphs

    @staticmethod
    def mark(sample: Sample, material: Material, seed=12345) -> Mark:
        p, n, scale = sample.position, sample.normal, material.scale
        # Dominant material-space face avoids screen-space texture projection.
        axis = max(range(3), key=lambda j: abs(n[j]))
        uv = ((p[2], p[1]), (p[0], p[2]), (p[0], p[1]))[axis]
        u, v = uv[0] / scale, uv[1] / scale
        iu, iv = math.floor(u), math.floor(v)
        side = int(n[axis] < 0)
        identity = _identity(sample.owner + '\0' + sample.material, seed)
        value = _mix(identity ^ _mix(iu & 0xffffffff) ^ _mix((iv + 0x9e3779b9) & 0xffffffff) ^ (axis << 12) ^ (side << 20))
        fu, fv = u - iu, v - iv
        if material.pattern == 'masonry':
            mortar = fv < .12 or (fu + .5 * (iv & 1)) % 1 < .08
            relief = -.9 if mortar else .2 + .35 * math.sin(fu * math.pi)
        elif material.pattern == 'fiber':
            relief = math.sin((fu * 1.8 + fv * .45) * math.tau) * .55
        elif material.pattern == 'stone':
            relief = math.sin(fu * math.pi) * math.sin(fv * math.pi) - .45
        else:
            relief = ((value >> 8 & 255) / 127.5 - 1) * .65
        return Mark((identity, axis, side, iu, iv), material.glyphs[value % len(material.glyphs)], relief, (value & 65535) / 65536)

    @staticmethod
    def _eligible(cell):
        a, b = cell.upper, cell.lower
        if a is None or b is None or cell.base[0] not in ('▀', '▄'):
            return False
        if a.owner != b.owner or a.material != b.material:
            return False
        if not (math.isfinite(a.depth) and math.isfinite(b.depth)) or min(a.depth, b.depth) <= 0:
            return False
        # Do not bridge a near/far edge even if the mesh uses one owner.
        return abs(a.depth - b.depth) <= max(a.footprint * 4, b.footprint * 4, .08 * min(a.depth, b.depth), 1e-6)

    def render(self, frame, materials, *, seed=12345):
        if not 1 <= frame.width <= 4096 or not 1 <= frame.height <= 2048:
            raise ValueError('invalid surface frame dimensions')
        output, seen, glyphs, inspected = {}, set(), 0, 0
        # Bounded input scan, with deterministic row-major producer contract.
        for cell in frame.cells:
            inspected += 1
            if inspected > frame.width * frame.height:
                raise ValueError('surface producer exceeds viewport budget')
            if not 0 <= cell.x < frame.width or not 0 <= cell.y < frame.height:
                raise ValueError('surface cell outside viewport')
            if not self._eligible(cell):
                continue
            a, b = cell.upper, cell.lower
            material = materials.get(a.material)
            if material is None:
                continue
            if len(output) >= self.max_cells:
                continue
            ma, mb = self.mark(a, material, seed), self.mark(b, material, seed)
            fade = max(0.0, min(1.0, (material.fade_end - max(a.depth, b.depth)) / (material.fade_end - material.fade_start)))
            # Fixed mark scale; unresolved features fade, never grow or reseed.
            lod = min(1.0, material.scale / max(a.footprint, b.footprint, material.scale))
            strength = fade * lod
            if strength <= 0:
                continue
            ca = _color(v * (1 + ma.value * material.relief * strength) for v in a.lit_rgb)
            cb = _color(v * (1 + mb.value * material.relief * strength) for v in b.lit_rgb)
            value = ('▄', ink(cb, ca))
            if glyphs < self.max_glyphs and ma.anchor not in seen and ma.admit < material.density * strength:
                base = tuple((x + y) / 2 for x, y in zip(ca, cb))
                # Preserve existing light/color, including dark material shading.
                direction = -1 if ma.value < -.12 else 1
                contrast = material.contrast * strength * direction
                fg = _color(v * (1 + contrast) + (3 * strength if direction > 0 else 0) for v in base)
                bg = _color(v * (1 - contrast * .14) for v in base)
                value = (ma.char, ink(fg, bg))
                glyphs += 1
                seen.add(ma.anchor)
            output[cell.x, cell.y] = value
        return SurfacePatch(output, glyphs, inspected)
