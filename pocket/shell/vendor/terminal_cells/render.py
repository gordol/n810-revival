"""Pure character-frame rendering."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from .models import (
    ASPECT,
    Bacterium,
    Cell,
    DIVISION_TIME,
    ENCLOSE_TIME,
    MICROBE_KINDS,
    Phage,
    SEAL_TIME,
    State,
    TAU,
    angle_delta,
    attachment_pose,
    bacterial_scale,
    clamp,
    disc_axes,
    division_stage,
    microbe_axes,
    nucleus_radii,
    phage_geometry,
    smooth,
    viral_stage,
)
from .world import World


class Ink(Enum):
    DEBRIS = 1
    RED = 2
    RED_DIM = 3
    CYTOPLASM = 4
    MEMBRANE = 5
    NUCLEUS = 6
    BACTERIA = 7
    VESICLE = 8
    TEXT = 9
    MUTED = 10
    COCCUS = 11
    SPIRAL = 12
    SPINDLE = 13
    DNA = 14
    CAPTURE = 15
    MITOCHONDRION = 16
    RETICULUM = 17
    NUCLEOLUS = 18
    MICROBIAL_DNA = 19
    PHAGE = 20
    VIRAL_DNA = 21
    LYSIS = 22
    BACILLUS = 23
    SPIROCHETE = 24
    VIBRIO = 25
    COLONY = 26
    YEAST = 27
    TRYPANOSOME = 28
    FUNGUS = 29
    NEUTROPHIL = 30
    NUTRIENT = 31
    ROTIFER = 32
    NET = 33
    GLASS = 34
    BACKGROUND_FAR = 35
    BACKGROUND_NEAR = 36
    # Background tints for filled bodies: glyphs keep their ink and draw on top.
    FILL_CYTOPLASM = 37
    FILL_NEUTROPHIL = 38
    FILL_NUCLEUS = 39
    FILL_RED = 40
    FILL_RED_PALE = 41


# Entity hues retain their meaning across colored themes. Internal anatomy and
# transient effects may share a family; outside-cell silhouettes have distinct inks.
_DARK = [
    (239, 0),
    (196, 1),
    (88, 1),
    (23, 6),
    (115, 2),
    (141, 5),
    (222, 3),
    (108, 2),
    (252, 7),
    (244, 7),
    (81, 6),
    (213, 5),
    (75, 4),
    (183, 5),
    (231, 7),
    (173, 1),
    (66, 6),
    (225, 7),
    (250, 7),
    (154, 2),
    (121, 2),
    (231, 7),
    (208, 3),
    (165, 5),
    (44, 6),
    (69, 4),
    (180, 3),
    (230, 7),
    (100, 3),
    (153, 4),
    (65, 2),
    (216, 1),
    (189, 5),
    (246, 7),
    (236, 7),
    (240, 7),
    (235, 0),
    (236, 0),
    (53, 0),
    (52, 0),
    (234, 0),
]
_LIGHT = [
    (250, 7),
    (160, 1),
    (124, 1),
    (152, 6),
    (29, 2),
    (90, 5),
    (94, 3),
    (28, 2),
    (16, 0),
    (242, 0),
    (25, 6),
    (126, 5),
    (24, 4),
    (55, 5),
    (16, 0),
    (166, 1),
    (30, 6),
    (54, 5),
    (237, 0),
    (64, 2),
    (22, 2),
    (16, 0),
    (166, 3),
    (91, 5),
    (30, 6),
    (20, 4),
    (137, 3),
    (235, 0),
    (58, 3),
    (67, 4),
    (65, 2),
    (167, 1),
    (97, 5),
    (242, 0),
    (249, 0),
    (245, 0),
    (254, 7),
    (255, 7),
    (189, 7),
    (224, 7),
    (255, 7),
]
_AMBER = list(_DARK)
_AMBER[Ink.CYTOPLASM.value - 1] = (58, 3)
_AMBER[Ink.TEXT.value - 1] = (230, 7)
_AMBER[Ink.MUTED.value - 1] = (137, 3)
_AMBER[Ink.FILL_CYTOPLASM.value - 1] = (234, 0)
PALETTES = {"slide": _DARK, "amber": _AMBER, "light": _LIGHT, "mono": [(244, 7)] * len(Ink)}
FILL_INKS = (
    Ink.FILL_CYTOPLASM,
    Ink.FILL_NEUTROPHIL,
    Ink.FILL_NUCLEUS,
    Ink.FILL_RED,
    Ink.FILL_RED_PALE,
)


BACTERIA_INKS = dict(
    zip(
        MICROBE_KINDS,
        (
            Ink.BACTERIA,
            Ink.COCCUS,
            Ink.SPIRAL,
            Ink.BACILLUS,
            Ink.SPIROCHETE,
            Ink.VIBRIO,
            Ink.COLONY,
            Ink.YEAST,
            Ink.TRYPANOSOME,
        ),
    )
)


@dataclass(frozen=True)
class Pixel:
    char: str = " "
    ink: Ink = Ink.DEBRIS
    bold: bool = False
    # Optional background tint; None keeps the terminal background.
    bg: Ink | None = None


EMPTY = Pixel()
KEEP = object()


class Frame:
    """A character grid. With ``fill``, bodies also carry background tints.

    Fill mode pairs a background color with a foreground glyph in each cell:
    cell bodies become solid tinted shapes and membranes, organelles, and
    microbes are drawn as glyphs on top, instead of texture characters
    standing in for the interior.
    """

    def __init__(self, columns: int, rows: int, fill: bool = False):
        self.width, self.height = columns, rows
        self.fill = fill
        self.pixels = [[EMPTY for _ in range(columns)] for _ in range(rows)]

    def put(self, x: int, y: int, char: str, ink: Ink, bold: bool = False, bg=KEEP) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            if bg is KEEP:
                # Glyphs drawn over a filled body stay inside it.
                bg = self.pixels[y][x].bg
            self.pixels[y][x] = Pixel(char, ink, bold, bg if self.fill else None)

    def point(self, x: float, y: float, char: str, ink: Ink, bold: bool = False) -> None:
        self.put(round(x), round(y / ASPECT), char, ink, bold)

    def text(
        self, x: int, y: int, text: str, ink: Ink = Ink.TEXT, bold: bool = False, bg=None
    ) -> None:
        # Captions default to the plain background so they read over any body.
        for offset, char in enumerate(text):
            self.put(x + offset, y, char, ink, bold, bg)

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        ink: Ink,
        unicode: bool = False,
        bg=KEEP,
    ) -> None:
        dx, dy = x2 - x1, y2 - y1
        if abs(dy) < abs(dx) * 0.45:
            char = "─" if unicode else "-"
        elif abs(dx) < abs(dy) * 0.3:
            char = "│" if unicode else "|"
        else:
            char = "\\" if dx * dy > 0 else "/"
        for col, row in line_pixels(x1, y1, x2, y2):
            self.put(col, row, char, ink, bg=bg)

    def plain(self) -> str:
        return "\n".join("".join(p.char for p in row) for row in self.pixels)


def line_pixels(x1: float, y1: float, x2: float, y2: float):
    # Rasterize in character coordinates: subpixel sampling can thicken
    # diagonal strokes into staircases of adjacent slashes.
    x, y, end_x, end_y = round(x1), round(y1 / ASPECT), round(x2), round(y2 / ASPECT)
    width, height = abs(end_x - x), abs(end_y - y)
    sx, sy = 1 if x < end_x else -1, 1 if y < end_y else -1
    error = width - height
    while True:
        yield x, y
        if (x, y) == (end_x, end_y):
            break
        twice = 2 * error
        if twice > -height:
            error -= height
            x += sx
        if twice < width:
            error += width
            y += sy


def membrane_char(angle: float, unicode: bool) -> str:
    if abs(math.sin(angle)) > 0.82:
        return "─" if unicode else "-"
    if abs(math.cos(angle)) > 0.9:
        return "│" if unicode else "|"
    return "/" if math.sin(2 * angle) > 0 else "\\"


def contour_pixels(points):
    """Keep an eight-connected, single-stroke path through sampled curves."""
    sampled = []
    for x, y, angle in points:
        pixel = round(x), round(y / ASPECT), angle
        if not sampled or pixel[:2] != sampled[-1][:2]:
            sampled.append(pixel)
    if not sampled:
        return sampled
    # Tiny rings need every corner to retain a visible enclosed body.
    if (
        max(p[0] for p in sampled) - min(p[0] for p in sampled) < 5
        or max(p[1] for p in sampled) - min(p[1] for p in sampled) < 3
    ):
        return sampled
    pixels = []
    for pixel in sampled:
        if len(pixels) >= 2:
            previous, corner = pixels[-2:]
            forward = (corner[0] - previous[0]) * (pixel[0] - corner[0]) + (
                corner[1] - previous[1]
            ) * (pixel[1] - corner[1])
            if forward >= 0 and max(abs(pixel[0] - previous[0]), abs(pixel[1] - previous[1])) <= 1:
                pixels.pop()
        pixels.append(pixel)
    return pixels


def draw_cell(frame: Frame, cell: Cell, now: float, unicode: bool, *, nucleus: bool = True) -> None:
    extent = cell.extent()
    left, right = max(0, int(cell.x - extent)), min(frame.width, math.ceil(cell.x + extent))
    top = max(0, int((cell.y - extent) / ASPECT))
    bottom = min(frame.height, math.ceil((cell.y + extent) / ASPECT))
    body = set()
    for row in range(top, bottom):
        for col in range(left, right):
            dx, dy = col - cell.x, row * ASPECT - cell.y
            angle = math.atan2(dy, dx)
            body_radius = cell.body_outline(angle, now)
            radius = cell.outline(angle, now) if cell.state is State.ENCLOSE else body_radius
            distance = math.hypot(dx, dy)
            if distance <= body_radius:
                body.add((col, row))
            # A tinted body also covers the band just inside the membrane, which
            # would otherwise show as notches of plain slide along the outline.
            if distance < radius - 0.65 or (frame.fill and distance <= radius):
                # Occlude the background, with sparse, stable cytoplasmic granules.
                speckle = (
                    (col - round(cell.x)) * 31 + (row - round(cell.y / ASPECT)) * 17 + cell.id * 7
                ) % 43
                char = "·" if unicode else "."
                tint = Ink.FILL_NEUTROPHIL if cell.kind == "neutrophil" else Ink.FILL_CYTOPLASM
                frame.put(col, row, char if speckle == 0 else " ", Ink.CYTOPLASM, bg=tint)
    mouth = 0.0
    if cell.state is State.ENCLOSE:
        mouth = 0.34 * smooth(cell.elapsed / 1.5) * (1 - smooth((cell.elapsed - SEAL_TIME) / 1.5))
    samples = max(80, math.ceil(cell.radius * 16))
    points = []
    for index in range(samples + 1):
        angle = index * TAU / samples
        radius = cell.body_outline(angle, now)
        points.append((cell.x + math.cos(angle) * radius, cell.y + math.sin(angle) * radius, angle))
    for col, row, angle in contour_pixels(points):
        if mouth and abs(angle_delta(angle, cell.reach_angle)) < mouth:
            continue
        frame.put(
            col,
            row,
            membrane_char(angle, unicode),
            Ink.NEUTROPHIL if cell.kind == "neutrophil" else Ink.MEMBRANE,
            # The outline sits on the plain slide so the tinted body has a crisp edge.
            bg=None,
        )
    if cell.state is State.ENCLOSE:
        draw_capture(frame, cell, unicode, now)
    draw_organelles(frame, cell, now, unicode)
    if cell.kind == "neutrophil":
        for col, row in body:
            dx, dy = col - round(cell.x), row - round(cell.y / ASPECT)
            if (dx * 17 + dy * 31) % 41 == 0 and math.hypot(dx, dy * ASPECT) < cell.radius * 0.78:
                frame.put(col, row, ":", Ink.CYTOPLASM)
    for vesicle in cell.vesicles:
        x = cell.x + math.cos(vesicle.angle) * cell.radius * vesicle.distance
        y = cell.y + math.sin(vesicle.angle) * cell.radius * vesicle.distance
        if vesicle.age < 9:
            size = clamp(cell.radius * 0.24, 2.0, 3.6)
            draw_ring(
                frame,
                x,
                y,
                size,
                size * 1.1,
                Ink.CAPTURE if vesicle.age < 2 else Ink.VESICLE,
                unicode,
            )
            content = Bacterium(-1, x, y, vesicle.angle, 0, vesicle.kind, 0, 0)
            draw_bacterium(frame, content, unicode, now, compact=True)
        else:
            spread = (vesicle.age - 9) * 0.25
            frame.point(x - spread, y - spread, ":" if vesicle.age < 11 else ".", Ink.VESICLE)
            frame.point(x + spread, y + spread, ".", BACTERIA_INKS[vesicle.kind])
    if nucleus:
        draw_nucleus(frame, cell, unicode)


def draw_ring(
    frame: Frame,
    x: float,
    y: float,
    rx: float,
    ry: float,
    ink: Ink,
    unicode: bool,
    fraction: float = 1.0,
    bg=KEEP,
) -> None:
    # Mask rasterized glyphs, rather than samples: many samples can land on a
    # single glyph, which otherwise kept a dissolving envelope visibly intact.
    samples = max(40, math.ceil(max(rx, ry) * 16))
    points = []
    for index in range(samples + 1):
        angle = index * TAU / samples
        points.append((x + math.cos(angle) * rx, y + math.sin(angle) * ry, angle))
    for col, row, angle in contour_pixels(points):
        order = ((col - round(x)) * 7 + (row - round(y / ASPECT)) * 11) % 17 / 17
        if order < fraction:
            frame.put(col, row, membrane_char(angle, unicode), ink, bg=bg)


def draw_organelles(frame: Frame, cell: Cell, now: float, unicode: bool) -> None:
    if cell.radius < 7:
        return
    division = (
        smooth((cell.elapsed - 26) / (DIVISION_TIME - 26)) if cell.state is State.DIVIDE else 0
    )
    ux, uy = math.cos(cell.division_angle), math.sin(cell.division_angle)

    def plot(x, y, char, ink):
        col, row = round(x), round(y / ASPECT)
        dx, dy = col - cell.x, row * ASPECT - cell.y
        if math.hypot(dx, dy) < cell.outline(math.atan2(dy, dx), now) - 1.1:
            frame.put(col, row, char, ink)

    compact = frame.width < 110 or frame.height < 36 or cell.radius < 13
    visible = {"mitochondrion": 0, "reticulum": 0, "lysosome": 0}
    for network in cell.organelles:
        visible[network.kind] += 1
        if compact and visible[network.kind] > (2 if network.kind == "mitochondrion" else 1):
            continue
        ink = {
            "mitochondrion": Ink.MITOCHONDRION,
            "reticulum": Ink.RETICULUM,
            "lysosome": Ink.VESICLE,
        }[network.kind]
        points, sides = [], []
        for index, (x, y) in enumerate(network.nodes):
            side = 1 if x * ux + y * uy >= 0 else -1
            sides.append(side)
            wiggle = 0.009 * math.sin(now * 0.35 + network.phase + index * 0.5)
            x = x * (1 - 0.28 * division) + side * ux * 0.62 * division
            y = y * (1 - 0.28 * division) + side * uy * 0.62 * division
            points.append(
                (cell.x + (x + wiggle) * cell.radius, cell.y + (y + wiggle * 0.6) * cell.radius)
            )
        for a, b in network.edges:
            # Keep the envelope distinct from the nucleus: no ladder rungs,
            # and just one fold in compact windows. State remains unchanged.
            if network.kind == "reticulum" and (
                a >= (6 if compact else 12) or b >= (6 if compact else 12)
            ):
                continue
            if cell.state is State.DIVIDE and cell.elapsed >= 40 and sides[a] != sides[b]:
                continue
            x, y = points[a]
            xx, yy = points[b]
            dx, dy = xx - x, yy - y
            char = membrane_char(math.atan2(dy, dx) + math.pi / 2, unicode)
            for col, row in line_pixels(x, y, xx, yy):
                plot(col, row * ASPECT, char, ink)
        if network.kind == "lysosome":
            plot(*points[0], "o", ink)
        elif network.kind == "mitochondrion":
            # A few compact folded sections remain among the branched tubules.
            x, y = points[len(points) // 2]
            plot(x, y, "≋" if unicode else "~", ink)


def draw_nuclear_body(
    frame: Frame, x: float, y: float, radius: float, unicode: bool, nucleolus: bool = True
) -> None:
    # One raster anchor keeps the envelope, chromatin, and nucleolus together.
    cx, cy = round(x), round(y / ASPECT)
    rx, ry = nucleus_radii(radius)
    rx, rows = max(2, round(rx)), max(1, round(ry / ASPECT))
    mask = {
        (col, row)
        for row in range(-rows, rows + 1)
        for col in range(-rx, rx + 1)
        if (col / rx) ** 2 + (row / rows) ** 2 <= 1.12
    }
    for col, row in mask:
        if any((col + dx, row + dy) not in mask for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]):
            char = membrane_char(math.atan2(row * ASPECT, col), unicode)
        elif frame.fill:
            # The tint carries the nucleoplasm; texture glyphs would only add noise.
            char = " "
        else:
            char = "░" if unicode else ":"
        frame.put(cx + col, cy + row, char, Ink.NUCLEUS, bg=Ink.FILL_NUCLEUS)
    for col, row in [(-1, -1), (1, 1)]:
        if (col, row) in mask:
            frame.put(cx + col, cy + row, "~", Ink.NUCLEUS)
    if nucleolus:
        frame.put(cx, cy, "●" if unicode else "O", Ink.NUCLEOLUS, True)


def draw_mitosis(frame: Frame, cell: Cell, unicode: bool) -> None:
    stage, progress = division_stage(cell.elapsed)
    ux, uy = math.cos(cell.division_angle), math.sin(cell.division_angle)
    scale = cell.radius / 7.2
    count = 5 if cell.radius >= 11 else 3
    offsets = [(index - (count - 1) / 2) * 4.4 * scale / (count - 1) for index in range(count)]

    def point(along: float, across: float) -> tuple[float, float]:
        return cell.x + ux * along - uy * across, cell.y + uy * along + ux * across

    def chromosome(along: float, across: float, char: str = "X") -> None:
        frame.point(*point(along, across), char, Ink.DNA, True)

    if stage in ("prophase", "envelope breakdown"):
        envelope = 1.0 if stage == "prophase" else 1 - progress
        rx, ry = nucleus_radii(cell.radius)
        draw_ring(frame, cell.x, cell.y, rx + 0.6, ry + 0.6, Ink.NUCLEUS, unicode, envelope)
        condensation = progress if stage == "prophase" else 1
        for index, across in enumerate(offsets):
            along = (-0.8 if index % 2 == 0 else 0.8) * scale
            chromosome(
                along, across, "~" if condensation < 0.45 else "x" if condensation < 0.8 else "X"
            )
        return

    if stage == "spindle formation":
        alignment = smooth(progress)
        clusters = [
            (along * (1 - alignment), across, "X")
            for along, across in zip(
                [(-1.4 if i % 2 == 0 else 1.2) * scale for i in range(count)], offsets
            )
        ]
        poles = cell.radius * (0.3 + 0.4 * alignment)
    elif stage == "metaphase":
        clusters = [(math.sin(cell.elapsed * 2) * 0.12, across, "X") for across in offsets]
        poles = cell.radius * 0.7
    elif stage == "anaphase":
        separation = cell.radius * (0.12 + 0.43 * smooth(progress))
        clusters = [
            (sign * separation, across * (1 - progress * 0.35), "<" if sign < 0 else ">")
            for sign in (-1, 1)
            for across in offsets
        ]
        poles = cell.radius * 0.88
    else:
        separation = (
            cell.radius * (0.55 + 0.165 * smooth(progress))
            if stage == "telophase"
            else cell.radius * 0.715
        )
        # Chromatids decondense as envelopes reform, then become compact nuclei.
        for sign in (-1, 1):
            x, y = point(sign * separation, 0)
            fraction = smooth(progress) if stage == "telophase" else 1
            rx, ry = nucleus_radii(cell.radius * 0.72)
            draw_ring(frame, x, y, rx, ry, Ink.NUCLEUS, unicode, fraction)
            if stage == "telophase" and progress < 0.65:
                for across in (-1.3 * scale, 1.3 * scale):
                    chromosome(sign * separation, across, ":" if progress > 0.35 else "x")
            else:
                draw_nuclear_body(frame, x, y, cell.radius * 0.72, unicode)
        if stage == "cytokinesis" and progress < 0.75:
            neck = cell.outline(cell.division_angle + math.pi / 2, cell.elapsed) * 0.8
            x, y = point(0, -neck)
            x2, y2 = point(0, neck)
            frame.line(x, y, x2, y2, Ink.CAPTURE, unicode)
        return

    # Fibers appear from both poles and remain attached to organizing DNA.
    for sign in (-1, 1):
        px, py = point(sign * poles, 0)
        for along, across, _ in clusters:
            if stage == "anaphase" and along * sign < 0:
                continue
            x, y = point(along, across)
            frame.line(px, py, x, y, Ink.SPINDLE, unicode)
        frame.point(px, py, "*", Ink.SPINDLE, True)
    for along, across, char in clusters:
        chromosome(along, across, char)


def draw_capture(frame: Frame, cell: Cell, unicode: bool, now: float = 0) -> None:
    cx, cy = cell.capture_center()
    ca, sa = math.cos(cell.capture_axis), math.sin(cell.capture_axis)
    elapsed = cell.elapsed
    transport = smooth((elapsed - SEAL_TIME) / (ENCLOSE_TIME - SEAL_TIME))
    vesicle = clamp(cell.radius * 0.24, 2.0, 3.6)
    a = (cell.capture_a + 1.2) * (1 - transport) + vesicle * transport
    b = (cell.capture_b + 1.3) * (1 - transport) + vesicle * 1.1 * transport
    beta = cell.reach_angle - cell.capture_axis
    start = math.atan2(-math.sin(beta) / b, -math.cos(beta) / a)

    def rim(theta):
        x, y = math.cos(theta) * a, math.sin(theta) * b
        return cx + ca * x - sa * y, cy + sa * x + ca * y

    if elapsed < SEAL_TIME:
        wrapping = smooth((elapsed - 1.0) / 5.8)
        ink = Ink.CAPTURE if elapsed > 6.7 else Ink.MEMBRANE
        for sign in (-1, 1):
            angle = cell.reach_angle + sign * 0.34
            radius = cell.body_outline(angle, now)
            base = cell.x + math.cos(angle) * radius, cell.y + math.sin(angle) * radius
            near = rim(start + sign * 0.15)
            control = (
                (base[0] + near[0]) * 0.5 - math.sin(cell.reach_angle) * sign,
                (base[1] + near[1]) * 0.5 + math.cos(cell.reach_angle) * sign,
            )
            previous = base
            for index in range(1, 17):
                t = index / 16 * smooth(elapsed / 1.2)
                x = (1 - t) ** 2 * base[0] + 2 * (1 - t) * t * control[0] + t * t * near[0]
                y = (1 - t) ** 2 * base[1] + 2 * (1 - t) * t * control[1] + t * t * near[1]
                # Wrapping pseudopods are the cell's outer membrane: keep them untinted.
                frame.line(*previous, x, y, ink, unicode, bg=None)
                previous = x, y
            if elapsed >= 1.2:
                previous = near
                for index in range(1, 49):
                    theta = start + sign * (0.15 + (math.pi - 0.15) * wrapping * index / 48)
                    x, y = rim(theta)
                    frame.line(*previous, x, y, ink, unicode, bg=None)
                    previous = x, y
            elif elapsed < 1.0:
                frame.point(*near, "+", Ink.CAPTURE, True)
    else:
        previous = rim(0)
        for index in range(1, 81):
            x, y = rim(index * TAU / 80)
            frame.line(*previous, x, y, Ink.CAPTURE if elapsed < 7.5 else Ink.VESICLE, unicode)
            previous = x, y
        # Two shoulders narrow into a neck before the sealed phagosome detaches.
        if transport < 0.55:
            for sign in (-1, 1):
                angle = cell.reach_angle + sign * 0.30 * (1 - transport)
                radius = cell.body_outline(angle, now)
                base = cell.x + math.cos(angle) * radius, cell.y + math.sin(angle) * radius
                frame.line(*base, *rim(start + sign * 0.25), Ink.MEMBRANE, unicode, bg=None)


def draw_nucleus(frame: Frame, cell: Cell, unicode: bool) -> None:
    if cell.kind == "neutrophil":
        # Three persistent lobes linked by thin chromatin bridges.
        cx, cy = round(cell.x), round(cell.y / ASPECT) * ASPECT
        points = [
            (cx - cell.radius * 0.28, cy - 2),
            (cx, cy + 2),
            (cx + cell.radius * 0.28, cy - 2),
        ]
        for left, right in zip(points, points[1:]):
            frame.line(*left, *right, Ink.NUCLEUS, unicode)
        for x, y in points:
            draw_nuclear_body(frame, x, y, cell.radius * 0.48, unicode, nucleolus=False)
    elif cell.state is State.DIVIDE:
        draw_mitosis(frame, cell, unicode)
    else:
        draw_nuclear_body(
            frame,
            cell.x - math.cos(cell.phase) * cell.radius * 0.22,
            cell.y - math.sin(cell.phase) * cell.radius * 0.22,
            cell.radius,
            unicode,
        )


def render(world: World, unicode: bool = False, fill: bool = False) -> Frame:
    frame = Frame(round(world.width), round(world.height / ASPECT), fill)
    compact_view = frame.width < 110 or frame.height < 36
    draw_nutrients(frame, world, unicode)
    draw_hyphae(frame, world, unicode)
    # Stable size-based depth cues add contrast without adding particles or
    # consuming simulation randomness. Both layers remain behind cell bodies.
    for particle in world.debris:
        distant = particle.size < 0.8
        frame.point(
            particle.x,
            particle.y,
            "." if distant else "·" if unicode else ":",
            Ink.BACKGROUND_FAR if distant else Ink.BACKGROUND_NEAR,
        )
    for red in world.red_cells:
        rx, ry = disc_axes(red)
        for row in range(math.floor((red.y - ry) / ASPECT), math.ceil((red.y + ry) / ASPECT) + 1):
            for col in range(math.floor(red.x - rx), math.ceil(red.x + rx) + 1):
                distance = ((col - red.x) / rx) ** 2 + ((row * ASPECT - red.y) / ry) ** 2
                if distance < 0.85:
                    pale = distance < 0.23
                    if frame.fill:
                        # The biconcave center reads as a paler tint, not a texture.
                        tint = Ink.FILL_RED_PALE if pale else Ink.FILL_RED
                        frame.put(col, row, " ", Ink.RED_DIM, bg=tint)
                    else:
                        char = ("░" if unicode else ".") if pale else " "
                        frame.put(col, row, char, Ink.RED_DIM)
        draw_ring(frame, red.x, red.y, rx, ry, Ink.RED, unicode, bg=None)
    for phage in world.phages.values():
        draw_phage(frame, phage, unicode)
    for capsid in world.spent_capsids:
        draw_phage(frame, capsid, unicode, contraction=1, empty=True)
    # Free bacteria are behind the large cells; captured bacteria appear in the cup.
    for bacterium in world.bacteria.values():
        owner = next((c for c in world.cells if c.id == bacterium.owner), None)
        if owner is None or owner.state is not State.ENCLOSE:
            draw_bacterium(
                frame, bacterium, unicode, world.time, world, tail=0.55 if compact_view else 1.0
            )
    for cell in sorted(world.cells, key=lambda c: c.radius):
        event = world.events.active
        if event is not None and event.kind == "net" and event.source == cell.id and event.age >= 2:
            source = Frame(frame.width, frame.height, frame.fill)
            draw_cell(source, cell, world.time, unicode, nucleus=False)
            fraction = 1 - smooth((event.age - 6) / 4)
            for row, pixels in enumerate(source.pixels):
                for col, pixel in enumerate(pixels):
                    if pixel != EMPTY and (col * 17 + row * 31) % 101 / 101 < fraction:
                        frame.put(col, row, pixel.char, pixel.ink, pixel.bold, pixel.bg)
        else:
            draw_cell(frame, cell, world.time, unicode)
    for bacterium in world.bacteria.values():
        owner = next((c for c in world.cells if c.id == bacterium.owner), None)
        if owner and owner.state is State.ENCLOSE:
            draw_bacterium(
                frame,
                bacterium,
                unicode,
                world.time,
                world,
                compact=owner.elapsed >= SEAL_TIME,
                tail=1 - smooth(owner.elapsed / SEAL_TIME),
            )
            # A late-stage capture can cross the nuclear anchor; keep the
            # nucleus connected rather than letting a microbe erase half of it.
            draw_nucleus(frame, owner, unicode)
    for burst in world.bursts:
        radius = 2 + burst.age * 9
        for index in range(12):
            angle = burst.angle + index * TAU / 12
            x, y = burst.x + math.cos(angle) * radius, burst.y + math.sin(angle) * radius
            if next(world._obstacles(x, y, 1.1), None) is None:
                char = "*" if burst.age < 0.35 else ":" if burst.age < 1 else "."
                frame.point(x, y, char, Ink.LYSIS, burst.age < 0.5)
    from .event_render import draw_sighting

    draw_sighting(frame, world, unicode)
    from .lab_render import draw_lab

    draw_lab(frame, world, unicode)
    return frame


def draw_phage(
    frame: Frame, phage: Phage, unicode: bool, contraction: float = 0, empty: bool = False
) -> None:
    # Tail/fork faces the host. Sideways sprites use two columns; vertical
    # sprites fit in a single terminal cell, including the ASCII fallback.
    ink = Ink.MUTED if empty else Ink.PHAGE
    ux, uy = math.cos(phage.angle), math.sin(phage.angle)
    bold = not empty and contraction < 0.5
    if abs(ux) > abs(uy):
        frame.text(
            round(phage.x - 0.5),
            round(phage.y / ASPECT),
            "-<" if ux > 0 else ">-",
            ink,
            bold,
            bg=KEEP,
        )
    else:
        char = ("ᛦ" if uy > 0 else "ᛘ") if unicode else "Y"
        frame.point(phage.x, phage.y, char, ink, bold)


def draw_infection(frame: Frame, bacterium: Bacterium, unicode: bool, point) -> None:
    infection = bacterium.infection
    stage, progress = viral_stage(infection.age)
    x, y, angle = attachment_pose(bacterium)
    contraction = smooth(progress) if stage == "injection" else (0 if stage == "attachment" else 1)
    offset = 0.5 - 0.2 * contraction
    shell = Phage(-1, x - math.cos(angle) * offset, y - math.sin(angle) * offset, angle=angle)
    draw_phage(frame, shell, unicode, contraction, empty=infection.age >= 7)
    if stage in ("attachment", "injection"):
        if stage == "injection":
            head, tip = phage_geometry(shell, contraction)
            if progress < 0.5:
                start, end, t = head, tip, progress * 2
            else:
                start, end, t = tip, (bacterium.x, bacterium.y), (progress - 0.5) * 2
            frame.line(*start, *end, Ink.VIRAL_DNA, unicode)
            frame.point(
                start[0] * (1 - t) + end[0] * t,
                start[1] * (1 - t) + end[1] * t,
                "•" if unicode else "*",
                Ink.VIRAL_DNA,
                True,
            )
            draw_phage(frame, shell, unicode, contraction)
    elif stage == "replication":
        positions = [(-1.8, -0.6), (0, 0.6), (1.8, -0.6), (-0.8, 0.6), (0.8, -0.6)]
        count = 1 + min(4, int(progress * 5))
        for along, across in positions[:count]:
            frame.point(*point(along, across), "≋" if unicode else "~", Ink.VIRAL_DNA, True)
    else:
        count = 2 + min(3, int(progress * 4)) if stage == "assembly" else 5
        capsids = [(-1.8, -0.8), (0, -0.8), (1.8, -0.8), (-0.9, 0.8), (0.9, 0.8)][:count]
        for index, (along, across) in enumerate(capsids):
            frame.point(
                *point(along, across),
                ("ᛦ" if index % 2 else "ᛘ") if unicode else "Y",
                Ink.PHAGE,
                True,
            )


def draw_nutrients(frame: Frame, world: World, unicode: bool) -> None:
    for patch in world.nutrients:
        radius = patch.radius
        for row in range(
            max(0, math.floor((patch.y - radius) / ASPECT)),
            min(frame.height, math.ceil((patch.y + radius) / ASPECT) + 1),
        ):
            for col in range(
                max(0, math.floor(patch.x - radius)),
                min(frame.width, math.ceil(patch.x + radius) + 1),
            ):
                dx, dy = col - patch.x, row * ASPECT - patch.y
                if dx * dx + dy * dy > radius * radius:
                    continue
                speckle = ((col - round(patch.x)) * 17 + (row - round(patch.y / ASPECT)) * 31) % 19
                threshold = 4 if patch.amount > 2 else 2
                if (
                    speckle < threshold
                    and next(world._obstacles(col, row * ASPECT, 1), None) is None
                ):
                    frame.put(col, row, "·" if unicode else ".", Ink.NUTRIENT)


def draw_hyphae(frame: Frame, world: World, unicode: bool) -> None:
    for hypha in world.hyphae:
        for a, b in hypha.edges:
            x, y = hypha.nodes[a]
            xx, yy = hypha.nodes[b]
            steps = max(1, math.ceil(math.hypot(xx - x, yy - y) * 2))
            for step in range(steps + 1):
                px, py = x + (xx - x) * step / steps, y + (yy - y) * step / steps
                if next(world._obstacles(px, py, 1.3), None) is None:
                    char = (
                        "+"
                        if step == 0
                        else membrane_char(math.atan2(yy - y, xx - x) + math.pi / 2, unicode)
                    )
                    frame.point(px, py, char, Ink.FUNGUS)
        for index, _ in hypha.tips:
            x, y = hypha.nodes[index]
            if next(world._obstacles(x, y, 1.3), None) is None:
                frame.point(x, y, "o", Ink.FUNGUS)


def draw_special_microbe(
    frame: Frame, microbe: Bacterium, unicode: bool, now: float, point, compact: bool
) -> bool:
    kind, ink = microbe.kind, BACTERIA_INKS[microbe.kind]

    def ellipse(cx, cy, a, b):
        points = []
        for index in range(65):
            theta = index * TAU / 64
            x, y = point(cx + math.cos(theta) * a, cy + math.sin(theta) * b)
            points.append((x, y, theta + microbe.angle))
        for col, row, angle in contour_pixels(points):
            frame.put(col, row, membrane_char(angle, unicode), ink)

    def curve(points):
        samples = []
        previous = None
        for along, across in points:
            x, y = point(along, across)
            tangent = math.atan2(y - previous[1], x - previous[0]) if previous else microbe.angle
            samples.append((x, y, tangent + math.pi / 2))
            previous = x, y
        for col, row, angle in contour_pixels(samples):
            frame.put(col, row, membrane_char(angle, unicode), ink)

    if kind == "bacillus":
        for index in range(microbe.units):
            x = (index - (microbe.units - 1) / 2) * 3.4
            ellipse(x, 0, 2.3, 1.65)
            frame.point(*point(x, 0), ":", Ink.MICROBIAL_DNA)
    elif kind == "spirochete":
        curve(
            [
                (-7 + index * 14 / 80, math.sin(index / 80 * TAU * 3 - now * 5 + microbe.id) * 1.5)
                for index in range(81)
            ]
        )
    elif kind == "vibrio":
        for side in (-1, 1):
            curve(
                [
                    (
                        x,
                        0.7 * (x / 2) ** 2
                        - 0.8
                        + side * 0.65 * math.sqrt(max(0, 1 - (x / 3.3) ** 2)),
                    )
                    for x in [-3.3 + i * 6.6 / 48 for i in range(49)]
                ]
            )
        frame.point(*point(0, -0.8), ":", Ink.MICROBIAL_DNA)
    elif kind == "colony":
        ellipse(0, 0, 1.35, 1.35)
        for index in range(microbe.units):
            theta = index * TAU / microbe.units
            ellipse(math.cos(theta) * 3.1, math.sin(theta) * 3.1, 1.35, 1.35)
    elif kind == "yeast":
        ellipse(0, 0, 3.3, 2.7)
        frame.point(*point(-1, 0), "o", ink)
        frame.point(*point(1, 0), "●" if unicode else "*", Ink.MICROBIAL_DNA)
        if microbe.bud > 0:
            growth = smooth(microbe.bud)
            ellipse(3.2 + growth * 1.8, 0, 0.4 + growth * 2, 0.4 + growth * 1.8)
            if growth > 0.6:
                frame.point(*point(5, 0), "·" if unicode else ".", Ink.MICROBIAL_DNA)
    elif kind == "trypanosome":
        for side in (-1, 1):
            curve(
                [
                    (
                        -7 + i * 14 / 64,
                        math.sin(i / 64 * math.pi)
                        * (side * 1.8 + math.sin(i / 64 * TAU * 1.5 - now * 5) * 0.55),
                    )
                    for i in range(65)
                ]
            )
        # The attached flagellum outlines an undulating membrane along one side.
        curve(
            [
                (
                    -7 + i * 14 / 64,
                    math.sin(i / 64 * math.pi)
                    * (2.0 + math.sin(i / 64 * TAU * 2 - now * 5) * 0.65),
                )
                for i in range(65)
            ]
        )
        if microbe.bud > 0:
            reach = 6 * smooth(microbe.bud)
            frame.line(*point(-reach, 0), *point(reach, 0), ink, unicode)
            for side in (-1, 1):
                frame.point(*point(0, side * (1 + microbe.bud)), "o", Ink.MICROBIAL_DNA)
        else:
            frame.point(*point(0, 0), "●" if unicode else "O", Ink.MICROBIAL_DNA)
        frame.point(*point(-4, 0), ".", Ink.MICROBIAL_DNA)
    else:
        return False
    return True


def draw_bacterium(
    frame: Frame,
    bacterium: Bacterium,
    unicode: bool,
    now: float = 0,
    world: World | None = None,
    compact: bool = False,
    tail: float = 1.0,
) -> None:
    ink = BACTERIA_INKS[bacterium.kind]
    ux, uy = math.cos(bacterium.angle), math.sin(bacterium.angle)
    a, b = microbe_axes(bacterium)
    scale = min(0.55, 2.1 / max(a, b)) if compact else bacterial_scale(bacterium)
    viral = viral_stage(bacterium.infection.age) if bacterium.infection is not None else None
    lysis = viral is not None and viral[0] == "lysis" and not compact

    def point(along: float, across: float) -> tuple[float, float]:
        return (
            bacterium.x + (ux * along - uy * across) * scale,
            bacterium.y + (uy * along + ux * across) * scale,
        )

    if bacterium.infection is not None:
        tail *= 1 - smooth(bacterium.infection.age / 7)
    if bacterium.kind in ("rod", "spiral", "vibrio", "trypanosome") and not compact and tail > 0.02:
        # A traveling wave implies flagellar propulsion. Clip the flexible tail
        # at obstacles; the body uses the larger physical collision clearance.
        previous = None
        for index in range(33):
            t = index / 32
            wave = math.sin(t * TAU * 1.4 - now * 7 + bacterium.id) * 1.1 * t
            x, y = point(-a - 0.3 - t * 6 * tail, wave * tail)
            if world and next(world._obstacles(x, y, 1.1), None) is not None:
                break
            if previous is not None:
                frame.line(*previous, x, y, ink, unicode)
            previous = x, y

    if bacterium.infection is None and draw_special_microbe(
        frame, bacterium, unicode, now, point, compact
    ):
        if bacterium.fed_until > now:
            frame.point(bacterium.x, bacterium.y, "*", Ink.MICROBIAL_DNA, True)
        return
    if bacterium.kind == "spiral" and bacterium.infection is None:
        previous = None
        for index in range(33):
            along = -2.9 + index / 32 * 5.8
            x, y = point(along, math.sin(along * 2.1) * 1.2)
            if previous is not None:
                frame.line(*previous, x, y, ink, unicode)
            previous = x, y
    else:
        # A membrane around a visible nucleoid replaces the old one-glyph body.
        points = []
        for index in range(65):
            angle = index * TAU / 64
            x, y = point(math.cos(angle) * a, math.sin(angle) * b)
            points.append((x, y, angle + bacterium.angle))
        for col, row, angle in contour_pixels(points):
            if lysis and int((angle - bacterium.angle) / TAU * 64) % 7 < viral[1] * 6:
                continue
            frame.put(col, row, membrane_char(angle, unicode), Ink.LYSIS if lysis else ink, True)
    frame.point(
        bacterium.x,
        bacterium.y,
        "~" if bacterium.kind == "rod" else "·" if unicode else ".",
        Ink.MICROBIAL_DNA,
    )
    if bacterium.infection is not None and not compact:
        draw_infection(frame, bacterium, unicode, point)
    elif bacterium.fed_until > now:
        frame.point(bacterium.x, bacterium.y, "*", Ink.MICROBIAL_DNA, True)


def overlay(frame: Frame, lines: list[str], inks: list[Ink] | None = None) -> None:
    width = min(frame.width - 2, max(map(len, lines)) + 4)
    height = min(frame.height, len(lines) + 2)
    left, top = (frame.width - width) // 2, (frame.height - height) // 2
    for row in range(top, top + height):
        for col in range(left, left + width):
            frame.put(col, row, " ", Ink.TEXT, bg=None)
    for index, line in enumerate(lines[: height - 2]):
        frame.text(
            left + 2,
            top + 1 + index,
            line[: max(0, width - 4)],
            inks[index] if inks else Ink.MEMBRANE if index == 0 else Ink.TEXT,
            index == 0,
        )


LEGEND = [
    ("Macrophage: mint membrane", Ink.MEMBRANE),
    ("Neutrophil: pale blue, lobed nucleus", Ink.NEUTROPHIL),
    ("Red blood cell: red disc", Ink.RED),
    ("Rod bacterium: gold", Ink.BACTERIA),
    ("Coccus: sky blue", Ink.COCCUS),
    ("Short spiral: pink", Ink.SPIRAL),
    ("Bacillary chain: orange", Ink.BACILLUS),
    ("Spirochete: vivid purple corkscrew", Ink.SPIROCHETE),
    ("Vibrio: turquoise comma", Ink.VIBRIO),
    ("Coccal colony: royal blue cluster", Ink.COLONY),
    ("Yeast: tan, budding oval", Ink.YEAST),
    ("Trypanosome: ivory, tapered swimmer", Ink.TRYPANOSOME),
    ("Fungus: olive branching filament", Ink.FUNGUS),
    ("Phage: lime fork", Ink.PHAGE),
    ("Food cloud: muted green dots", Ink.NUTRIENT),
    ("Rotifer: coral body, beating wheels", Ink.ROTIFER),
    ("DNA trap: pale lilac web", Ink.NET),
    ("Micropipette: gray glass outline", Ink.GLASS),
    ("Nucleus: violet envelope", Ink.NUCLEUS),
    ("Chromosomes: lilac", Ink.DNA),
    ("Nucleolus: pale nuclear dot", Ink.NUCLEOLUS),
    ("Mitochondria: salmon tubules", Ink.MITOCHONDRION),
    ("Endoplasmic reticulum: teal folds", Ink.RETICULUM),
    ("Digestive vesicles: subdued green", Ink.VESICLE),
    ("Microbial nucleoid: pale DNA", Ink.MICROBIAL_DNA),
    ("Viral genome: green pulse", Ink.VIRAL_DNA),
    ("Spindle fibers: blue", Ink.SPINDLE),
    ("Capture flash / lysis: white", Ink.CAPTURE),
]
HELP_INKS = dict(LEGEND)
GENERAL_HELP = [
    "cells / a living microscope slide",
    "",
    "q / Esc    quit",
    "Space      pause / resume",
    "+ / -      speed up / slow down",
    "r          new slide",
    "s          show / hide observations",
    "?          close this help",
    "",
]

INTERACTIVE_HELP = [
    "Microscope tools",
    "",
    "1              Inspect / select and follow a body",
    "2              Lyse / rupture a cell",
    "3              Feed / add nutrients",
    "4              Stir / create a local current",
    "",
    "Left click     aim and apply the selected tool",
    "Arrows / hjkl  move the reticle",
    "Tab            select the next entity",
    "Enter          apply at the reticle or selection",
    "",
    "Tools apply immediately, including while paused.",
    "",
]


def help_lines(interactive: bool = False) -> list[str]:
    return (
        GENERAL_HELP
        + (INTERACTIVE_HELP if interactive else [])
        + [
            "Species colors use your selected palette.",
            "Shapes identify species in limited-color modes.",
            "",
        ]
        + [label for label, _ in LEGEND]
    )


HELP = help_lines()
