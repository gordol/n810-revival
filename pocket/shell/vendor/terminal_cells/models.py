"""Simulation data and geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


TAU = math.tau


STEP = 1 / 30


ASPECT = 2.0  # Terminal characters are approximately twice as tall as they are wide.


DIVISION_STAGES = (
    ("prophase", 6.0),
    ("envelope breakdown", 6.0),
    ("spindle formation", 7.0),
    ("metaphase", 7.0),
    ("anaphase", 7.0),
    ("telophase", 7.0),
    ("cytokinesis", 10.0),
)


DIVISION_TIME = sum(duration for _, duration in DIVISION_STAGES)


ENCLOSE_TIME = 10.0


SEAL_TIME = 7.0


VESICLE_TIME = 14.0


CELL_RADIUS = 16.5


NEUTROPHIL_RADIUS = 14.0


BACTERIUM_PADDING = 4.5  # Body + one glyph of clearance; flagella bend at obstacles.


DEBRIS_PADDING = 2.0


PHAGE_PADDING = 1.5  # One terminal row or two columns, including raster rounding.


PHAGE_CONTACT = 3.2 + PHAGE_PADDING  # Resting rod, approached along its long axis.


INFECTION_CHANCE = 0.45  # One roll per encounter, independent of frame rate.


MICROBE_KINDS = (
    "rod",
    "coccus",
    "spiral",
    "bacillus",
    "spirochete",
    "vibrio",
    "colony",
    "yeast",
    "trypanosome",
)


BACTERIAL_KINDS = frozenset(MICROBE_KINDS) - {"yeast", "trypanosome"}


VIRAL_STAGES = (
    ("attachment", 3.0),
    ("injection", 4.0),
    ("replication", 7.0),
    ("assembly", 7.0),
    ("lysis", 3.0),
)


VIRAL_TIME = sum(duration for _, duration in VIRAL_STAGES)


def viral_stage(elapsed: float) -> tuple[str, float]:
    for name, duration in VIRAL_STAGES:
        if elapsed < duration:
            return name, clamp(elapsed / duration, 0, 1)
        elapsed -= duration
    return "lysis", 1.0


def bacterial_scale(bacterium) -> float:
    return (
        1.0 if bacterium.infection is None else 1 + 0.65 * smooth(bacterium.infection.age / 21)
    ) * bacterium.swelling


def bacterial_padding(bacterium) -> float:
    return max(BACTERIUM_PADDING, max(microbe_axes(bacterium)) + 1.3) * bacterial_scale(bacterium)


def microbe_axes(microbe) -> tuple[float, float]:
    return {
        "rod": (3.2, 1.65),
        "coccus": (2.3, 2.3),
        "spiral": (3.2, 1.65),
        "bacillus": (2.4 + (microbe.units - 1) * 1.7, 1.7),
        "spirochete": (7.0, 1.7),
        "vibrio": (3.3, 2.1),
        "colony": (3.2 + microbe.units * 0.35, 3.2 + microbe.units * 0.35),
        "yeast": (3.3 + microbe.bud * 3.5, 2.7),
        "trypanosome": (7.0, 2.4),
    }[microbe.kind]


def disc_axes(disc) -> tuple[float, float]:
    return disc.size, disc.size * 0.8


def nucleus_radii(radius: float) -> tuple[float, float]:
    rx = clamp(radius * 0.29, 1.5, 5.5)
    return rx, rx * 1.2


def division_stage(elapsed: float) -> tuple[str, float]:
    for name, duration in DIVISION_STAGES:
        if elapsed < duration:
            return name, clamp(elapsed / duration, 0, 1)
        elapsed -= duration
    return "cytokinesis", 1.0


def smooth(value: float) -> float:
    value = clamp(value, 0, 1)
    return value * value * (3 - 2 * value)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def angle_delta(a: float, b: float) -> float:
    return (a - b + math.pi) % TAU - math.pi


class State(Enum):
    WANDER = "wander"
    APPROACH = "approach"
    ENCLOSE = "enclose"
    DIGEST = "digest"
    DIVIDE = "divide"


@dataclass
class Infection:
    age: float = 0.0
    angle: float = 0.0  # Attachment direction relative to the host's heading.


@dataclass
class Entry:
    angle: float
    remaining: float
    target_x: float
    target_y: float


@dataclass
class Bacterium:
    id: int
    x: float
    y: float
    angle: float
    speed: float
    kind: str
    turn_at: float
    divide_at: float
    owner: int | None = None
    infection: Infection | None = None
    units: int = 3
    bud: float = 0.0
    escape_until: float = 0.0
    escape_ready: float = 0.0
    fed_until: float = 0.0
    rail: int | None = None
    rail_from: int = 0
    rail_to: int = 0
    rail_until: float = 0.0
    rail_ready: float = 0.0
    swelling: float = 1.0
    leaving: bool = False
    entry: Entry | None = None


@dataclass
class Nutrient:
    x: float
    y: float
    amount: float = 4.0
    age: float = 0.0
    lifetime: float = 40.0

    @property
    def radius(self) -> float:
        return 4 + min(6, self.age * 0.22)


@dataclass
class Hypha:
    nodes: list[tuple[float, float]]
    edges: list[tuple[int, int]]
    tips: list[tuple[int, float]]
    grow_at: float


@dataclass
class Phage:
    id: int
    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0
    flight: float = 0.0
    age: float = 0.0
    lifetime: float = math.inf
    contacts: set[int] = field(default_factory=set)
    angle: float = math.pi / 2  # Head-to-tail direction; free particles remain still.
    entry: Entry | None = None


@dataclass
class Burst:
    x: float
    y: float
    angle: float = 0.0
    age: float = 0.0


@dataclass
class Vesicle:
    angle: float
    distance: float
    age: float = 0.0
    kind: str = "rod"


@dataclass
class OrganelleNetwork:
    kind: str
    nodes: list[tuple[float, float]]  # Coordinates in units of the cell radius.
    edges: list[tuple[int, int]]
    tags: list[int]  # Material identity survives remodeling and cell division.
    phase: float = 0.0

    def fragments(self, selected: set[int]) -> list[OrganelleNetwork]:
        result = []
        adjacency = {index: set() for index in selected}
        for a, b in self.edges:
            if a in selected and b in selected:
                adjacency[a].add(b)
                adjacency[b].add(a)
        remaining = set(selected)
        while remaining:
            stack, group = [min(remaining)], set()
            while stack:
                index = stack.pop()
                if index in group:
                    continue
                group.add(index)
                stack.extend(adjacency[index] - group)
            remaining -= group
            indices = sorted(group)
            remap = {old: new for new, old in enumerate(indices)}
            result.append(
                OrganelleNetwork(
                    self.kind,
                    [self.nodes[i] for i in indices],
                    [(remap[a], remap[b]) for a, b in self.edges if a in group and b in group],
                    [self.tags[i] for i in indices],
                    self.phase,
                )
            )
        return result


def initial_organelles(ident: int, phase: float) -> list[OrganelleNetwork]:
    result = []

    def rotate(x, y):
        return x * math.cos(phase) - y * math.sin(phase), x * math.sin(phase) + y * math.cos(phase)

    for index, angle in enumerate((-0.55, 0.25, math.pi + 0.25)):
        cx, cy = math.cos(angle) * 0.68, math.sin(angle) * 0.68
        nodes = [rotate(cx + (i - 2) * 0.065, cy + math.sin(i * 0.9) * 0.065) for i in range(5)]
        nodes += [rotate(cx + 0.015, cy - 0.11), rotate(cx + 0.09, cy - 0.15)]
        result.append(
            OrganelleNetwork(
                "mitochondrion",
                nodes,
                [(0, 1), (1, 2), (2, 3), (3, 4), (2, 5), (5, 6)],
                [ident * 10000 + index * 100 + i for i in range(7)],
                phase + index,
            )
        )
    nodes = []
    for radius in (0.40, 0.50):
        for index in range(12):
            angle = 0.35 + index * (TAU - 0.7) / 11
            nodes.append(rotate(-0.22 + math.cos(angle) * radius, math.sin(angle) * radius))
    edges = [(i, i + 1) for i in range(11)] + [(i, i + 1) for i in range(12, 23)]
    edges += [(i, i + 12) for i in (0, 4, 8, 11)]
    result.append(
        OrganelleNetwork(
            "reticulum", nodes, edges, [ident * 10000 + 300 + i for i in range(24)], phase
        )
    )
    for index, angle in enumerate((0.95, 4.0)):
        result.append(
            OrganelleNetwork(
                "lysosome",
                [rotate(math.cos(angle) * 0.55, math.sin(angle) * 0.55)],
                [],
                [ident * 10000 + 400 + index],
                phase + index,
            )
        )
    return result


@dataclass
class Cell:
    id: int
    x: float
    y: float
    radius: float
    phase: float
    heading: float
    state: State = State.WANDER
    elapsed: float = 0.0
    target: int | None = None
    reach_angle: float = 0.0
    reach: float = 0.0
    cooldown: float = 0.0
    vesicles: list[Vesicle] = field(default_factory=list)
    divide_at: float = math.inf
    division_angle: float = 0.0
    adult_radius: float | None = None
    capture_distance: float = 0.0
    capture_start: float = 0.0
    capture_axis: float = 0.0
    capture_a: float = 3.2
    capture_b: float = 1.65
    organelles: list[OrganelleNetwork] | None = None
    remodel_at: float = 18.0
    fuse_next: bool = True
    kind: str = "macrophage"
    entry: Entry | None = None

    def __post_init__(self):
        if self.organelles is None:
            self.organelles = initial_organelles(self.id, self.phase)

    def capture_center(self) -> tuple[float, float]:
        transport = smooth((self.elapsed - SEAL_TIME) / (ENCLOSE_TIME - SEAL_TIME))
        distance = self.capture_distance * (1 - transport) + self.radius * 0.45 * transport
        return self.x + math.cos(self.reach_angle) * distance, self.y + math.sin(
            self.reach_angle
        ) * distance

    def extent(self) -> float:
        extent = self.radius * 1.6 + self.reach * 2 + 1
        if self.state is State.ENCLOSE:
            extent = max(extent, self.capture_distance + max(self.capture_a, self.capture_b) + 2)
        return extent

    def outline(self, angle: float, now: float) -> float:
        """Shared collision/fill envelope, including the compact capture pocket."""
        radius = self.body_outline(angle, now)
        if self.state is not State.ENCLOSE or self.elapsed < 0.05:
            return radius
        x, y = self.capture_center()
        ca, sa = math.cos(self.capture_axis), math.sin(self.capture_axis)
        cx, cy = x - self.x, y - self.y
        local_x, local_y = cx * ca + cy * sa, -cx * sa + cy * ca
        ux, uy = math.cos(angle - self.capture_axis), math.sin(angle - self.capture_axis)
        a, b = self.capture_a + 1.2, self.capture_b + 1.3
        aa = (ux / a) ** 2 + (uy / b) ** 2
        bb = -2 * (ux * local_x / a**2 + uy * local_y / b**2)
        cc = (local_x / a) ** 2 + (local_y / b) ** 2 - 1
        discriminant = bb * bb - 4 * aa * cc
        if discriminant >= 0:
            far = (-bb + math.sqrt(discriminant)) / (2 * aa)
            radius = max(radius, far)
        return radius

    def body_outline(self, angle: float, now: float) -> float:
        """Persistent lobes, a broad leading edge, a trailing tip, and local ruffles."""
        wave = 0.065 * math.sin(3 * angle + self.phase) + 0.035 * math.sin(
            5 * angle - self.phase * 0.7
        )
        front = math.exp(-((angle_delta(angle, self.heading) / 0.72) ** 2))
        tail = math.exp(-((angle_delta(angle, self.heading + math.pi) / 0.30) ** 2))
        protrusion = math.exp(-((angle_delta(angle, self.phase + 1.1) / 0.24) ** 2))
        ruffle = 0.025 * math.sin(11 * angle - now * 0.85 + self.phase) * (0.25 + front)
        radius = self.radius * (1 + wave + 0.12 * front + 0.11 * tail + 0.08 * protrusion + ruffle)
        if self.state is State.DIVIDE:
            # The union of two overlapping lobes stays continuous as the waist
            # narrows. Daughter area approaches half the original cell's area.
            progress = 0.15 * smooth(self.elapsed / 26) + 0.85 * smooth(
                (self.elapsed - 26) / (DIVISION_TIME - 26)
            )
            delta = angle - self.division_angle
            lobe = self.radius * (1 - 0.28 * progress)
            offset = self.radius * 0.715 * progress
            radius = abs(offset * math.cos(delta)) + math.sqrt(
                max(0, lobe * lobe - (offset * math.sin(delta)) ** 2)
            )
            return radius * (1 + wave * (1 - progress) * 0.5)
        if self.reach and self.state is State.APPROACH:
            delta = angle_delta(angle, self.reach_angle)
            radius += self.reach * math.exp(-((delta / 0.65) ** 2))
        return radius


@dataclass
class Drifter:
    x: float
    y: float
    phase: float
    size: float
    entry: Entry | None = None


def attachment_pose(bacterium: Bacterium) -> tuple[float, float, float]:
    """Surface anchor and inward normal, rotating and swelling with the host."""
    assert bacterium.infection is not None
    angle = bacterium.infection.angle
    a, b = microbe_axes(bacterium)
    a, b = a * bacterial_scale(bacterium), b * bacterial_scale(bacterium)
    dx, dy = math.cos(angle), math.sin(angle)
    distance = 1 / math.hypot(dx / a, dy / b)
    x, y = dx * distance, dy * distance
    ux, uy = math.cos(bacterium.angle), math.sin(bacterium.angle)
    normal = math.atan2(y / b**2, x / a**2) + bacterium.angle
    return (bacterium.x + ux * x - uy * y, bacterium.y + uy * x + ux * y, normal + math.pi)


def phage_geometry(
    phage: Phage, contraction: float = 0
) -> tuple[tuple[float, float], tuple[float, float]]:
    ux, uy = math.cos(phage.angle), math.sin(phage.angle)
    offset = 0.5 - 0.2 * contraction
    tip = phage.x + ux * offset, phage.y + uy * offset
    length = 2 * offset
    head = tip[0] - ux * length, tip[1] - uy * length
    return head, tip


def phage_contact_distance(bacterium: Bacterium, angle: float) -> float:
    """Host envelope toward a compact phage, plus its small raster footprint."""
    a, b = microbe_axes(bacterium)
    relative = angle - bacterium.angle
    radius = 1 / math.hypot(math.cos(relative) / a, math.sin(relative) / b)
    return radius * bacterial_scale(bacterium) + PHAGE_PADDING
