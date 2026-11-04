"""Custom compact console icons; explicit font capability, readable fallbacks.

The operator declares compact-v1 only after verifying the active font. TERM,
SSH and geometry do not prove support. Artwork is not official APRS pictograms.
"""
import os
from types import MappingProxyType
from cell_text import single

PROFILE = 'compact-v1'
# Stable ID: (word label, primary one-cell codepoint, single ASCII fallback).
ICONS = MappingProxyType({
    'home': ('Home', 0x2302, 'H'),
    'station': ('Station', 0xe101, 'S'),
    'handheld': ('Handheld', 0xe102, 'R'),
    'car': ('Car', 0xe103, 'C'),
    'person': ('Person', 0xe104, 'P'),
    'digi': ('Digi', 0xe105, 'D'),
    'igate': ('iGate', 0xe106, 'G'),
    'weather': ('Weather', 0x2600, 'W'),
    'object': ('Object', 0xe108, 'O'),
    'waypoint': ('Waypoint', 0xe109, '+'),
    'selected': ('Selected', 0xe10a, '*'),
    'cluster': ('Cluster', 0xe10b, '#'),
    'unknown': ('Unknown', 0xe10c, '?'),
    'mesh-node': ('Mesh node', 0xe10d, 'N'),
    'mesh-relay': ('Mesh relay', 0xe10e, 'R'),
    'room': ('Room', 0xe10f, 'c'),
    'direct': ('Direct', 0xe110, '>'),
    'relayed': ('Relayed', 0xe111, 'r'),
    'dx-spot': ('DX spot', 0xe112, 'D'),
    'beacon': ('Beacon', 0xe113, 'B'),
    'satellite': ('Satellite', 0xe114, 'S'),
    'compass': ('Compass', 0xe115, 'C'),
    'envelope': ('Envelope', 0x2709, 'E'),
    'mailbox': ('Mailbox', 0xe117, 'M'),
    'chat': ('Chat', 0xe118, 'c'),
    'packet': ('Packet', 0xe119, 'P'),
    'feed': ('Feed', 0xe11a, 'F'),
    'directory': ('Directory', 0xe11b, 'D'),
    'gear': ('Gear', 0x2699, 'S'),
    'sliders': ('Sliders', 0xe11d, '='),
    'bluetooth': ('Bluetooth', 0xe11e, 'B'),
    'wifi': ('WiFi', 0xe11f, 'W'),
    'battery': ('Battery', 0xe120, 'B'),
    'power': ('Power', 0x23fb, 'p'),
    'gps-fix': ('GPS fix', 0xe122, 'G'),
    'no-fix': ('No fix', 0xe123, '?'),
    'rx': ('RX', 0xe124, 'R'),
    'tx': ('TX', 0xe125, 'T'),
    'pending': ('Pending', 0xe126, '~'),
    'ack': ('Ack', 0xe127, '+'),
    'failed': ('Failed', 0xe128, '!'),
    'save': ('Save', 0xe129, 'S'),
    'audio': ('Audio', 0xe12a, 'A'),
    'mute': ('Mute', 0xe12b, 'x'),
    'repeater': ('Repeater', 0xe12c, 'R'),
    'link': ('Link', 0xe12d, 'L'),
    'history': ('History', 0xe12e, 'h'),
    'lock': ('Lock', 0xe12f, 'L'),
})


def profile_from_environment():
    """Read at view construction only; no font probing or recurring work."""
    return PROFILE if os.environ.get('N810_ICON_PROFILE') == PROFILE else None


def glyph(identifier, profile=None):
    label, codepoint, fallback = ICONS[identifier]
    char=chr(codepoint)
    # Semantic BMP text is portable when one cell; specialised PUA requires the
    # explicitly verified font capability. Supplementary emoji stay deferred.
    if single(char) and (profile == PROFILE or codepoint < 0xe000):return char
    return fallback


APP_ICONS = MappingProxyType({
    'APRS': 'compass', 'Map': 'compass', 'Messages': 'envelope',
    'Nets': 'room', 'Directory': 'directory', 'Stations': 'station',
    'Services': 'gear', 'Settings': 'gear', 'Radio': 'handheld',
    'Radio Manager': 'handheld', 'Bluetooth': 'bluetooth', 'Feed': 'feed',
    'Radio Feed': 'feed', 'Last Heard': 'history',
})


def app_glyph(title, profile=None, fallback='.'):
    identifier = APP_ICONS.get(title)
    return glyph(identifier, profile) if identifier else fallback


# Direct symbol identities only; no role inferred from station callsigns.
APRS_ICONS = MappingProxyType({
    ('/', '-'): 'home', ('/', '>'): 'car', ('/', '['): 'person',
    ('/', '#'): 'digi', ('/', '_'): 'weather',
    ('/', 'm'): 'repeater', ('/', 'r'): 'repeater',
    ('\\', '-'): 'home', ('\\', '>'): 'car', ('\\', '_'): 'weather',
    ('\\', '/'): 'waypoint', ('\\', 'd'): 'dx-spot',
})


def aprs_display(display, profile=None):
    identifier = APRS_ICONS.get((display.get('base_table'), display.get('code')))
    if not display.get('known') or identifier is None:
        return display
    codepoint=ICONS[identifier][1]
    if profile != PROFILE and codepoint >= 0xe000:return display
    return dict(display, glyph=glyph(identifier, profile), icon_id=identifier,
                glyph_kind='custom_console_approximation' if codepoint >= 0xe000 else 'unicode_terminal_approximation')
