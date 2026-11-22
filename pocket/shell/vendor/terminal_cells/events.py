"""Rare, seeded vignettes; interactive pacing uses unpaused wall time."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import random

from .models import BACTERIAL_KINDS, State, TAU, bacterial_padding, clamp, smooth


@dataclass
class Meal:
    kind: str
    age: float = 0.0


@dataclass
class Sighting:
    kind: str
    x: float
    y: float
    angle: float = 0.0
    age: float = 0.0
    radius: float = 12.0
    source: int | None = None
    phase: str = "entering"
    traveled: float = 0.0
    travel_goal: float = 36.0
    eaten: int = 0
    fed_at: float = -10.0
    dropped: bool = False
    deposited: bool = False
    held: set[int] = field(default_factory=set)
    caught: set[int] = field(default_factory=set)
    meals: list[Meal] = field(default_factory=list)

    @property
    def mouth(self):
        return self.x + math.cos(self.angle) * 11, self.y + math.sin(self.angle) * 11


def web_segments(event: Sighting):
    """The same strands are drawn and tested for bacterial contact."""
    reach = event.radius * (0.35 + 1.65 * smooth((event.age - 5) / 13))
    nodes = []
    for index in range(10):
        angle = event.angle + index * TAU / 10
        radius = reach * (0.75 + 0.2 * math.sin(index * 3.7))
        nodes.append((event.x + math.cos(angle) * radius, event.y + math.sin(angle) * radius))
    center = event.x, event.y
    for index, node in enumerate(nodes):
        yield center, node
        if index % 2 == 0:
            yield node, nodes[(index + 1) % len(nodes)]


def segment_distance(x, y, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    t = clamp(((x - start[0]) * dx + (y - start[1]) * dy) / max(0.001, dx * dx + dy * dy), 0, 1)
    return math.hypot(x - start[0] - t * dx, y - start[1] - t * dy)


@dataclass
class EventDirector:
    seed: int
    enabled: bool = True
    microscope: bool = True
    clock: float = 0.0
    next_at: float = field(init=False)
    active: Sighting | None = None
    last_kind: str | None = None
    counts: dict[str, int] = field(default_factory=dict)
    cooldowns: dict[str, float] = field(default_factory=dict)
    rng: random.Random = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        self.rng = random.Random(self.seed ^ 0x5A17C311)
        self.next_at = self.rng.uniform(180, 360)

    @property
    def caption(self):
        event = self.active
        if event is None:
            return ""
        if event.kind == "rotifer":
            return "Rare visitor: rotifer / " + event.phase
        if event.kind == "net":
            return "Neutrophil DNA trap / " + (
                "chromatin unfolding" if event.age < 10 else "extracellular web"
            )
        return "Micropipette / " + (
            "nutrient droplet" if event.deposited and event.age < 20 else "passing glass tip"
        )

    def freezes(self, cell):
        e = self.active
        return e is not None and e.kind == "net" and e.source == cell.id and e.age < 10

    def trapped(self, bacterium):
        e = self.active
        return (
            e is not None
            and e.kind == "net"
            and bacterium.id in e.held
            and bacterium.owner is None
            and bacterium.infection is None
            and e.age < 45
        )

    def start(self, world, kind: str) -> bool:
        """Start only with a suitable subject and room; also used by previews/tests."""
        if not self.enabled or self.active is not None:
            return False
        if kind == "net":
            candidates = [
                c
                for c in world.cells
                if c.kind == "neutrophil"
                and c.entry is None
                and c.state in (State.WANDER, State.APPROACH)
                and not c.vesicles
                and sum(
                    b.owner is None
                    and b.entry is None
                    and b.infection is None
                    and math.hypot(b.x - c.x, b.y - c.y) < c.radius + 18
                    for b in world.bacteria.values()
                )
                >= 2
            ]
            if not candidates:
                return False
            cell = self.rng.choice(candidates)
            world._release(cell)  # A pursuit may yield to trap release; sealed cups never do.
            event = Sighting(kind, cell.x, cell.y, cell.phase, radius=cell.radius, source=cell.id)
        elif kind in ("rotifer", "pipette"):
            if world.width < 80 or world.height < 48:
                return False
            if (
                kind == "rotifer"
                and world.scene == "blood"
                or kind == "pipette"
                and not self.microscope
            ):
                return False
            event = None
            for _ in range(32):
                right = bool(self.rng.randrange(2))
                x = world.width - 18 if right else 18
                y = self.rng.uniform(14, world.height - 14)
                if kind == "rotifer":
                    prey = [
                        b
                        for b in world.bacteria.values()
                        if b.kind in BACTERIAL_KINDS
                        and b.owner is None
                        and b.infection is None
                        and b.entry is None
                    ]
                    if prey:
                        subject = self.rng.choice(prey)
                        right = subject.x > world.width / 2
                        direction = -1 if right else 1
                        x = (
                            clamp(subject.x - direction * 19, world.width - 33, world.width - 18)
                            if right
                            else clamp(subject.x - 19, 18, 33)
                        )
                        y = clamp(subject.y + self.rng.uniform(-2, 2), 14, world.height - 14)
                if next(world._obstacles(x, y, 14, visitors=False), None) is None:
                    event = Sighting(
                        kind, world.width + 18 if right else -18, y, math.pi if right else 0
                    )
                    if kind == "rotifer":
                        event.travel_goal = abs(x - event.x)
                    break
            if event is None:
                return False
        else:
            raise ValueError("unknown rare event")
        self.active = event
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return True

    def resize(self, sx, sy):
        if self.active:
            self.active.x *= sx
            self.active.y *= sy
            self.active.radius *= min(sx, sy)

    def obstacle(self, x, y, padding):
        e = self.active
        if e is None or e.kind != "rotifer":
            return
        dx, dy = x - e.x, y - e.y
        if abs(dx) > 12 + padding or abs(dy) > 12 + padding:
            return
        angle = math.atan2(dy, dx)
        local = angle - e.angle
        boundary = 1 / math.hypot(math.cos(local) / 9, math.sin(local) / 4) + padding
        distance = math.hypot(dx, dy)
        if distance < boundary:
            yield math.cos(angle), math.sin(angle), boundary - distance

    def flow(self, x, y):
        e = self.active
        if e is None:
            return 0.0, 0.0
        if e.kind == "rotifer" and e.phase == "feeding":
            mx, my = e.mouth
            dx, dy = mx - x, my - y
            distance = math.hypot(dx, dy)
            forward = (x - mx) * math.cos(e.angle) + (y - my) * math.sin(e.angle)
            if 0 < distance < 18 and forward > -1:
                force = 3.2 * (1 - distance / 18)
                return dx / distance * force, dy / distance * force
        if e.kind == "pipette" and 10 <= e.age < 16:
            dx, dy = x - e.x, y - e.y
            distance = math.hypot(dx, dy)
            if 0 < distance < 16:
                force = 0.8 * (1 - distance / 16) * (1 - (e.age - 10) / 6)
                return dx / distance * force, dy / distance * force
        return 0.0, 0.0

    def advance(self, world, dt):
        if not self.enabled:
            return
        self.clock += dt
        e = self.active
        if e is None:
            if self.clock >= self.next_at:
                choices = [
                    k
                    for k in ("rotifer", "net", "pipette")
                    if self.clock >= self.cooldowns.get(k, 0)
                ]
                self.rng.shuffle(choices)
                choices.sort(key=lambda kind: kind == self.last_kind)
                if not any(self.start(world, k) for k in choices):
                    self.next_at = self.clock + 20
            return
        e.age += dt
        if e.kind == "rotifer":
            self._rotifer(world, e, dt)
            finished = e.age >= 100 or (
                e.phase == "leaving" and (e.x < -20 or e.x > world.width + 20)
            )
        elif e.kind == "net":
            self._net(world, e)
            finished = e.age >= 60
        else:
            self._pipette(world, e)
            finished = e.age >= 32
        if finished:
            self.finish()

    def finish(self):
        if self.active is None:
            return
        self.last_kind = self.active.kind
        self.cooldowns[self.active.kind] = self.clock + 900
        self.active = None
        self.next_at = self.clock + self.rng.uniform(180, 360)

    def _rotifer(self, world, e, dt):
        if e.age >= 48:
            e.phase = "leaving"
        elif e.traveled >= e.travel_goal:
            e.phase = "feeding"
        if e.phase in ("entering", "leaving"):
            sign = -1 if e.phase == "leaving" else 1
            dx = math.cos(e.angle) * dt * 2 * sign
            dy = math.sin(e.angle) * dt * 2 * sign
            if next(world._obstacles(e.x + dx, e.y + dy, 13, visitors=False), None) is None:
                e.x += dx
                e.y += dy
                e.traveled += math.hypot(dx, dy)
        for meal in e.meals:
            meal.age += dt
        e.meals = [m for m in e.meals if m.age < 8]
        if e.phase != "feeding":
            return
        mx, my = e.mouth
        floor = max(3, world._limits()[1] // 2)
        for b in list(world.bacteria.values()):
            if (
                e.eaten < 3
                and e.age - e.fed_at > 6
                and len(world.bacteria) > floor
                and b.kind in BACTERIAL_KINDS
                and b.owner is None
                and b.infection is None
                and b.entry is None
                and math.hypot(b.x - mx, b.y - my) < 3
            ):
                e.meals.append(Meal(b.kind))
                del world.bacteria[b.id]
                e.eaten += 1
                e.fed_at = e.age
        for particle in list(world.debris):
            if len(world.debris) > 5 and math.hypot(particle.x - mx, particle.y - my) < 1.8:
                world.debris.remove(particle)

    def _net(self, world, e):
        if e.age >= 10 and e.source is not None:
            source = next((c for c in world.cells if c.id == e.source), None)
            if source is not None:
                world._release(source)
                world.cells.remove(source)
                world.large_arrival_at = min(world.large_arrival_at, world.time + 60)
            e.source = None
        if not 10 <= e.age < 45:
            e.held.clear()
            return
        e.held = {
            ident
            for ident in e.held
            if ident in world.bacteria
            and world.bacteria[ident].owner is None
            and world.bacteria[ident].infection is None
        }
        for b in world.bacteria.values():
            if (
                len(e.caught) < 3
                and b.id not in e.caught
                and b.kind in BACTERIAL_KINDS
                and b.owner is None
                and b.infection is None
                and b.entry is None
                and any(
                    segment_distance(b.x, b.y, *segment) < 1 + bacterial_padding(b) * 0.3
                    for segment in web_segments(e)
                )
            ):
                e.held.add(b.id)
                e.caught.add(b.id)
        # Remove at most three, and preserve a viable microbial population.
        if e.age >= 35:
            for ident in list(e.held):
                if len(world.bacteria) > max(3, world._limits()[1] // 2):
                    del world.bacteria[ident]
                e.held.remove(ident)

    def _pipette(self, world, e):
        ux = math.cos(e.angle)
        target = world.width - 18 if ux < 0 else 18
        outside = world.width + 18 if ux < 0 else -18
        progress = smooth(e.age / 8) if e.age < 20 else 1 - smooth((e.age - 20) / 12)
        e.x = outside * (1 - progress) + target * progress
        if e.age >= 10 and not e.dropped:
            # The pipette is in a separate focal layer; deposit only in clear fluid.
            if next(world._obstacles(e.x + ux * 3, e.y, 3), None) is None:
                world._add_nutrient(e.x + ux * 3, e.y, 5)
                e.deposited = True
            e.dropped = True
