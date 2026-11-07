"""Compact RGB inks and retained static/dynamic scene layers."""
from functools import lru_cache
from collections.abc import Mapping
import themes


def rgb(r,g,b):
    r,g,b=(max(0,min(255,v)) for v in (r,g,b))
    r=round(round(r*31/255)*255/31)
    g=round(round(g*63/255)*255/63)
    b=round(round(b*31/255)*255/31)
    return (r<<16)|(g<<8)|b


def ink(r,g,b,background=None):
    color=rgb(r,g,b)
    return (1<<24)|color if background is None else (1<<48)|(color<<24)|rgb(*background)


# Preserve the terminal's palette foreground while carrying an RGB background.
# Low RGB channels retain an approximation for any later alpha operation.
FRAME_INK=1<<49
FRAME_ROLE_SHIFT=50
FRAME_TINTED=1<<52
FRAME_DEFERRED=1<<55


def valid_ink(color,deferred=False):
    if not isinstance(color,int) or color<0:return False
    if color<1<<49:return True
    allowed=(1<<48)-1|(1<<48)|FRAME_INK|(3<<FRAME_ROLE_SHIFT)|FRAME_TINTED|(FRAME_DEFERRED if deferred else 0)
    return bool(color&FRAME_INK and color&(1<<48) and (color>>FRAME_ROLE_SHIFT)&3 in (1,2) and not color&~allowed)


@lru_cache(maxsize=128)
def frame_template(role,palette,tinted=True):
    if role not in (1,2):raise ValueError('frame role must be focused or inactive')
    code=palette[role];parts=tuple(map(int,code.split(';')))
    if parts[:2]==(38,2):fore=parts[2:5]
    else:
        ansi=((0,0,0),(170,0,0),(0,170,0),(170,85,0),(0,0,170),(170,0,170),(0,170,170),(170,170,170),
              (85,85,85),(255,85,85),(85,255,85),(255,255,85),(85,85,255),(255,85,255),(85,255,255),(255,255,255))
        value=parts[0];index=value-30 if 30<=value<=37 else value-90+8
        fore=ansi[index]
    return FRAME_DEFERRED|FRAME_INK|(role<<FRAME_ROLE_SHIFT)|(FRAME_TINTED if tinted else 0)|ink(*fore,background=(0,0,0))


@lru_cache(maxsize=128)
def chrome_ink(role,palette,tinted=True):
    """Opaque window chrome, independent of imagery beneath the window."""
    template=frame_template(role,palette,tinted)
    name=themes.from_palette(palette)
    back=themes.roles(name)['panel' if role==1 else 'body'][1] if name else (38,30,48) if role==1 else (24,28,32)
    return (template&~(FRAME_DEFERRED|0xffffff))|rgb(*back)


@lru_cache(maxsize=4096)
def frame_ink(template,char,color,tinted=True):
    if color>=1<<48:
        fore=tuple((color>>shift)&255 for shift in (40,32,24))
        back=tuple((color>>shift)&255 for shift in (16,8,0))
        channels=tuple((a+b)/2 for a,b in zip(fore,back)) if char in ('▄','▀') else fore if char=='█' else back
    else:
        value=8 if color==14 else 10 if color>=4 and tinted else 18
        channels=(value,)*3
    return (template&~(FRAME_DEFERRED|0xffffff))|rgb(*channels)


@lru_cache(maxsize=2048)
def foreground(color,palette):
    if color&FRAME_INK:return palette[(color>>FRAME_ROLE_SHIFT)&3]
    if color<(1<<24):return palette[color]
    value=(color>>24)&0xffffff if color>=(1<<48) else color
    return f'38;2;{(value>>16)&255};{(value>>8)&255};{value&255}'


def background(color,fallback):
    if color<(1<<48):return fallback
    return f'2;{(color>>16)&255};{(color>>8)&255};{color&255}'


NATIVE_SCENES=None


class Scene(Mapping):
    """Shared static plane plus a small replacing overlay."""
    def __init__(self,base,overlay):self.base,self.overlay=base,overlay
    def __getitem__(self,key):
        # Mapping.__contains__ fetches the value itself. Native overlays would
        # otherwise cross the extension boundary and construct each cell twice.
        try:return self.overlay[key]
        except KeyError:return self.base[key]
    def __iter__(self):
        yield from self.base
        yield from (key for key in self.overlay if key not in self.base)
    def __len__(self):return len(self.base)+sum(key not in self.base for key in self.overlay)
    def __bool__(self):
        return bool(self.base) or bool(self.overlay)


SCENE_ROLES={4:(0,70,25),5:(65,68,65),6:(0,125,50),7:(145,78,110),
             8:(160,130,55),9:(35,85,100),10:(145,165,168),11:(95,105,108),12:(35,110,70)}


def inherit_background(color,under):
    if color==14 or color>=(1<<48):return color
    if color>=(1<<24):fg=((color>>16)&255,(color>>8)&255,color&255)
    else:fg=SCENE_ROLES.get(color,(150,155,150))
    bg=((under>>16)&255,(under>>8)&255,under&255) if under>=(1<<48) else (10,10,10)
    return ink(*fg,background=bg)


@lru_cache(maxsize=2048)
def terminal_background(char,color,under_char,under,opacity):
    """Blend the background, keeping the terminal's foreground at full strength."""
    if opacity>=1:return char,color
    if under<1<<48:
        base=SCENE_ROLES.get(under,(18,18,18))
        under=ink(*base,background=(18,18,18))
    bg=color&0xffffff
    def blend(source):
        return rgb(*(round(((bg>>shift)&255)*opacity+((source>>shift)&255)*(1-opacity)) for shift in (16,8,0)))
    if char==' ':
        fg,bg=blend((under>>24)&0xffffff),blend(under&0xffffff)
        # Equal half-block colors are a plain background, not a text glyph.
        glyph=' ' if under_char in ('▄','▀') and fg==bg else under_char
        return glyph,(1<<48)|(fg<<24)|bg
    if under_char in ('▄','▀'):
        channels=[round((((under>>(shift+24))&255)+((under>>shift)&255))/2) for shift in (16,8,0)]
        base=(channels[0]<<16)|(channels[1]<<8)|channels[2]
    else:base=under&0xffffff
    return char,(color&~0xffffff)|blend(base)


@lru_cache(maxsize=4096)
def shade_ink(color,strength=.4):
    """Darken both halves of an RGB cell without changing its glyph."""
    if strength<=0:return color
    if color<(1<<48):
        if color not in SCENE_ROLES:return 14
        scale=1-strength
        return ink(*(v*scale for v in SCENE_ROLES[color]),background=(10*scale,)*3)
    fg=((color>>40)&255,(color>>32)&255,(color>>24)&255)
    bg=((color>>16)&255,(color>>8)&255,color&255)
    scale=1-strength
    return ink(*(v*scale for v in fg),background=tuple(v*scale for v in bg))


@lru_cache(maxsize=4096)
def pane_ink(color,opacity):
    """Shade filled RGB cells without turning their half-blocks into gray bars."""
    if color<(1<<48):return 15 if opacity else color
    fg=((color>>40)&255,(color>>32)&255,(color>>24)&255)
    bg=((color>>16)&255,(color>>8)&255,color&255)
    def blend(channels):return tuple(v*(1-opacity)+24*opacity for v in channels)
    return ink(*blend(fg),background=blend(bg))


@lru_cache(maxsize=4096)
def window_text_ink(under):
    """Keep text legible; approximate the two scene halves under its glyph."""
    top=((under>>40)&255,(under>>32)&255,(under>>24)&255)
    bottom=((under>>16)&255,(under>>8)&255,under&255)
    return ink(195,199,195,background=tuple((a+b)/2 for a,b in zip(top,bottom)))


@lru_cache(maxsize=4096)
def window_pane_ink(color,opacity):
    if color<(1<<48):
        base=SCENE_ROLES.get(color,(10,10,10))
        color=ink(*base,background=base)
    return pane_ink(color,opacity)


@lru_cache(maxsize=128)
def control_ink(role,palette,focused=True):
    if role=='obstruction':return ink(255,255,255,background=(170,35,25))
    material=palette.material if isinstance(palette,themes.ThemeContext) else themes.roles(palette)
    if material and role=='caret':
        fg,bg=material['body'];return ink(*bg,background=fg)
    if material and role in material:
        fg,bg=material['body' if role=='selected' and not focused else role]
        return ink(*fg,background=bg)
    accent={'ice':(110,210,220),'amber':(230,185,95),'paper':(190,195,190),'violet':(175,145,220),'rose':(225,140,160),'ocean':(110,165,220)}.get(palette,(110,210,220))
    map_roles={'map':((90,125,110),(10,19,17)),'water':((80,145,180),(10,19,17)),'terrain':((90,140,100),(10,19,17)),'road':((175,155,100),(10,19,17)),'station':((245,210,110),(10,19,17))}
    if role in map_roles:
        fg,bg=map_roles[role];return ink(*fg,background=bg)
    surfaces={'panel':(25,31,34),'rail':(17,22,25),'inset':(32,40,44),'toolbar':(38,45,49)}
    if role in surfaces:return ink(195,204,205,background=surfaces[role])
    bg=(23,26,28);fg=(190,195,195)
    if role=='caret':return ink(23,26,28,background=accent)
    if role in ('selected','input'):
        bg=tuple(18+v*(.22 if focused else .10) for v in accent);fg=(240,243,240)
    elif role=='match':bg=(66,56,30);fg=(255,244,185)
    elif role in ('control','tab'):bg=(33,38,40);fg=accent
    elif role in ('heading','accent'):fg=accent
    elif role=='warning':fg=(225,180,105)
    elif role=='status':fg=(140,190,165)
    elif role=='muted':fg=(120,130,133)
    return ink(*fg,background=bg)
