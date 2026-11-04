"""Opt-in APRS TUI terrain palette and panel treatment."""

WATER = (20, 76, 112)
LAND = (43, 79, 52)
LOW = (36, 82, 52)
HIGH = (167, 166, 107)
NODATA = (33, 38, 49)
REGIONAL = (WATER, (45, 91, 55), (95, 116, 61), (152, 130, 71),
            (157, 142, 114), (179, 181, 169), (221, 227, 220), NODATA)

PANEL_TINT = (10, 18, 24)
PANEL_OPACITY = .74
BACKPLATE = (7, 13, 18)
SELECTION_TEXT = (240, 247, 250)
SELECTION_FILL = (26, 77, 116)
LIVE = (93, 201, 224)
SUBMITTED = (232, 175, 77)
FAULT = (234, 100, 105)


def blend(a, b, fraction):
    return tuple(round(x + (y - x) * fraction) for x, y in zip(a, b))


def band_color(height, low, high):
    return blend(LOW, HIGH, max(0, min(1, (height - low) / max(5, high - low))))
