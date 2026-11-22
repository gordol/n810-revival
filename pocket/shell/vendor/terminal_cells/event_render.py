"""Read-only drawings for rare sightings."""

import math

from .events import web_segments
from .models import ASPECT, Bacterium, TAU, smooth
from .render import BACTERIA_INKS, Frame, Ink, draw_bacterium


def draw_sighting(frame: Frame, world, unicode: bool):
    event = world.events.active
    if event is None:
        return
    if event.kind == "rotifer":
        _rotifer(frame, event, unicode)
    elif event.kind == "net":
        _net(frame, world, event, unicode)
    else:
        _pipette(frame, world, event, unicode)


def _rotifer(frame, e, unicode):
    ux, uy = math.cos(e.angle), math.sin(e.angle)

    def point(along, across):
        return e.x + ux * along - uy * across, e.y + uy * along + ux * across

    drawing = Frame(frame.width, frame.height)
    # Pear-shaped body with segmented cuticle, forked foot, and moving mastax.
    for i in range(81):
        angle = i * TAU / 80
        along, across = math.cos(angle) * 9, math.sin(angle) * (3.5 + 0.5 * math.cos(angle))
        drawing.point(
            *point(along, across), "-" if abs(math.sin(angle)) > 0.6 else "/", Ink.ROTIFER
        )
    for side in (-1, 1):
        drawing.line(*point(8.5, side), *point(11, side), Ink.ROTIFER, unicode)
    for along in (-6, -3, 0):
        drawing.line(*point(along, -3), *point(along, 3), Ink.ROTIFER, unicode)
    for side in (-1, 1):
        drawing.line(*point(-8, 0), *point(-13, side * 1.5), Ink.ROTIFER, unicode)
    drawing.point(*point(4, -0.7), "<" if int(e.age * 6) % 2 else "{", Ink.ROTIFER, True)
    drawing.point(*point(4, 0.7), ">" if int(e.age * 6) % 2 else "}", Ink.ROTIFER, True)
    drawing.point(*point(-1, 0), "o", Ink.ROTIFER)
    opening = smooth((e.age - 14) / 6) * (1 - smooth((e.age - 48) / 5))
    for side in (-1, 1):
        center = 11, side * (1 + opening * 2.5)
        for index in range(12):
            angle = index * TAU / 12 + e.age * 5
            radius = 0.5 + opening * 1.7
            start = point(
                center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius
            )
            end = point(
                center[0] + math.cos(angle) * (radius + 0.8),
                center[1] + math.sin(angle) * (radius + 0.8),
            )
            drawing.line(*start, *end, Ink.ROTIFER, unicode)
    for meal in e.meals:
        along = 11 - smooth(meal.age / 4) * 13
        drawing.point(
            *point(along, 0), "o" if meal.age < 4 else ":", BACTERIA_INKS[meal.kind], True
        )
    # A blocked visitor can drift out of focus rather than disappear abruptly.
    visible = 1 - smooth((e.age - 85) / 15)
    for y, row in enumerate(drawing.pixels):
        for x, pixel in enumerate(row):
            if pixel.char != " " and (x * 31 + y * 17) % 101 / 101 < visible:
                frame.put(x, y, pixel.char, pixel.ink, pixel.bold)


def _net(frame, world, e, unicode):
    if e.age < 2:
        return
    visible = 1 - smooth((e.age - 45) / 15)
    for start, end in web_segments(e):
        steps = max(1, math.ceil(math.dist(start, end) * 2))
        for index in range(steps + 1):
            t = index / steps
            x, y = start[0] * (1 - t) + end[0] * t, start[1] * (1 - t) + end[1] * t
            col, row = round(x), round(y / ASPECT)
            if (col * 31 + row * 17) % 101 / 101 < visible and next(
                world._obstacles(x, y, 0.1, exempt=e.source), None
            ) is None:
                char = "~" if abs(end[0] - start[0]) > abs(end[1] - start[1]) else ":"
                frame.put(col, row, char, Ink.NET)
    for ident in sorted(e.held):
        bacterium = world.bacteria.get(ident)
        if bacterium is None or not world.events.trapped(bacterium):
            continue
        # Tethers show exactly which swimmers are caught; preserve species hue.
        angle = math.atan2(bacterium.y - e.y, bacterium.x - e.x)
        x, y = bacterium.x + math.cos(angle) * 4, bacterium.y + math.sin(angle) * 4
        frame.line(bacterium.x, bacterium.y, x, y, Ink.NET, unicode)
        copy = Bacterium(
            -1,
            bacterium.x,
            bacterium.y,
            bacterium.angle,
            0,
            bacterium.kind,
            0,
            0,
            units=bacterium.units,
        )
        draw_bacterium(frame, copy, unicode, world.time, compact=True, tail=0)


def _pipette(frame, world, e, unicode):
    ux = math.cos(e.angle)
    outside = world.width + 5 if ux < 0 else -5
    for side in (-1, 1):
        frame.line(outside, e.y + side * 3, e.x, e.y + side * 0.6, Ink.GLASS, unicode)
    frame.point(e.x, e.y, "<" if ux < 0 else ">", Ink.GLASS)
    if e.deposited and 10 <= e.age < 17:
        radius = (e.age - 10) * 0.8
        for index in range(20):
            angle = index * TAU / 20
            x, y = e.x + ux * 3 + math.cos(angle) * radius, e.y + math.sin(angle) * radius
            if next(world._obstacles(x, y, 0.2), None) is None:
                frame.point(x, y, "." if e.age > 14 else "o", Ink.NUTRIENT)
