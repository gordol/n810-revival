"""Target geometry and bounded experimental interventions, independent of curses."""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from .events import segment_distance
from .models import (
    ASPECT,
    SEAL_TIME,
    State,
    Vesicle,
    bacterial_scale,
    disc_axes,
    microbe_axes,
    PHAGE_PADDING,
    DEBRIS_PADDING,
    bacterial_padding,
    smooth,
    clamp,
)


@dataclass(eq=False)
class Target:
    kind: str
    obj: object
    segment: tuple[int, int] | None = None

    def alive(self, world):
        pools = {
            "cell": world.cells,
            "microbe": world.bacteria.values(),
            "red": world.red_cells,
            "phage": world.phages.values(),
            "hypha": world.hyphae,
            "food": world.nutrients,
        }
        if self.kind == "rotifer":
            return world.events.active is self.obj
        return any(obj is self.obj for obj in pools[self.kind]) and (
            self.segment is None or self.segment in self.obj.edges
        )

    @property
    def center(self):
        if self.kind == "hypha":
            a, b = (self.obj.nodes[i] for i in self.segment)
            return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        return self.obj.x, self.obj.y

    @property
    def extent(self):
        if self.kind == "cell":
            return self.obj.extent()
        if self.kind == "microbe":
            return max(microbe_axes(self.obj)) * bacterial_scale(self.obj)
        if self.kind == "red":
            return self.obj.size
        return {"phage": 1.5, "rotifer": 14, "food": 5, "hypha": 2}[self.kind]


def targets(world):
    result = [Target("cell", obj) for obj in world.cells]
    result += [Target("microbe", obj) for obj in world.bacteria.values()]
    result += [Target("red", obj) for obj in world.red_cells]
    result += [Target("phage", obj) for obj in world.phages.values()]
    result += [Target("hypha", obj, obj.edges[0]) for obj in world.hyphae if obj.edges]
    result += [Target("food", obj) for obj in world.nutrients]
    if world.events.active is not None and world.events.active.kind == "rotifer":
        result.append(Target("rotifer", world.events.active))
    return result


def hit_test(world, col: int, row: int):
    """Pick the visible body under a terminal cell; never pick a distant neighbor."""
    x, y = col, row * ASPECT
    hits = []
    for order, target in enumerate(targets(world)):
        obj = target.obj
        cx, cy = target.center
        dx, dy = x - cx, y - cy
        priority = {
            "food": 0,
            "hypha": 1,
            "red": 2,
            "phage": 3,
            "microbe": 4,
            "cell": 5,
            "rotifer": 7,
        }[target.kind]
        distance = math.hypot(dx, dy)
        if target.kind == "cell":
            inside = distance <= obj.outline(math.atan2(dy, dx), world.time) + 0.6
            order = obj.radius  # Large cells are painted over small cells.
        elif target.kind == "microbe":
            owner = next((c for c in world.cells if c.id == obj.owner), None)
            if owner and owner.state is State.ENCLOSE:
                priority = 6
            a, b = microbe_axes(obj)
            scale = bacterial_scale(obj)
            ux, uy = math.cos(obj.angle), math.sin(obj.angle)
            inside = ((dx * ux + dy * uy) / (a * scale + 0.6)) ** 2 + (
                (-dx * uy + dy * ux) / (b * scale + 0.8)
            ) ** 2 <= 1
        elif target.kind == "red":
            a, b = disc_axes(obj)
            inside = (dx / (a + 0.5)) ** 2 + (dy / (b + 0.8)) ** 2 <= 1
        elif target.kind == "phage":
            if abs(math.cos(obj.angle)) > abs(math.sin(obj.angle)):
                inside = row == round(obj.y / ASPECT) and col in (
                    round(obj.x - 0.5),
                    round(obj.x - 0.5) + 1,
                )
            else:
                inside = (col, row) == (round(obj.x), round(obj.y / ASPECT))
        elif target.kind == "hypha":
            edges = sorted(
                obj.edges, key=lambda edge: segment_distance(x, y, *(obj.nodes[i] for i in edge))
            )
            target.segment = edges[0]
            inside = segment_distance(x, y, *(obj.nodes[i] for i in target.segment)) <= 1
        elif target.kind == "rotifer":
            ux, uy = math.cos(obj.angle), math.sin(obj.angle)
            along, across = dx * ux + dy * uy, -dx * uy + dy * ux
            opening = smooth((obj.age - 14) / 6) * (1 - smooth((obj.age - 48) / 5))
            inside = (
                (along / 9.6) ** 2 + (across / 4.6) ** 2 <= 1
                or -14 <= along <= -8
                and abs(across) <= 2
                or any(
                    math.hypot(along - 11, across - sign * (1 + opening * 2.5))
                    < 1.3 + opening * 1.7
                    for sign in (-1, 1)
                )
            )
        else:
            inside = distance < obj.radius
        if inside:
            hits.append((priority, order, target))
    if not hits:
        return None
    top = max(hits, key=lambda item: item[:2])[2]
    # The renderer redraws a nucleus over ingested cargo. Respect that visible
    # foreground when a captured microbe and its owner's nucleus overlap.
    if top.kind == "microbe" and top.obj.owner is not None:
        owner = next(
            (t for _, _, t in hits if t.kind == "cell" and t.obj.id == top.obj.owner), None
        )
        if owner is not None and 0 <= col < world.width and 0 <= row < world.height / ASPECT:
            from .render import Ink, render

            pixel = render(world).pixels[row][col]
            if pixel.ink in (Ink.NUCLEUS, Ink.NUCLEOLUS, Ink.DNA, Ink.SPINDLE):
                return owner
    return top


@dataclass
class Fragment:
    x: float
    y: float
    vx: float
    vy: float
    role: str
    char: str


@dataclass
class Rupture:
    target: Target
    x: float
    y: float
    angle: float
    size: float
    age: float = 0.0
    fragments: list[Fragment] = field(default_factory=list)


@dataclass
class Pulse:
    x: float
    y: float
    age: float = 0.0


@dataclass
class Laboratory:
    ruptures: list[Rupture] = field(default_factory=list)
    stirs: list[Pulse] = field(default_factory=list)
    pings: list[Pulse] = field(default_factory=list)

    def lyse(self, world, target, x, y):
        if target is None or not target.alive(world):
            return "No cell at cursor"
        if target.kind in ("rotifer", "food"):
            return "Choose a cell, fungal branch, or phage particle"
        if len(self.ruptures) >= 16:
            self.ruptures.pop(0)
        cx, cy = target.center
        effect = Rupture(
            target,
            cx,
            cy,
            math.atan2(y - cy, x - cx),
            target.obj.radius if target.kind == "cell" else target.extent,
        )
        self.ruptures.append(effect)
        self._rupture(world, effect)
        return "Cell ruptured" if target.kind != "hypha" else "Fungal branch severed"

    def feed(self, world, x, y):
        if next(world._obstacles(x, y, 3), None) is not None:
            return "Place nutrients in clear fluid outside membranes"
        world._add_nutrient(x, y, 5)
        self.pings.append(Pulse(x, y))
        self.pings = self.pings[-8:]
        return "Nutrient droplet added"

    def stir(self, world, x, y):
        self.stirs.append(Pulse(x, y))
        self.stirs = self.stirs[-4:]
        # Apply on input, including while explicitly paused. The remaining
        # current advances with simulation time, without freezing the scene.
        self._stir_particles(world, 0.35)
        return "Local current applied"

    def flow(self, x, y):
        fx = fy = 0.0
        for pulse in self.stirs:
            dx, dy = x - pulse.x, y - pulse.y
            distance = math.hypot(dx, dy)
            if distance < 24:
                # A finite core prevents the clicked particle becoming a
                # stationary pivot. The bias blends into the outer swirl.
                core = max(0, 1 - distance / 4)
                nx, ny = dx / max(1, distance), dy / max(1, distance)
                force = 16 * (1 - distance / 24) * math.exp(-pulse.age * 0.8)
                fx += (-ny + 0.35 * nx + core) * force
                fy += (nx + 0.35 * ny + core * 0.5) * force
        speed = math.hypot(fx, fy)
        scale = min(1.0, 18 / max(0.001, speed))
        return fx * scale, fy * scale

    def _advect(self, world, obj, dt, padding, *, red=True):
        if getattr(obj, "entry", None) is not None:
            return
        fx, fy = self.flow(obj.x, obj.y)
        # Resolve small steps so an input-time impulse cannot jump membranes.
        steps = max(1, math.ceil(math.hypot(fx, fy) * dt / 0.5))
        for _ in range(steps):
            if not (fx or fy):
                break
            obj.x = (obj.x + fx * dt / steps) % world.width
            obj.y = (obj.y + fy * dt / steps) % world.height
            world._exclude(obj, padding, red=red)

    def _stir_particles(self, world, dt):
        for microbe in world.bacteria.values():
            owner = next((c for c in world.cells if c.id == microbe.owner), None)
            if world.events.trapped(microbe) or (owner and owner.state is State.ENCLOSE):
                continue
            fx, fy = self.flow(microbe.x, microbe.y)
            if fx or fy:
                microbe.rail = None
            self._advect(world, microbe, dt, bacterial_padding(microbe))
        for disc in world.red_cells:
            self._advect(world, disc, dt, disc.size + 1, red=False)
        for particle in world.debris:
            self._advect(world, particle, dt, DEBRIS_PADDING)
        for phage in [*world.phages.values(), *world.spent_capsids]:
            self._advect(world, phage, dt, PHAGE_PADDING)
        for effect in self.ruptures:
            for piece in effect.fragments:
                self._advect(world, piece, dt, 0.6)

    def update(self, world, dt):
        if self.stirs:
            self._stir_particles(world, dt)
        for pulse in self.stirs + self.pings:
            pulse.age += dt
        self.stirs = [p for p in self.stirs if p.age < 4]
        self.pings = [p for p in self.pings if p.age < 1.5]
        for effect in self.ruptures:
            effect.age += dt
            for piece in effect.fragments:
                piece.x += piece.vx * dt
                piece.y += piece.vy * dt
                piece.vx *= math.exp(-dt * 0.6)
                piece.vy *= math.exp(-dt * 0.6)
                world._exclude(piece, 0.6)
        self.ruptures = [e for e in self.ruptures if e.age < 7]

    def _rupture(self, world, effect):
        target, obj = effect.target, effect.target.obj
        if target.kind == "cell":
            world._release(obj)
            for bacterium in world.bacteria.values():
                if bacterium.owner == obj.id:
                    bacterium.owner = None
            world.cells = [c for c in world.cells if c is not obj]
            event = world.events.active
            if event and event.kind == "net" and event.source == obj.id:
                world.events.finish()
            world._add_nutrient(
                clamp(effect.x, 0, world.width - 1), clamp(effect.y, 0, world.height - 1), 4
            )
            roles = [
                ("membrane", "-"),
                ("nucleus", "~"),
                ("mitochondrion", ")"),
                ("reticulum", "~"),
                ("vesicle", "o"),
            ]
        elif target.kind == "red":
            world.red_cells = [r for r in world.red_cells if r is not obj]
            world._add_nutrient(
                clamp(effect.x, 0, world.width - 1), clamp(effect.y, 0, world.height - 1), 2
            )
            roles = [("red", "."), ("red_dim", ":")]
        elif target.kind == "microbe":
            owner = next((c for c in world.cells if c.target == obj.id and c.id == obj.owner), None)
            if owner and owner.state is State.ENCLOSE and owner.elapsed >= SEAL_TIME:
                world._release(owner)
                owner.state = State.DIGEST
                owner.elapsed = 9
                owner.vesicles.append(Vesicle(owner.reach_angle, 0.45, age=9, kind=obj.kind))
                world.bacteria.pop(obj.id, None)
                world.engulfed += 1
                return
            for cell in world.cells:
                if cell.target == obj.id:
                    world._release(cell)
            if obj.infection:
                assembled = (
                    0
                    if obj.infection.age < 14
                    else 2 + min(3, int((obj.infection.age - 14) / 7 * 4))
                )
                world._lyse(obj, progeny=assembled)
            else:
                world.bacteria.pop(obj.id, None)
                world._add_nutrient(
                    clamp(effect.x, 0, world.width - 1), clamp(effect.y, 0, world.height - 1), 2
                )
            roles = [("microbe", "-"), ("microbial_dna", "~")]
        elif target.kind == "hypha":
            a, b = target.segment
            obj.edges.remove(target.segment)
            new_tips = [
                (
                    node,
                    math.atan2(
                        obj.nodes[node][1] - obj.nodes[other][1],
                        obj.nodes[node][0] - obj.nodes[other][0],
                    ),
                )
                for node, other in ((a, b), (b, a))
            ]
            obj.tips = (new_tips + [tip for tip in obj.tips if tip[0] not in (a, b)])[:4]
            obj.grow_at = world.time + 5
            network = next(i for i, hypha in enumerate(world.hyphae) if hypha is obj)
            for bacterium in world.bacteria.values():
                if bacterium.rail == network and {bacterium.rail_from, bacterium.rail_to} == {a, b}:
                    bacterium.rail = None
            roles = [("fungus", ":"), ("fungus", ".")]
        else:
            world.phages.pop(obj.id, None)
            roles = [("phage", ".")]
        count = 18 if target.kind == "cell" else 8 if target.kind != "phage" else 3
        for index in range(count):
            angle = effect.angle + index * 2.399963
            distance = effect.size * (0.2 + (index % 5) * 0.12)
            speed = 1.5 + index % 5 * 0.7
            role, char = roles[index % len(roles)]
            effect.fragments.append(
                Fragment(
                    effect.x + math.cos(angle) * distance,
                    effect.y + math.sin(angle) * distance,
                    math.cos(angle) * speed,
                    math.sin(angle) * speed,
                    role,
                    char,
                )
            )

    def resize(self, sx, sy):
        for pulse in self.stirs + self.pings:
            pulse.x *= sx
            pulse.y *= sy
        for effect in self.ruptures:
            effect.x *= sx
            effect.y *= sy
            for fragment in effect.fragments:
                fragment.x *= sx
                fragment.y *= sy
                fragment.vx *= sx
                fragment.vy *= sy
