"""Seeded microscopic ecosystem simulation."""

from __future__ import annotations

import math
import random
from .events import EventDirector
from .lab import Laboratory
from .models import (
    ASPECT,
    BACTERIAL_KINDS,
    Bacterium,
    Burst,
    CELL_RADIUS,
    Cell,
    DEBRIS_PADDING,
    DIVISION_TIME,
    Drifter,
    ENCLOSE_TIME,
    Entry,
    Hypha,
    INFECTION_CHANCE,
    Infection,
    MICROBE_KINDS,
    Nutrient,
    NEUTROPHIL_RADIUS,
    OrganelleNetwork,
    PHAGE_PADDING,
    Phage,
    SEAL_TIME,
    STEP,
    State,
    TAU,
    VESICLE_TIME,
    VIRAL_TIME,
    Vesicle,
    angle_delta,
    attachment_pose,
    bacterial_padding,
    bacterial_scale,
    clamp,
    disc_axes,
    microbe_axes,
    phage_contact_distance,
    smooth,
)


class World:
    """Continuous, seeded simulation; independent of curses and rendering."""

    def __init__(
        self,
        columns: int,
        rows: int,
        seed: int,
        density: float = 1.0,
        *,
        scene: str = "mixed",
        rare_events: bool = True,
        microscope_events: bool = True,
    ):
        if scene not in ("mixed", "blood", "microbial"):
            raise ValueError("unknown scene")
        self.events = EventDirector(seed, rare_events, microscope_events)
        self.lab = Laboratory()
        self.scene = scene
        self.rng = random.Random(seed)
        self.seed = seed
        self.density = density
        self.width = float(max(1, columns))
        self.height = float(max(1, rows)) * ASPECT
        self.time = 0.0
        self.next_id = 0
        self.engulfed = 0
        self.divisions = 0
        self.next_cell_id = 0
        self.next_phage_id = 0
        self.infections = 0
        self.lysed = 0
        self.cells: list[Cell] = []
        self.bacteria: dict[int, Bacterium] = {}
        self.phages: dict[int, Phage] = {}
        self.spent_capsids: list[Phage] = []
        self.bursts: list[Burst] = []
        self.red_cells: list[Drifter] = []
        self.debris: list[Drifter] = []
        self.hyphae: list[Hypha] = []
        self.nutrients: list[Nutrient] = []
        self.nutrient_at = 12.0
        self.fungal_arrival_at = 50.0
        self.large_arrival_at = 100.0
        self.last_seen = dict.fromkeys(MICROBE_KINDS, 0.0)
        self.arrivals = 0
        # Draw a new community profile per slide; children retain their type.
        self.microbe_weights = [self.rng.gammavariate(0.8, 1) + 0.08 for _ in MICROBE_KINDS]
        if scene == "blood":
            multipliers = (2, 3, 0.3, 0.5, 0.2, 0.3, 0.5, 1, 2)
            self.microbe_weights = [w * m for w, m in zip(self.microbe_weights, multipliers)]
        self.neutrophil_fraction = self.rng.uniform(0.15, 0.65)
        self.replenish_at = 6.0
        self._populate()
        for _ in range(self.rng.randint(1, min(3, self._phage_limit()))):
            self._seed_phage()
        self.phage_replenish_at = 45.0

    def _limits(self) -> tuple[int, int, int, int]:
        area = self.width * self.height
        return (
            0
            if self.scene == "microbial"
            else max(1 if area < 3000 else 2, min(8, round(area / 12500 * self.density))),
            max(4, min(90, round(area / 1100 * self.density))),
            0 if self.scene == "microbial" else max(1, min(12, round(area / 4500 * self.density))),
            max(5, min(100, round(area / 500 * self.density))),
        )

    def _populate(self) -> None:
        cell_limit, bacteria_count, red_count, debris_count = self._limits()
        cell_count = min(cell_limit, 2, max(1, math.ceil(cell_limit / 3)))
        for index in range(cell_count):
            self._add_cell(index, cell_count)
        for _ in range(max(4, round(bacteria_count * self.rng.uniform(0.65, 1)))):
            self._add_bacterium()
        # Put one microbe in the path of each macrophage: the first encounter
        # should not require watching an empty slide for a minute.
        for cell, bacterium in zip(self.cells, self.bacteria.values()):
            angle = self.rng.uniform(0, TAU)
            bacterium.x = clamp(cell.x + math.cos(angle) * (cell.radius + 4), 1, self.width - 1)
            bacterium.y = clamp(cell.y + math.sin(angle) * (cell.radius + 4), 1, self.height - 1)
        for _ in range(min(red_count, max(1, round(red_count * self.rng.uniform(0.35, 1))))):
            self.red_cells.append(self._drifter(self.rng.uniform(4.3, 5.5)))
        for _ in range(max(5, round(debris_count * self.rng.uniform(0.4, 1)))):
            self.debris.append(self._drifter(self.rng.uniform(0.5, 1.3)))
        for _ in range(self.rng.randint(0, self._hypha_limit())):
            self._add_hypha()
        self._resolve_obstacles()

    def _add_cell(self, index: int, count: int, kind: str | None = None) -> None:
        kind = kind or (
            "neutrophil" if self.rng.random() < self.neutrophil_fraction else "macrophage"
        )
        base_radius = NEUTROPHIL_RADIUS if kind == "neutrophil" else CELL_RADIUS
        radius = min(
            self.rng.uniform(base_radius - 1, base_radius + 1),
            self.width * 0.18,
            self.height * 0.25,
        )
        margin = radius + 1
        x = self.width * (index + 0.6) / (count + 0.2)
        y = self.height * self.rng.uniform(0.3, 0.7)
        self.cells.append(
            Cell(
                self.next_cell_id,
                clamp(x, margin, self.width - margin),
                clamp(y, margin, self.height - margin),
                radius,
                self.rng.uniform(0, TAU),
                self.rng.uniform(0, TAU),
                cooldown=self.rng.uniform(0.5, 2.0),
                divide_at=self.time + self.rng.uniform(18, 26) + index * 8,
                adult_radius=radius,
                kind=kind,
            )
        )
        if kind == "neutrophil":
            self.cells[-1].divide_at = math.inf
        self.next_cell_id += 1

    def _drifter(self, size: float) -> Drifter:
        return Drifter(
            self.rng.uniform(0, self.width),
            self.rng.uniform(0, self.height),
            self.rng.uniform(0, TAU),
            size,
        )

    def _add_bacterium(
        self, parent: Bacterium | None = None, kind: str | None = None, arrival: bool = False
    ) -> None:
        ident = self.next_id
        self.next_id += 1
        if parent:
            x = (parent.x + math.cos(parent.angle + math.pi / 2) * 1.5) % self.width
            y = (parent.y + math.sin(parent.angle + math.pi / 2) * 1.5) % self.height
            kind = parent.kind
        else:
            x, y = self.rng.uniform(0, self.width), self.rng.uniform(0, self.height)
            kind = kind or self.rng.choices(MICROBE_KINDS, weights=self.microbe_weights)[0]
            # Free microbes should begin outside a macrophage's body.
            for _ in range(20):
                if all(math.hypot(x - c.x, y - c.y) > c.radius + 2 for c in self.cells):
                    break
                x, y = self.rng.uniform(0, self.width), self.rng.uniform(0, self.height)
        self.bacteria[ident] = Bacterium(
            ident,
            x,
            y,
            self.rng.uniform(0, TAU),
            self.rng.uniform(0.8, 2.0),
            kind,
            self.time + self.rng.uniform(1, 4),
            self.time + self.rng.uniform(25, 65),
        )
        child = self.bacteria[ident]
        if parent:
            child.angle = parent.angle
        if kind == "yeast":
            child.speed = 0
        elif kind == "trypanosome":
            child.speed *= 1.5
        elif kind == "vibrio":
            child.speed *= 1.8
        if arrival:
            self._begin_entry(child)
        else:
            self._exclude(child, bacterial_padding(child))

    def _edge_position(self, margin: float = 1) -> tuple[float, float, float]:
        side = self.rng.randrange(4)
        x, y = self.rng.uniform(0, self.width), self.rng.uniform(0, self.height)
        margin = min(margin, self.width / 3, self.height / 3)
        if side == 0:
            return margin, y, 0.0
        if side == 1:
            return self.width - margin, y, math.pi
        if side == 2:
            return x, margin, math.pi / 2
        return x, self.height - margin, -math.pi / 2

    def _entry_padding(self, obj) -> float:
        if isinstance(obj, Bacterium):
            return bacterial_padding(obj)
        if isinstance(obj, Cell):
            return obj.radius * 1.3 + 1
        return PHAGE_PADDING if isinstance(obj, Phage) else obj.size + 1

    def _begin_entry(self, obj) -> None:
        """Choose a clear crossing with the entire sprite initially offscreen."""
        padding = self._entry_padding(obj)
        footprint = self._entry_extent(obj)
        exempt = obj.id if isinstance(obj, Cell) else None
        for _ in range(32):
            tx, ty, angle = self._edge_position(footprint + 1)
            tx = clamp(
                tx,
                min(footprint + 1, self.width / 2),
                max(self.width / 2, self.width - footprint - 1),
            )
            ty = clamp(
                ty,
                min(footprint + 1, self.height / 2),
                max(self.height / 2, self.height - footprint - 1),
            )
            ux, uy = round(math.cos(angle)), round(math.sin(angle))
            x = -footprint - 2 if ux > 0 else self.width + footprint + 2 if ux < 0 else tx
            y = -footprint - 2 if uy > 0 else self.height + footprint + 2 if uy < 0 else ty
            remaining = math.hypot(tx - x, ty - y)
            samples = max(1, math.ceil(remaining / 2))
            if all(
                next(
                    self._obstacles(
                        x + ux * remaining * i / samples,
                        y + uy * remaining * i / samples,
                        padding,
                        exempt,
                        red=not isinstance(obj, Drifter),
                    ),
                    None,
                )
                is None
                for i in range(samples + 1)
            ):
                break
        obj.x, obj.y = x, y
        obj.entry = Entry(angle, remaining, tx, ty)
        if isinstance(obj, Cell):
            obj.heading = angle
        elif isinstance(obj, (Bacterium, Phage)):
            obj.angle = angle

    def _entry_extent(self, obj) -> float:
        footprint = self._entry_padding(obj) + 2
        if isinstance(obj, Bacterium) and obj.kind in ("rod", "spiral", "vibrio", "trypanosome"):
            footprint = max(footprint, microbe_axes(obj)[0] + 8)
        return footprint

    def _advance_entry(self, obj, dt: float) -> None:
        entry = obj.entry
        speed = (
            max(1.8, obj.speed)
            if isinstance(obj, Bacterium)
            else 2.6
            if isinstance(obj, Cell)
            else 2
        )
        distance = min(entry.remaining, speed * dt)
        steps = max(1, math.ceil(distance / 0.5))
        ux = (entry.target_x - obj.x) / max(entry.remaining, 1e-9)
        uy = (entry.target_y - obj.y) / max(entry.remaining, 1e-9)
        exempt = obj.id if isinstance(obj, Cell) else None
        for _ in range(steps):
            step = distance / steps
            x, y = obj.x + ux * step, obj.y + uy * step
            if (
                next(
                    self._obstacles(
                        x, y, self._entry_padding(obj), exempt, red=not isinstance(obj, Drifter)
                    ),
                    None,
                )
                is not None
            ):
                return  # Wait at a blocked entrance instead of being teleported.
            obj.x, obj.y = x, y
            entry.remaining = max(0, entry.remaining - step)
        if entry.remaining < 1e-7:
            obj.entry = None
            if isinstance(obj, Bacterium):
                obj.turn_at = self.time + self.rng.uniform(1, 3)
            elif isinstance(obj, Cell):
                obj.cooldown = 1
                if obj.kind == "macrophage":
                    obj.divide_at = self.time + self.rng.uniform(18, 26)

    def _add_nutrient(self, x: float, y: float, amount: float = 4) -> None:
        if len(self.nutrients) >= 4:
            self.nutrients.remove(min(self.nutrients, key=lambda p: p.amount))
        self.nutrients.append(Nutrient(x, y, amount))

    def _update_nutrients(self, dt: float) -> None:
        for patch in self.nutrients:
            patch.age += dt
            patch.amount *= math.exp(-dt * 0.012)
            vx, vy = self.current(patch.x, patch.y)
            patch.x = (patch.x + vx * dt * 0.3) % self.width
            patch.y = (patch.y + vy * dt * 0.3) % self.height
        self.nutrients = [p for p in self.nutrients if p.age < p.lifetime and p.amount > 0.1]
        if self.time >= self.nutrient_at:
            particle = self._drifter(1)
            self._exclude(particle, 3)
            self._add_nutrient(particle.x, particle.y)
            self.nutrient_at = self.time + self.rng.uniform(18, 30)

    def _update_arrivals(self) -> None:
        counts = {kind: 0 for kind in MICROBE_KINDS}
        for microbe in self.bacteria.values():
            if not microbe.leaving:
                counts[microbe.kind] += 1
                self.last_seen[microbe.kind] = self.time
        if self.time < self.replenish_at:
            return
        target = self._limits()[1]
        missing = [
            k for k in MICROBE_KINDS if not counts[k] and self.time - self.last_seen[k] >= 35
        ]
        if len(self.bacteria) < target or missing:
            choices = missing or list(MICROBE_KINDS)
            weights = [self.microbe_weights[MICROBE_KINDS.index(k)] for k in choices]
            if len(self.bacteria) < target * 2:
                self._add_bacterium(
                    kind=self.rng.choices(choices, weights=weights)[0], arrival=True
                )
                self.arrivals += 1
            elif missing and not any(b.leaving for b in self.bacteria.values()):
                # Make space gradually: an abundant free swimmer leaves through
                # an edge instead of vanishing to make room for a new species.
                candidates = [
                    b
                    for b in self.bacteria.values()
                    if b.owner is None
                    and b.infection is None
                    and b.entry is None
                    and counts[b.kind] > 2
                ]
                if candidates:
                    leaver = max(
                        candidates,
                        key=lambda b: (
                            counts[b.kind],
                            -min(b.x, self.width - b.x, b.y, self.height - b.y),
                        ),
                    )
                    leaver.leaving = True
                    leaver.rail = None
        self.replenish_at = self.time + self.rng.uniform(4, 9)
        if self.time >= self.fungal_arrival_at:
            if len(self.hyphae) < self._hypha_limit():
                x, y, _ = self._edge_position(3)
                before = len(self.hyphae)
                self._add_hypha((x, y))
                self.arrivals += len(self.hyphae) - before
            self.fungal_arrival_at = self.time + self.rng.uniform(45, 85)
        if self.time >= self.large_arrival_at:
            cell_limit, _, red_limit, _ = self._limits()
            reserved = len(self.cells) + sum(c.state is State.DIVIDE for c in self.cells)
            if reserved < cell_limit:
                missing_immune = [
                    k for k in ("macrophage", "neutrophil") if all(c.kind != k for c in self.cells)
                ]
                kind = self.rng.choice(missing_immune) if missing_immune else None
                self._add_cell(0, 1, kind)
                cell = self.cells[-1]
                self._begin_entry(cell)
                self.arrivals += 1
            if len(self.red_cells) < red_limit:
                red = self._drifter(self.rng.uniform(4.3, 5.5))
                self._begin_entry(red)
                self.red_cells.append(red)
                self.arrivals += 1
            self.large_arrival_at = self.time + self.rng.uniform(80, 140)

    def _hypha_limit(self) -> int:
        if self.scene == "blood":
            return 0
        return max(1, min(3, round(self.width * self.height * self.density / 10000)))

    def _add_hypha(self, origin: tuple[float, float] | None = None) -> None:
        if len(self.hyphae) >= self._hypha_limit():
            return
        for _ in range(30):
            x, y = origin or (
                self.rng.uniform(2, max(2, self.width - 2)),
                self.rng.uniform(2, max(2, self.height - 2)),
            )
            if next(self._obstacles(x, y, 3), None) is None:
                self.hyphae.append(
                    Hypha([(x, y)], [], [(0, self.rng.uniform(0, TAU))], self.time + 2)
                )
                return
            if origin:
                return

    def _update_hyphae(self) -> None:
        for hypha in list(self.hyphae):
            if self.time < hypha.grow_at:
                continue
            hypha.grow_at = self.time + self.rng.uniform(3, 5)
            if len(hypha.nodes) >= 48:
                if self.rng.random() < 0.1:
                    self._add_hypha(hypha.nodes[-1])
                continue
            tips = []
            for node, heading in hypha.tips:
                heading += self.rng.uniform(-0.3, 0.3)
                x, y = hypha.nodes[node]
                xx, yy = x + math.cos(heading) * 3, y + math.sin(heading) * 3
                clear = (
                    1 < xx < self.width - 1
                    and 1 < yy < self.height - 1
                    and all(
                        next(self._obstacles(x + (xx - x) * t, y + (yy - y) * t, 1.3), None) is None
                        for t in (0.25, 0.5, 0.75, 1)
                    )
                )
                if clear and len(hypha.nodes) < 48:
                    new = len(hypha.nodes)
                    hypha.nodes.append((xx, yy))
                    hypha.edges.append((node, new))
                    tips.append((new, heading))
                    if len(tips) < 4 and self.rng.random() < 0.22:
                        tips.append((new, heading + self.rng.choice((-1, 1)) * 0.8))
                else:
                    tips.append((node, heading + 0.8))
            hypha.tips = tips[:4]

    def resize(self, columns: int, rows: int) -> None:
        width, height = float(max(1, columns)), float(max(1, rows)) * ASPECT
        sx, sy = width / self.width, height / self.height
        self.width, self.height = width, height
        self.events.resize(sx, sy)
        for obj in [
            *self.cells,
            *self.bacteria.values(),
            *self.red_cells,
            *self.debris,
            *self.phages.values(),
            *self.spent_capsids,
            *self.bursts,
            *self.nutrients,
        ]:
            obj.x *= sx
            obj.y *= sy
        for hypha in self.hyphae:
            hypha.nodes = [(x * sx, y * sy) for x, y in hypha.nodes]
        self.hyphae = self.hyphae[: self._hypha_limit()]
        for phage in self.phages.values():
            phage.vx *= sx
            phage.vy *= sy
        while len(self.phages) > self._phage_limit():
            del self.phages[next(reversed(self.phages))]
        for cell in self.cells:
            maturity = cell.radius / (cell.adult_radius or cell.radius)
            base_radius = NEUTROPHIL_RADIUS if cell.kind == "neutrophil" else CELL_RADIUS
            cell.adult_radius = min(base_radius, width * 0.18, height * 0.25)
            cell.radius = cell.adult_radius * maturity
            cell.reach = 0
        # Keep references valid, including when a captured microbe is removed.
        cell_count, bacteria_count, red_count, debris_count = self._limits()
        removed = {cell.id for cell in self.cells[cell_count:]}
        for bacterium in self.bacteria.values():
            if bacterium.owner in removed:
                bacterium.owner = None
        self.cells = self.cells[:cell_count]
        # Growing the terminal creates room for division, rather than spawning
        # adult cells. Shrinking also cancels divisions that no longer fit.
        available = cell_count - len(self.cells)
        for cell in self.cells:
            if cell.state is State.DIVIDE:
                if available > 0:
                    available -= 1
                else:
                    self._release(cell)
                    cell.divide_at = self.time + self.rng.uniform(10, 20)
        if len(self.bacteria) > bacteria_count * 2:
            for ident in list(self.bacteria):
                if len(self.bacteria) <= bacteria_count * 2:
                    break
                if self.bacteria[ident].owner is None:
                    del self.bacteria[ident]
        self.red_cells = self.red_cells[:red_count]
        self.debris = self.debris[:debris_count]
        while len(self.red_cells) < red_count:
            self.red_cells.append(self._drifter(self.rng.uniform(4.3, 5.5)))
        while len(self.debris) < debris_count:
            self.debris.append(self._drifter(self.rng.uniform(0.5, 1.3)))
        for obj in [*self.cells, *self.bacteria.values(), *self.red_cells, *self.phages.values()]:
            if obj.entry is None:
                continue
            ux, uy = round(math.cos(obj.entry.angle)), round(math.sin(obj.entry.angle))
            margin = self._entry_extent(obj) + 1
            tx = min(margin, self.width / 2) if ux > 0 else max(self.width / 2, self.width - margin)
            ty = (
                min(margin, self.height / 2)
                if uy > 0
                else max(self.height / 2, self.height - margin)
            )
            if ux == 0:
                tx = clamp(
                    obj.x, min(margin, self.width / 2), max(self.width / 2, self.width - margin)
                )
            if uy == 0:
                ty = clamp(
                    obj.y, min(margin, self.height / 2), max(self.height / 2, self.height - margin)
                )
            obj.entry.target_x, obj.entry.target_y = tx, ty
            obj.entry.remaining = math.hypot(tx - obj.x, ty - obj.y)
        self.lab.resize(sx, sy)
        self._resolve_obstacles()

    def _obstacles(
        self,
        x: float,
        y: float,
        padding: float,
        exempt: int | None = None,
        red: bool = True,
        visitors: bool = True,
    ):
        """Yield penetration normals for the same outlines used by the renderer."""
        if visitors:
            yield from self.events.obstacle(x, y, padding)
        for cell in self.cells:
            if cell.id == exempt:
                continue
            dx, dy = x - cell.x, y - cell.y
            bound = cell.extent() + padding + 2
            if abs(dx) > bound or abs(dy) > bound:
                continue
            angle = math.atan2(dy, dx)
            boundary = cell.outline(angle, self.time) + padding
            distance = math.hypot(dx, dy)
            if distance < boundary:
                yield math.cos(angle), math.sin(angle), boundary - distance
        if red:
            for disc in self.red_cells:
                dx, dy = x - disc.x, y - disc.y
                a, b = disc_axes(disc)
                if abs(dx) > a + padding or abs(dy) > b + padding:
                    continue
                angle = math.atan2(dy, dx)
                boundary = a * b / math.hypot(b * math.cos(angle), a * math.sin(angle)) + padding
                distance = math.hypot(dx, dy)
                if distance < boundary:
                    yield math.cos(angle), math.sin(angle), boundary - distance

    def _exclude(self, obj, padding: float, exempt: int | None = None, red: bool = True) -> None:
        """Keep extracellular bodies outside membranes, including moving ones.

        A claimed microbe is still extracellular until its owner starts enclosing
        it. Only that owner's membrane may then be crossed during ingestion.
        """
        if getattr(obj, "entry", None) is not None:
            return  # Entry movement checks obstacles without projection or relocation.
        original = obj.x, obj.y
        for _ in range(8):
            hit = next(self._obstacles(obj.x, obj.y, padding, exempt, red), None)
            if hit is None:
                return
            nx, ny, depth = hit
            obj.x += nx * (depth + 0.12)
            obj.y += ny * (depth + 0.12)
            if isinstance(obj, Bacterium):
                vx, vy = math.cos(obj.angle), math.sin(obj.angle)
                inward = vx * nx + vy * ny
                if inward < 0:
                    obj.angle = math.atan2(vy - 2 * inward * ny, vx - 2 * inward * nx)
        # Overlapping membranes can otherwise trap a point between two pushes.
        # Search a local clear position deterministically rather than leaving it
        # inside a cell or erasing it behind the cell's interior.
        if next(self._obstacles(obj.x, obj.y, padding, exempt, red), None) is not None:
            for distance in (4, 8, 16, 32, 64):
                for index in range(24):
                    angle = index * TAU / 24
                    x = original[0] + math.cos(angle) * distance
                    y = original[1] + math.sin(angle) * distance
                    if next(self._obstacles(x, y, padding, exempt, red), None) is None:
                        obj.x, obj.y = x, y
                        return

    def _position_capture(self, cell: Cell, target: Bacterium) -> None:
        # Bring the target into close contact without moving it through the body.
        if cell.elapsed < SEAL_TIME and cell.capture_start > 0:
            delta = cell.reach_angle - cell.capture_axis
            support = math.hypot(cell.capture_a * math.cos(delta), cell.capture_b * math.sin(delta))
            contact = cell.body_outline(cell.reach_angle, self.time) + support + 0.8
            adhesion = smooth(cell.elapsed / 2.0)
            cell.capture_distance = cell.capture_start * (1 - adhesion) + contact * adhesion
        target.x, target.y = cell.capture_center()

    def _resolve_obstacles(self) -> None:
        for cell in self.cells:
            hit = next(self.events.obstacle(cell.x, cell.y, cell.extent()), None)
            if hit is not None:
                nx, ny, depth = hit
                cell.x += nx * (depth + 0.1)
                cell.y += ny * (depth + 0.1)
        for disc in self.red_cells:
            self._exclude(disc, disc.size + 1, red=False)
        for bacterium in self.bacteria.values():
            owner = next((c for c in self.cells if c.id == bacterium.owner), None)
            captured = owner is not None and owner.state is State.ENCLOSE
            if captured:
                self._position_capture(owner, bacterium)
            self._exclude(
                bacterium,
                bacterial_padding(bacterium),
                owner.id if captured else None,
                red=not captured,
            )
        for particle in self.debris:
            self._exclude(particle, DEBRIS_PADDING)
        for phage in self.phages.values():
            self._exclude(phage, PHAGE_PADDING)
        for capsid in self.spent_capsids:
            self._exclude(capsid, PHAGE_PADDING)

    def _phage_limit(self) -> int:
        return max(8, min(32, round(self.width * self.height / 1200 * self.density)))

    def _add_phage(
        self,
        x: float,
        y: float,
        vx: float = 0,
        vy: float = 0,
        flight: float = 0,
        lifetime: float = math.inf,
    ) -> Phage | None:
        if len(self.phages) >= self._phage_limit():
            return None
        phage = Phage(self.next_phage_id, x, y, vx, vy, flight, lifetime=lifetime)
        if vx or vy:
            phage.angle = math.atan2(vy, vx)
        self.next_phage_id += 1
        self._exclude(phage, PHAGE_PADDING)
        self.phages[phage.id] = phage
        return phage

    def _seed_phage(self, arrival: bool = False) -> None:
        if arrival:
            phage = self._add_phage(0, 0)
            if phage is not None:
                self._begin_entry(phage)
            return
        # Start near a swimming path, without forcing contact or infection.
        microbes = sorted(
            (b for b in self.bacteria.values() if b.kind in BACTERIAL_KINDS),
            reverse=True,
            key=lambda b: min((math.hypot(b.x - c.x, b.y - c.y) for c in self.cells), default=0),
        )
        for microbe in microbes:
            for ahead in (7.5, 6.5, 9.0):
                x = microbe.x + math.cos(microbe.angle) * ahead
                y = microbe.y + math.sin(microbe.angle) * ahead
                if (
                    3 <= x <= self.width - 3
                    and 4 <= y <= self.height - 4
                    and all(math.hypot(x - p.x, y - p.y) > 8 for p in self.phages.values())
                    and next(self._obstacles(x, y, PHAGE_PADDING), None) is None
                ):
                    self._add_phage(x, y)
                    return
        x, y = self.width * 0.22, self.height * 0.65
        for _ in range(60):
            if (
                3 <= x <= self.width - 3
                and 4 <= y <= self.height - 4
                and next(self._obstacles(x, y, PHAGE_PADDING), None) is None
            ):
                break
            x = self.rng.uniform(0, self.width)
            y = self.rng.uniform(0, self.height)
        self._add_phage(x, y)

    def _infect(self, bacterium: Bacterium, phage: Phage) -> None:
        if bacterium.kind not in BACTERIAL_KINDS:
            return
        angle = math.atan2(phage.y - bacterium.y, phage.x - bacterium.x) - bacterium.angle
        bacterium.infection = Infection(angle=angle)
        bacterium.leaving = False
        bacterium.rail = None
        self.phages.pop(phage.id, None)
        self.infections += 1
        self.phage_replenish_at = self.time + 45

    def _lyse(self, bacterium: Bacterium, *, progeny: int | None = None) -> None:
        self._add_nutrient(bacterium.x, bacterium.y, 3)
        if bacterium.infection is not None and bacterium.infection.age >= 7:
            x, y, angle = attachment_pose(bacterium)
            # A contracted, empty shell remains extracellular after host lysis.
            self.spent_capsids.append(
                Phage(
                    -1,
                    x - math.cos(angle) * 0.3,
                    y - math.sin(angle) * 0.3,
                    lifetime=18,
                    angle=angle,
                )
            )
            self.spent_capsids = self.spent_capsids[-64:]
        self.bacteria.pop(bacterium.id, None)
        self.bursts.append(Burst(bacterium.x, bacterium.y, bacterium.angle))
        self.lysed += 1
        # Release any macrophage pursuing this host; ingestion itself suppresses
        # the viral cycle, so phages never burst out through an enclosing cell.
        for cell in self.cells:
            if cell.target == bacterium.id:
                self._release(cell)
        count = min(
            self.rng.randint(4, 7) if progeny is None else progeny,
            self._phage_limit() - len(self.phages),
        )
        for index in range(count):
            angle = bacterium.angle + index * TAU / max(1, count) + self.rng.uniform(-0.2, 0.2)
            speed = self.rng.uniform(6, 10)
            self._add_phage(
                bacterium.x + math.cos(angle) * 4,
                bacterium.y + math.sin(angle) * 4,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                flight=2.5,
                lifetime=self.rng.uniform(100, 160),
            )

    def _update_phages(self, dt: float) -> None:
        for phage in list(self.phages.values()):
            phage.age += dt
            if phage.age >= phage.lifetime:
                del self.phages[phage.id]
                continue
            if phage.entry is not None:
                self._advance_entry(phage, dt)
                continue
            if phage.flight > 0:
                phage.x = (phage.x + phage.vx * dt) % self.width
                phage.y = (phage.y + phage.vy * dt) % self.height
                phage.vx *= math.exp(-dt * 0.8)
                phage.vy *= math.exp(-dt * 0.8)
                phage.flight = max(0, phage.flight - dt)
            # Settled phages ignore the ambient current, but moving membranes
            # can displace them just as they displace extracellular debris.
            self._exclude(phage, PHAGE_PADDING)
            # Orientation is cosmetic: settled particles do not chase hosts.
            candidates = [
                b
                for b in self.bacteria.values()
                if b.kind in BACTERIAL_KINDS
                and b.entry is None
                and b.owner is None
                and b.infection is None
            ]
            nearest = min(
                candidates, key=lambda b: math.hypot(b.x - phage.x, b.y - phage.y), default=None
            )
            if phage.flight == 0 and nearest is not None:
                dx, dy = nearest.x - phage.x, nearest.y - phage.y
                if math.hypot(dx, dy) < max(microbe_axes(nearest)) + 6:
                    phage.angle = math.atan2(dy, dx)
            nearby = set()
            for bacterium in list(self.bacteria.values()):
                if bacterium.entry is not None:
                    continue
                dx, dy = bacterium.x - phage.x, bacterium.y - phage.y
                distance = math.hypot(dx, dy)
                if bacterium.kind not in BACTERIAL_KINDS:
                    continue  # Bacteriophages do not infect yeast or protozoa.
                contact = phage_contact_distance(bacterium, math.atan2(-dy, -dx))
                if distance > contact + 1.2:
                    continue
                # The outer band retains a real encounter until separation;
                # entering it must not count as an attachment attempt itself.
                if distance <= contact or bacterium.id in phage.contacts:
                    nearby.add(bacterium.id)
                owner = next((c for c in self.cells if c.id == bacterium.owner), None)
                if distance > contact or (owner and owner.state is State.ENCLOSE):
                    continue
                if (
                    bacterium.id not in phage.contacts
                    and bacterium.owner is None
                    and bacterium.infection is None
                    and self.rng.random() < INFECTION_CHANCE
                ):
                    self._infect(bacterium, phage)
                    break
                # A failed attachment deflects the host, rather than letting the
                # free phage appear inside it. Hysteresis prevents repeated rolls
                # while they remain in the same contact neighborhood.
                angle = math.atan2(dy, dx)
                nx, ny = math.cos(angle), math.sin(angle)
                bacterium.x = phage.x + nx * (contact + 0.2)
                bacterium.y = phage.y + ny * (contact + 0.2)
                vx, vy = math.cos(bacterium.angle), math.sin(bacterium.angle)
                dot = vx * nx + vy * ny
                if dot < 0:
                    bacterium.angle = math.atan2(vy - 2 * dot * ny, vx - 2 * dot * nx)
                self._exclude(bacterium, bacterial_padding(bacterium))
            phage.contacts = nearby
        for burst in self.bursts:
            burst.age += dt
        self.bursts = [burst for burst in self.bursts if burst.age < 2.0]
        for capsid in self.spent_capsids:
            capsid.age += dt
            self._exclude(capsid, PHAGE_PADDING)
        self.spent_capsids = [c for c in self.spent_capsids if c.age < c.lifetime]
        if (
            not self.phages
            and not any(b.infection is not None for b in self.bacteria.values())
            and self.time >= self.phage_replenish_at
        ):
            self._seed_phage(arrival=True)
            self.phage_replenish_at = self.time + 45

    def current(self, x: float, y: float) -> tuple[float, float]:
        return (
            0.35 + math.sin(y * 0.07 + self.time * 0.09) * 0.25,
            math.sin(x * 0.05 + self.time * 0.13) * 0.22,
        )

    def _cell_current(self, cell: Cell) -> tuple[float, float]:
        # Crawling immune cells resist the slide's bulk flow; suspended
        # microbes and red cells continue to drift at the full fluid velocity.
        vx, vy = self.current(cell.x, cell.y)
        fx, fy = self.lab.flow(cell.x, cell.y)
        return vx * 0.15 + fx * 0.08, vy * 0.15 + fy * 0.08

    def _steer_from_edges(self, cell: Cell, dt: float) -> None:
        margin = cell.radius * 1.2 + 0.8
        band = max(4, cell.radius)
        dx = smooth(1 - (cell.x - margin) / band) - smooth(
            1 - (self.width - margin - cell.x) / band
        )
        dy = smooth(1 - (cell.y - margin) / band) - smooth(
            1 - (self.height - margin - cell.y) / band
        )
        if math.hypot(dx, dy) > 0.01:
            desired = math.atan2(dy, dx)
            turn = clamp(angle_delta(desired, cell.heading), -0.6 * dt, 0.6 * dt)
            cell.heading += turn

    def _release(self, cell: Cell) -> None:
        target = self.bacteria.get(cell.target)
        if target and target.owner == cell.id:
            target.owner = None
        cell.target = None
        cell.state = State.WANDER
        cell.elapsed = 0
        cell.cooldown = 1.5

    def _remodel_organelles(self, cell: Cell) -> None:
        if self.time < cell.remodel_at or (cell.state is State.DIVIDE and cell.elapsed >= 26):
            return
        mitochondria = [n for n in cell.organelles if n.kind == "mitochondrion"]
        if cell.fuse_next and len(mitochondria) >= 2:
            choices = []
            for index, left in enumerate(mitochondria):
                for right in mitochondria[index + 1 :]:
                    for a, (x, y) in enumerate(left.nodes):
                        for b, (xx, yy) in enumerate(right.nodes):
                            choices.append((math.hypot(x - xx, y - yy), left, right, a, b))
            distance, left, right, a, b = min(choices, key=lambda item: item[0])
            if distance < 0.55:
                offset = len(left.nodes)
                merged = OrganelleNetwork(
                    "mitochondrion",
                    left.nodes + right.nodes,
                    left.edges
                    + [(a + offset, b + offset) for a, b in right.edges]
                    + [(a, b + offset)],
                    left.tags + right.tags,
                    left.phase,
                )
                cell.organelles = [
                    n for n in cell.organelles if n is not left and n is not right
                ] + [merged]
        elif mitochondria:
            network = max(mitochondria, key=lambda n: len(n.edges))
            if len(network.edges) >= 3:
                edge = network.edges.pop(len(network.edges) // 2)
                pieces = network.fragments(set(range(len(network.nodes))))
                if len(pieces) > 1:
                    cell.organelles = [n for n in cell.organelles if n is not network] + pieces
                else:
                    network.edges.append(edge)
        cell.fuse_next = not cell.fuse_next
        cell.remodel_at = self.time + self.rng.uniform(15, 24)

    def _inherit_organelles(
        self, cell: Cell
    ) -> tuple[list[OrganelleNetwork], list[OrganelleNetwork]]:
        ux, uy = math.cos(cell.division_angle), math.sin(cell.division_angle)
        children = ([], [])
        for network in cell.organelles:
            for child_index, sign in enumerate((-1, 1)):
                selected = {
                    i
                    for i, (x, y) in enumerate(network.nodes)
                    if (1 if x * ux + y * uy >= 0 else -1) == sign
                }
                for piece in network.fragments(selected):
                    # Matches the final animated placement exactly, expressed in
                    # each smaller daughter's coordinates instead of the parent.
                    shift = sign * (0.76 - 0.62) / 0.72
                    piece.nodes = [(x - shift * ux, y - shift * uy) for x, y in piece.nodes]
                    children[child_index].append(piece)
        return children

    def _update_cell(self, cell: Cell, dt: float) -> None:
        if self.events.freezes(cell):
            return
        if cell.entry is not None:
            self._advance_entry(cell, dt)
            return
        cell.elapsed += dt
        cell.cooldown = max(0, cell.cooldown - dt)
        cell.reach *= math.exp(-3 * dt)
        self._remodel_organelles(cell)
        for vesicle in cell.vesicles:
            vesicle.age += dt
            vesicle.angle += dt * 0.13
        cell.vesicles = [v for v in cell.vesicles if v.age < VESICLE_TIME]
        if cell.state is State.DIVIDE:
            self._update_division(cell, dt)
            return
        if cell.adult_radius is not None:
            cell.radius = min(cell.adult_radius, cell.radius + dt * cell.adult_radius * 0.009)
        if (
            cell.kind == "macrophage"
            and self.time >= cell.divide_at
            and cell.state is not State.ENCLOSE
            and not cell.vesicles
        ):
            reserved = len(self.cells) + sum(c.state is State.DIVIDE for c in self.cells)
            if reserved < self._limits()[0]:
                self._release(cell)
                cell.state = State.DIVIDE
                cell.division_angle = self.rng.uniform(-0.6, 0.6)
                cell.reach = 0
                return
            cell.divide_at = self.time + self.rng.uniform(20, 35)
        target = self.bacteria.get(cell.target)
        if cell.state in (State.APPROACH, State.ENCLOSE):
            if target is None or target.owner != cell.id:
                self._release(cell)
                target = None
        if cell.state is State.WANDER and cell.cooldown == 0:
            nearby = [
                b
                for b in self.bacteria.values()
                if b.owner is None
                and b.entry is None
                and math.hypot(b.x - cell.x, b.y - cell.y) < 27
            ]
            if nearby:
                target = min(nearby, key=lambda b: math.hypot(b.x - cell.x, b.y - cell.y))
                target.owner = cell.id
                cell.target = target.id
                cell.state = State.APPROACH
                cell.elapsed = 0
        vx, vy = self._cell_current(cell)
        if cell.state is State.APPROACH and target:
            dx, dy = target.x - cell.x, target.y - cell.y
            distance = math.hypot(dx, dy)
            cell.heading = math.atan2(dy, dx)
            cell.reach_angle = cell.heading
            cell.reach = clamp(5 - (distance - cell.radius), 0, 2.8)
            vx += math.cos(cell.heading) * 2.6
            vy += math.sin(cell.heading) * 2.6
            padding = bacterial_padding(target)
            if distance <= cell.outline(cell.heading, self.time) + padding + 0.8:
                cell.state = State.ENCLOSE
                target.rail = None
                target.escape_until = 0
                cell.elapsed = 0
                cell.capture_distance = max(distance, cell.radius + padding + 0.5)
                cell.capture_start = cell.capture_distance
                cell.capture_axis = target.angle
                size = bacterial_scale(target)
                a, b = microbe_axes(target)
                cell.capture_a, cell.capture_b = a * size, b * size
                cell.reach = 0
            elif cell.elapsed > 25 or distance > 35:
                self._release(cell)
        elif cell.state is State.ENCLOSE and target:
            progress = clamp(cell.elapsed / ENCLOSE_TIME, 0, 1)
            cell.reach = 3.8 * (1 - smooth((cell.elapsed - SEAL_TIME) / 3))
            self._position_capture(cell, target)
            if progress >= 1:
                cell.vesicles.append(Vesicle(cell.reach_angle, 0.45, kind=target.kind))
                del self.bacteria[target.id]
                self.engulfed += 1
                cell.target = None
                cell.state = State.DIGEST
                cell.elapsed = 0
        else:
            cell.heading += math.sin(self.time * 0.3 + cell.phase) * dt * 0.25
            self._steer_from_edges(cell, dt)
            vx += math.cos(cell.heading) * 0.65
            vy += math.sin(cell.heading) * 0.65
            if cell.state is State.DIGEST and cell.elapsed >= VESICLE_TIME:
                cell.state = State.WANDER
                cell.elapsed = 0
                cell.cooldown = self.rng.uniform(1, 3)
        # Soft avoidance keeps nuclei from piling up without rigid collisions.
        for other in self.cells:
            if other is cell:
                continue
            dx, dy = cell.x - other.x, cell.y - other.y
            distance = math.hypot(dx, dy)
            separation = cell.radius + other.radius + 5
            if cell.state is State.ENCLOSE:
                separation += max(0, cell.capture_distance - cell.radius)
            if other.state is State.ENCLOSE:
                separation += max(0, other.capture_distance - other.radius)
            if 0 < distance < separation:
                force = (separation - distance) * 0.7
                vx += dx / distance * force
                vy += dy / distance * force
        margin = cell.radius * 1.2 + 0.8
        cell.x = clamp(cell.x + vx * dt, margin, self.width - margin)
        cell.y = clamp(cell.y + vy * dt, margin, self.height - margin)

    def _update_division(self, cell: Cell, dt: float) -> None:
        vx, vy = self._cell_current(cell)
        margin = cell.radius * 1.55 + 0.8
        cell.x = clamp(cell.x + vx * dt, margin, self.width - margin)
        cell.y = clamp(cell.y + vy * dt, margin, self.height - margin)
        if cell.elapsed < DIVISION_TIME:
            return
        x, y = cell.x, cell.y
        dx = math.cos(cell.division_angle) * cell.radius * 0.76
        dy = math.sin(cell.division_angle) * cell.radius * 0.76
        adult = cell.adult_radius or cell.radius
        left_organelles, right_organelles = self._inherit_organelles(cell)
        cell.radius *= 0.72
        cell.x, cell.y = x - dx, y - dy
        cell.state = State.WANDER
        cell.elapsed = 0
        cell.cooldown = 3
        cell.heading = cell.division_angle + math.pi
        cell.adult_radius = adult
        cell.organelles = left_organelles
        cell.remodel_at = self.time + self.rng.uniform(15, 24)
        cell.divide_at = self.time + self.rng.uniform(50, 75)
        daughter = Cell(
            self.next_cell_id,
            x + dx,
            y + dy,
            cell.radius,
            self.rng.uniform(0, TAU),
            cell.division_angle,
            cooldown=3,
            divide_at=self.time + self.rng.uniform(55, 85),
            adult_radius=adult,
            organelles=right_organelles,
            remodel_at=self.time + self.rng.uniform(15, 24),
        )
        self.next_cell_id += 1
        self.cells.append(daughter)
        self.divisions += 1

    def _reproduce_microbe(self, microbe: Bacterium, dt: float, limit: int) -> None:
        if (
            self.time < microbe.divide_at
            or microbe.owner is not None
            or microbe.infection is not None
            or microbe.leaving
            or microbe.entry is not None
            or len(self.bacteria) >= limit
        ):
            return
        if microbe.kind in ("yeast", "trypanosome"):
            microbe.bud = min(1, microbe.bud + dt / (12 if microbe.kind == "yeast" else 10))
            if microbe.bud < 1:
                return
        elif microbe.kind in ("bacillus", "colony") and microbe.units < 5:
            microbe.units += 1
            microbe.divide_at = self.time + self.rng.uniform(10, 18)
            return
        self._add_bacterium(microbe)
        child = self.bacteria[self.next_id - 1]
        if microbe.kind in ("bacillus", "colony"):
            child.units = microbe.units // 2
            microbe.units -= child.units
        angle = (
            microbe.angle if microbe.kind in ("yeast", "bacillus") else microbe.angle + math.pi / 2
        )
        axis = 0 if microbe.kind in ("yeast", "bacillus") else 1
        microbe.bud = 0
        separation = microbe_axes(microbe)[axis] + microbe_axes(child)[axis] + 0.5
        child.x = (microbe.x + math.cos(angle) * separation) % self.width
        child.y = (microbe.y + math.sin(angle) * separation) % self.height
        self._exclude(child, bacterial_padding(child))
        microbe.divide_at = self.time + self.rng.uniform(25, 65)

    def _rail_heading(self, microbe: Bacterium) -> float | None:
        if microbe.kind not in ("rod", "bacillus", "vibrio"):
            return None
        if microbe.rail is not None and (
            microbe.rail >= len(self.hyphae) or self.time >= microbe.rail_until
        ):
            microbe.rail = None
            microbe.rail_ready = self.time + 6
        if microbe.rail is None and self.time >= microbe.rail_ready:
            microbe.rail_ready = self.time + 1
            nearest = None
            for ident, hypha in enumerate(self.hyphae):
                for a, b in hypha.edges:
                    x, y = hypha.nodes[a]
                    xx, yy = hypha.nodes[b]
                    dx, dy = xx - x, yy - y
                    length2 = dx * dx + dy * dy
                    if length2 < 0.01:
                        continue
                    t = clamp(((microbe.x - x) * dx + (microbe.y - y) * dy) / length2, 0, 1)
                    px, py = x + dx * t, y + dy * t
                    distance = math.hypot(microbe.x - px, microbe.y - py)
                    if distance <= 6 and (nearest is None or distance < nearest[0]):
                        if next(self._obstacles(px, py, bacterial_padding(microbe)), None) is None:
                            nearest = distance, ident, a, b, dx, dy
            if nearest is not None:
                _, ident, a, b, dx, dy = nearest
                if math.cos(microbe.angle) * dx + math.sin(microbe.angle) * dy < 0:
                    a, b = b, a
                microbe.rail, microbe.rail_from, microbe.rail_to = ident, a, b
                microbe.rail_until = self.time + self.rng.uniform(12, 22)
        if microbe.rail is None:
            return None
        hypha = self.hyphae[microbe.rail]
        x, y = hypha.nodes[microbe.rail_from]
        xx, yy = hypha.nodes[microbe.rail_to]
        heading = math.atan2(yy - y, xx - x)
        side = 1 if microbe.id % 2 else -1
        tx, ty = xx - math.sin(heading) * side * 1.6, yy + math.cos(heading) * side * 1.6
        if math.hypot(tx - microbe.x, ty - microbe.y) < 1.4:
            neighbors = [
                b if a == microbe.rail_to else a
                for a, b in hypha.edges
                if (a == microbe.rail_to or b == microbe.rail_to)
                and a != microbe.rail_from
                and b != microbe.rail_from
            ]
            if neighbors:
                microbe.rail_from, microbe.rail_to = microbe.rail_to, self.rng.choice(neighbors)
                xx, yy = hypha.nodes[microbe.rail_to]
                return math.atan2(yy - microbe.y, xx - microbe.x)
            microbe.rail = None
            microbe.rail_ready = self.time + 6
            return None
        return math.atan2(ty - microbe.y, tx - microbe.x)

    def _microbe_behavior(self, microbe: Bacterium, dt: float) -> float:
        """Steer locally; return a speed multiplier. Capture remains authoritative."""
        if microbe.leaving:
            distances = (microbe.x, self.width - microbe.x, microbe.y, self.height - microbe.y)
            microbe.angle = (math.pi, 0, -math.pi / 2, math.pi / 2)[distances.index(min(distances))]
            return 1
        if microbe.infection is not None:
            microbe.rail = None
            return 1
        desired, turn_rate, multiplier = None, 2.2, 1.0
        evasive = microbe.kind in ("rod", "spiral", "spirochete", "vibrio") and microbe.id % 3 != 0
        threat = None
        if evasive:
            for cell in self.cells:
                dx, dy = microbe.x - cell.x, microbe.y - cell.y
                angle = math.atan2(dy, dx)
                gap = (
                    math.hypot(dx, dy) - cell.outline(angle, self.time) - bacterial_padding(microbe)
                )
                if gap < 4 and cell.state is not State.DIVIDE:
                    if threat is None or gap < threat[0]:
                        threat = gap, angle
            if threat is not None and self.time >= microbe.escape_ready:
                microbe.escape_until = self.time + 1.2
                microbe.escape_ready = self.time + self.rng.uniform(8, 14)
            if threat is not None and self.time < microbe.escape_until:
                desired, turn_rate, multiplier = threat[1], 7, 2.2
                microbe.rail = None
                microbe.rail_ready = self.time + 5
        if desired is None:
            desired = self._rail_heading(microbe)
            if desired is not None:
                turn_rate = 5
        best = None
        if microbe.kind != "trypanosome":
            for patch in self.nutrients:
                distance = math.hypot(microbe.x - patch.x, microbe.y - patch.y)
                if distance < patch.radius * 0.65:
                    eaten = min(max(0, patch.amount - 0.1), dt * 0.3)
                    patch.amount -= eaten
                    if eaten:
                        microbe.fed_until = self.time + 1
                        if microbe.owner is None:
                            microbe.divide_at -= eaten * 4
                if distance < 20 + microbe.id % 13 and patch.amount > 0.2:
                    score = patch.amount / max(4, distance)
                    if best is None or score > best[0]:
                        best = score, patch
            if desired is None and best is not None and microbe.kind in BACTERIAL_KINDS:
                patch = best[1]
                desired = math.atan2(patch.y - microbe.y, patch.x - microbe.x)
        if desired is not None:
            microbe.angle += clamp(
                angle_delta(desired, microbe.angle), -turn_rate * dt, turn_rate * dt
            )
        return multiplier

    def advance_events(self, dt: float) -> None:
        while dt > 1e-9:
            step = min(0.1, dt)
            self.events.advance(self, step)
            dt -= step

    def update(self, dt: float = STEP, *, events: bool = True) -> None:
        self.time += dt
        self.lab.update(self, dt)
        _, bacteria_count, _, _ = self._limits()
        self._update_nutrients(dt)
        for bacterium in list(self.bacteria.values()):
            if self.events.trapped(bacterium):
                continue
            if bacterium.entry is not None:
                self._advance_entry(bacterium, dt)
                continue
            owner = next((c for c in self.cells if c.id == bacterium.owner), None)
            if owner and owner.state is State.ENCLOSE:
                continue
            if bacterium.infection is not None:
                bacterium.infection.age += dt
                if bacterium.infection.age >= VIRAL_TIME:
                    self._lyse(bacterium)
                    continue
            if self.time >= bacterium.turn_at:
                bacterium.angle += self.rng.uniform(-1.8, 1.8)
                bacterium.turn_at = self.time + self.rng.uniform(1, 4)
            vx, vy = self.current(bacterium.x, bacterium.y)
            fx, fy = self.events.flow(bacterium.x, bacterium.y)
            vx += fx
            vy += fy
            boost = self._microbe_behavior(bacterium, dt)
            motility = (
                1 if bacterium.infection is None else 1 - 0.88 * smooth(bacterium.infection.age / 7)
            )
            speed = 2.5 if bacterium.leaving else bacterium.speed * boost * motility
            vx += math.cos(bacterium.angle) * speed
            vy += math.sin(bacterium.angle) * speed
            if bacterium.kind == "spirochete":
                # Whole-body corkscrew swimming, rather than an external tail.
                sway = math.sin(self.time * 5 + bacterium.id) * 0.65
                vx -= math.sin(bacterium.angle) * sway
                vy += math.cos(bacterium.angle) * sway
            elif bacterium.kind == "trypanosome":
                sway = math.sin(self.time * 3 + bacterium.id) * 1.2
                vx -= math.sin(bacterium.angle) * sway
                vy += math.cos(bacterium.angle) * sway
            bacterium.x += vx * dt
            bacterium.y += vy * dt
            if bacterium.leaving:
                if not (0 <= bacterium.x < self.width and 0 <= bacterium.y < self.height):
                    del self.bacteria[bacterium.id]
                    continue
            else:
                bacterium.x %= self.width
                bacterium.y %= self.height
            reserve = min(2, max(1, bacteria_count // 4))
            self._reproduce_microbe(bacterium, dt, bacteria_count * 2 - reserve)
        for cell in list(self.cells):
            self._update_cell(cell, dt)
        for obj in [*self.red_cells, *self.debris]:
            if obj.entry is not None:
                self._advance_entry(obj, dt)
                continue
            vx, vy = self.current(obj.x, obj.y)
            fx, fy = self.events.flow(obj.x, obj.y)
            vx += fx
            vy += fy
            obj.x = (obj.x + vx * dt) % self.width
            obj.y = (obj.y + (vy + math.sin(self.time * 0.3 + obj.phase) * 0.16) * dt) % self.height
        self._resolve_obstacles()
        self._update_phages(dt)
        self._update_hyphae()
        self._update_arrivals()
        if events:
            self.advance_events(dt)
