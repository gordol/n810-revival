"""Explicit RGB colors for the radio applications."""
import atexit
import curses
import sys

COLORS = {
    'background': '0b1015', 'text': 'adb6b5', 'accent': '93cfa5',
    'muted': '6d787b', 'warning': 'c4bf8c', 'water': '193f59',
    'lowland': '142f27', 'foothills': '273d32', 'upland': '3b4635',
    'highland': '4b5553', 'alpine': '6d787b', 'summit': 'adb6b5',
}
SLOTS = {name: 16 + index for index, name in enumerate(COLORS)}
TERRAIN = {name: SLOTS[name] for name in (
    'water','lowland','foothills','upland','highland','alpine','summit','background')}
FALLBACK = {
    'background': curses.COLOR_BLACK, 'text': curses.COLOR_WHITE,
    'accent': curses.COLOR_GREEN, 'muted': curses.COLOR_WHITE,
    'warning': curses.COLOR_YELLOW, 'water': curses.COLOR_BLUE,
    'lowland': curses.COLOR_GREEN, 'foothills': curses.COLOR_GREEN,
    'upland': curses.COLOR_GREEN, 'highland': curses.COLOR_WHITE,
    'alpine': curses.COLOR_WHITE, 'summit': curses.COLOR_WHITE,
}
_active = False


def color(name):
    return SLOTS[name] if _active else FALLBACK[name]


def activate():
    global _active
    if _active or curses.COLORS < 32:
        return
    entries = ';'.join('%d;#%s' % (SLOTS[name], rgb) for name, rgb in COLORS.items())
    sys.stdout.write('\x1b]4;' + entries + '\x1b\\')
    sys.stdout.flush()
    _active = True
    atexit.register(deactivate)


def deactivate():
    global _active
    if not _active:
        return
    sys.stdout.write('\x1b]104;' + ';'.join(map(str, SLOTS.values())) + '\x1b\\')
    sys.stdout.flush()
    _active = False
