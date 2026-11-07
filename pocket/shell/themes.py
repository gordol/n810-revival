# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Semantic UI themes. Resolve once; rendering never reads configuration files.

A process inherits POCKET_THEME; an explicit --palette wins. Domain colors
(terrain, radio bands, warnings on maps) are deliberately not recolored.
"""
from functools import lru_cache
from collections import namedtuple
from types import MappingProxyType

# background, raised surface, text, muted text, accent, selected background
PRESETS = {
    'light': ('f7f7f2','e4e8e8','253238','56676e','006b80','bddfe7'),
    'dark': ('171a1c','262d31','bec3c3','879497','6ed2dc','284d54'),
    'solarized-light': ('fdf6e3','eee8d5','586e75','657b83','005f87','d6e5df'),
    'solarized-dark': ('002b36','073642','93a1a1','839496','2aa198','164d54'),
    'vibe': ('170e29','2b1742','e6dafa','af9aca','65edce','563579'),
}

def color(value):
    return tuple(int(value[i:i+2],16) for i in (0,2,4))

@lru_cache(maxsize=32)
def roles(name):
    """Immutable role values shared by native and Python compositors."""
    if name not in PRESETS:return None
    bg,surface,text,muted,accent,selected=map(color,PRESETS[name])
    return MappingProxyType(dict(body=(text,bg), panel=(text,surface), toolbar=(text,surface),
                rail=(text,bg), inset=(text,surface), control=(accent,surface),
                tab=(accent,surface), selected=(text,selected), input=(text,surface),
                heading=(accent,bg), accent=(accent,bg), muted=(muted,bg),
                status=(accent,bg), warning=(color('b65b00') if 'light' in name else color('ffc46b'),bg)))

def ansi(rgb):return '38;2;'+';'.join(map(str,rgb))

def palettes():
    return {name:(ansi(roles(name)['body'][0]),ansi(roles(name)['accent'][0]),
                  ansi(roles(name)['muted'][0]),ansi(roles(name)['heading'][0])) for name in PRESETS}

@lru_cache(maxsize=32)
def from_palette(palette):
    return next((name for name,values in palettes().items() if tuple(palette[:4])==values),None)

def window_styles(name,styles,width,height):
    """Give unstyled text the same body material in either compositor."""
    if name not in PRESETS:return styles
    frozen=tuple((row,tuple(spans)) for row,spans in sorted(styles.items()))
    return _window_styles(frozen,width,height)

@lru_cache(maxsize=128)
def _window_styles(frozen,width,height):
    styles=dict(frozen)
    return MappingProxyType({row:((0,max(0,width-2),'body'),)+styles.get(row,()) for row in range(max(0,height-2))})


class ThemeContext(namedtuple('ThemeContextValue','name overrides',defaults=('dark',()))):
    """A child shares its parent's immutable role table until an override exists.

    Contexts are values, not a global mutable registry. Owners publish a new
    context on a theme-change event; children can retain their old value safely.
    """
    __slots__=()

    def __new__(cls,name='dark',overrides=()):
        if name not in PRESETS:raise ValueError('Unknown theme: '+name)
        for role,pair in overrides:
            if role not in roles(name):raise ValueError('Unknown theme role: '+role)
            if len(pair)!=2 or any(len(rgb)!=3 or any(type(v) is not int or not 0<=v<=255 for v in rgb) for rgb in pair):
                raise ValueError('Theme colors require RGB byte triples')
        if not isinstance(overrides,tuple) or any(not isinstance(pair,tuple) or any(not isinstance(rgb,tuple) for rgb in pair) for _,pair in overrides):
            raise ValueError('Theme overrides must be immutable tuples')
        return super().__new__(cls,name,overrides)

    def derive(self, **overrides):
        if not overrides:return self
        values=dict(self.overrides)
        values.update((role,tuple(tuple(rgb) for rgb in pair)) for role,pair in overrides.items())
        return ThemeContext(self.name,tuple(sorted(values.items())))

    @property
    def material(self):return context_roles(self)

@lru_cache(maxsize=64)
def context_roles(context):
    if not context.overrides:return roles(context.name)
    return MappingProxyType(dict(roles(context.name),**dict(context.overrides)))
