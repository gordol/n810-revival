"""Read-only feedback for experimental tools; uses existing semantic colors."""

import math

from .models import TAU, smooth
from .render import BACTERIA_INKS, Ink


def draw_lab(frame, world, unicode):
    for pulse in world.lab.stirs:
        radius = 3 + pulse.age * 5
        for index in range(8):
            angle = index * TAU / 8 + pulse.age * 2
            x, y = pulse.x + math.cos(angle) * radius, pulse.y + math.sin(angle) * radius
            if next(world._obstacles(x, y, 0.2), None) is None:
                frame.point(x, y, "." if pulse.age > 2 else "~", Ink.MUTED)
    for pulse in world.lab.pings:
        for index in range(12):
            angle = index * TAU / 12
            radius = 1 + pulse.age * 3
            x, y = pulse.x + math.cos(angle) * radius, pulse.y + math.sin(angle) * radius
            if next(world._obstacles(x, y, 0.2), None) is None:
                frame.point(x, y, "o" if pulse.age < 0.3 else ".", Ink.NUTRIENT)
    for effect in world.lab.ruptures:
        target, obj = effect.target, effect.target.obj
        visible = 1 - smooth((effect.age - 3) / 4)
        if target.kind == "red":
            for index in range(48):
                if (index * 17) % 49 / 49 > visible:
                    continue
                angle = index * TAU / 48
                frame.point(
                    effect.x + math.cos(angle) * effect.size,
                    effect.y + math.sin(angle) * effect.size * 0.8,
                    "." if effect.age > 3 else ":",
                    Ink.RED_DIM,
                )
        for index, piece in enumerate(effect.fragments):
            if (index * 17) % 23 / 23 > visible:
                continue
            if piece.role == "microbe":
                ink = BACTERIA_INKS[obj.kind]
            else:
                ink = {
                    "membrane": Ink.MEMBRANE
                    if getattr(obj, "kind", "") != "neutrophil"
                    else Ink.NEUTROPHIL,
                    "nucleus": Ink.NUCLEUS,
                    "mitochondrion": Ink.MITOCHONDRION,
                    "reticulum": Ink.RETICULUM,
                    "vesicle": Ink.VESICLE,
                    "red": Ink.RED,
                    "red_dim": Ink.RED_DIM,
                    "phage": Ink.PHAGE,
                    "microbial_dna": Ink.MICROBIAL_DNA,
                    "fungus": Ink.FUNGUS,
                }[piece.role]
            frame.point(piece.x, piece.y, piece.char if effect.age < 4 else ".", ink)
