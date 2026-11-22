"""Illustrated blood smear shared by the terminal and RGB565 slide views."""
from array import array
from functools import lru_cache
import math
from random import Random
import time

from core import surface_cell
from paint import BOLD_RGB, ink
from vendor.terminal_cells.models import DIVISION_TIME, STEP, State, bacterial_scale, microbe_axes, smooth
from vendor.terminal_cells.render import PALETTES, render
from vendor.terminal_cells.world import World


GLASS = (240, 235, 227)
def rgb565(rgb):
    r, g, b = rgb
    return (r >> 3) << 11 | (g >> 2) << 5 | (b >> 3)


def ramp(stops):
    colors = []
    for i in range(256):
        frac, index = math.modf(i / 255 * (len(stops) - 1))
        a, b = stops[int(index)], stops[min(int(index) + 1, len(stops) - 1)]
        colors.append(rgb565(tuple(round(x + (y-x)*frac) for x,y in zip(a,b))))
    return colors


RED = ramp(((132,65,99), (184,88,116), (216,124,143), (232,155,161),
            (242,188,180), (248,215,195), GLASS))
CYTOPLASM = ramp(((113,93,137), (164,142,172), (200,185,199),
                  (223,211,217), (232,224,225), GLASS))
CHROMATIN = ramp(((49,42,83), (78,52,106), (113,74,139), (150,108,164),
                  (180,147,184)))
PLATELET = ramp(((74,57,108), (127,88,149), (181,152,181), GLASS))
MICROBE = ramp(((45,89,83), (81,137,110), (174,202,158), GLASS))
CLEAR = rgb565(GLASS)


def intensity(palette, value):
    return palette[max(0, min(255, int(value)))]


def grain_grid():
    rng = Random(810)
    return tuple(rng.uniform(-1,1) for _ in range(64*64))


GRAIN = grain_grid()


def grain(x,y):
    """Interpolate a repeatable pigment field in specimen coordinates."""
    ix,iy = math.floor(x), math.floor(y)
    fx,fy = x-ix,y-iy
    i,j = ix & 63,(ix+1) & 63
    a,b = (iy & 63)*64,((iy+1) & 63)*64
    top = GRAIN[a+i] + fx*(GRAIN[a+j]-GRAIN[a+i])
    bottom = GRAIN[b+i] + fx*(GRAIN[b+j]-GRAIN[b+i])
    return top + fy*(bottom-top)


def cell_color(kind, x, y, seed, radius, fill):
    theta = math.atan2(y, x)
    contour = 1 + .026*math.sin(3*theta+seed) + .018*math.cos(5*theta-seed)
    r = math.hypot(x,y) / contour
    if r >= 1:
        return None
    # Sub-pixel variation is anchored to the specimen as the field moves.
    fine = grain(69*x+seed,69*y)
    relief = grain(13*x+seed,13*y)
    if kind == 'red':
        basin = math.hypot(x+.095+.04*math.sin(3*y), (y+.055)*1.08)
        ring = math.exp(-((basin-.70)/.34)**2)
        # Transmitted light, a soft central depression and a narrow dark lip.
        value = 208 - 113*ring - 18*y - 9*x + 11*relief + 8*fine + 8*math.sin(seed)
        value -= 40*math.exp(-((r-.945)/.045)**2)
        if not fill:
            value = 76 if r > .94 or abs(basin-.41)<.034 else 255
        color = intensity(RED,value)
    elif kind == 'body':
        granule = max(0., fine+.25*relief-.38)
        value = 176 + 26*relief - 145*granule - 52*r**8
        color = intensity(CYTOPLASM,value) if fill or r > .94 else CLEAR
    elif kind == 'nucleus':
        color = intensity(CHROMATIN,118+70*relief+47*fine-48*r**3) if fill or r > .86 else CLEAR
    elif kind == 'microbe':
        color = intensity(MICROBE, 90+63*relief+32*fine-47*r**3) if fill or r > .78 else CLEAR
    else:
        color = intensity(PLATELET,55+115*r+40*fine)
    # Feather the last optical sample, including on the coarse terminal grid.
    edge = min(1., (1-r)*radius)
    if edge < 1:
        return blend(color,CLEAR,edge)
    return color


def blend(a,b,weight):
    channels = ((11,31), (5,63), (0,31))
    return sum(round(((a>>shift)&mask)*weight + ((b>>shift)&mask)*(1-weight)) << shift
               for shift,mask in channels)


def specimen(kind, radius, aspect, tilt, seed, fill):
    """Prepaint contiguous scanlines; animation only moves the cached runs."""
    span = math.ceil(radius*1.12)
    cosine, sine = math.cos(tilt), math.sin(tilt)
    strokes = []
    for dy in range(-span,span+1):
        strip = array('H')
        start = 0
        for dx in range(-span,span+1):
            x, y = (dx*cosine+dy*sine)/radius, (dy*cosine-dx*sine)/(radius*aspect)
            color = cell_color(kind,x,y,seed,radius,fill)
            if color is None:
                if strip:
                    strokes.append((start,dy,strip))
                    strip = array('H')
            else:
                if not strip:
                    start = dx
                strip.append(color)
        if strip:
            strokes.append((start,dy,strip))
    return strokes


def projection(width,height,world):
    scale = min(width/world.width,height/world.height)
    return scale,(width-world.width*scale)/2,(height-world.height*scale)/2


def raster(width, height, world, fill, sprite):
    """Project a single world snapshot; rendering never advances the model."""
    field = array('H', [CLEAR]) * (width * height)
    scale, ox, oy = projection(width,height,world)

    def stamp(kind, x, y, size, aspect=1., tilt=0., seed=0):
        cx, cy = round(ox+x * scale), round(oy+y * scale)
        for dx, dy, run in sprite(kind, max(1, round(scale * size)), aspect, tilt, seed, fill):
            row, left = cy + dy, cx + dx
            if 0 <= row < height:
                first, last = max(0, -left), min(len(run), width-left)
                if first < last:
                    base = row * width + left
                    field[base+first:base+last] = run[first:last]

    def line(x, y, xx, yy, color, keep=None):
        x,y,xx,yy = round(ox+x*scale),round(oy+y*scale),round(ox+xx*scale),round(oy+yy*scale)
        steps = max(1, abs(xx-x), abs(yy-y))
        for n in range(steps + 1):
            px, py = x + (xx-x)*n//steps, y + (yy-y)*n//steps
            if 0 <= px < width and 0 <= py < height and (
                    keep is None or keep((px-ox)/scale, (py-oy)/scale)):
                field[py*width+px] = color

    def microbe(b, captured=False):
        a, minor = microbe_axes(b)
        tilt = round(b.angle / math.tau * 16) % 16 * math.tau / 16
        ux, uy = math.cos(b.angle), math.sin(b.angle)
        size = min(.65, 2.2/a) if captured else bacterial_scale(b)

        def point(along, across):
            return b.x+size*(ux*along-uy*across), b.y+size*(uy*along+ux*across)

        def body(along, across, radius, aspect=1.):
            stamp('microbe', *point(along,across), radius*size, aspect, tilt, b.id % 5)

        if b.kind == 'colony':
            body(0,0,1.35)
            for i in range(b.units):
                angle = i*math.tau/b.units
                body(3.1*math.cos(angle),3.1*math.sin(angle),1.35)
        elif b.kind == 'bacillus':
            for i in range(b.units):
                body((i-(b.units-1)/2)*3.4,0,2.3,.72)
        elif b.kind in ('spiral','spirochete'):
            for i in range(31):
                t = i/30
                body((2*t-1)*a,1.2*math.sin(t*math.tau*2-world.time*5+b.id),.58)
        else:
            body(0,0,3.3 if b.kind=='yeast' else a, minor/a)
            if b.bud:
                body(3.2+b.bud*1.8,0,.4+2*b.bud)
        if not captured and b.kind in ('rod','vibrio','trypanosome'):
            previous = point(-a,0)
            for i in range(1,13):
                t = i/12
                tip = point(-a-t*5,t*math.sin(8*t-world.time*7+b.id))
                if next(world._obstacles(*tip, 1.1), None) is not None:
                    break
                line(*previous,*tip,MICROBE[48])
                previous = tip
        if b.infection:
            stamp('nucleus', b.x, b.y, .75)

    for hypha in world.hyphae:
        for a, b in hypha.edges:
            line(*hypha.nodes[a], *hypha.nodes[b], rgb565((113, 133, 91)))
    for patch in world.nutrients:
        stamp('platelet', patch.x, patch.y, min(1.5, patch.amount * .4))
    for d in world.debris:
        stamp('platelet', d.x, d.y, d.size * .65)
    for red in world.red_cells:
        stamp('red', red.x, red.y, red.size, .8, red.phase)
    captured = {c.target for c in world.cells if c.state is State.ENCLOSE}
    for b in world.bacteria.values():
        if b.id not in captured:
            microbe(b)
    for cell in world.cells:
        # Each scanline follows the engine's collision envelope, including the
        # reaching arm, capture pocket and the waist between dividing daughters.
        points = []
        for i in range(96):
            angle = math.tau * i / 96
            r = cell.outline(angle, world.time)
            points.append((ox+(cell.x + r*math.cos(angle))*scale,
                           oy+(cell.y + r*math.sin(angle))*scale))
        rows = {}
        for (x, y), (xx, yy) in zip(points, points[1:] + points[:1]):
            for row in range(max(0, math.ceil(min(y,yy))), min(height, math.ceil(max(y,yy)))):
                rows.setdefault(row, []).append(round(x + (row-y)*(xx-x)/(yy-y)))
        radius = max(1, round(cell.radius * scale))
        texture = sprite('body', radius, 1., 0., cell.id % 5, fill)
        top = min(rows, default=0)
        depth = max(1, max(rows, default=0) - top)
        for row, edges in rows.items():
            edges.sort()
            source = texture[(row-top)*(len(texture)-1)//depth][2]
            for left, right in zip(edges[::2], edges[1::2]):
                lo, hi = max(0,left), min(width,right+1)
                if hi > lo:
                    span = right-left+1
                    field[row*width+lo:row*width+hi] = array('H', (
                        source[(x-left)*len(source)//span] for x in range(lo,hi)))
        division = (smooth((cell.elapsed-26)/(DIVISION_TIME-26))
                    if cell.state is State.DIVIDE else 0)
        ux, uy = math.cos(cell.division_angle), math.sin(cell.division_angle)

        def inside(wx, wy, cell=cell):
            dx, dy = wx-cell.x, wy-cell.y
            return math.hypot(dx,dy) < cell.outline(math.atan2(dy,dx), world.time) - 1.1

        for net in cell.organelles:
            sides, nodes = [], []
            for x,y in net.nodes:
                side = 1 if x*ux + y*uy >= 0 else -1
                sides.append(side)
                nodes.append((cell.x + (x*(1-.28*division) + side*ux*.62*division)*cell.radius,
                              cell.y + (y*(1-.28*division) + side*uy*.62*division)*cell.radius))
            for a,b in net.edges:
                if cell.state is State.DIVIDE and cell.elapsed >= 40 and sides[a] != sides[b]:
                    continue
                line(*nodes[a], *nodes[b], CYTOPLASM[102], inside)
        if cell.kind == 'neutrophil':
            for dx,dy in ((-.28,-.12),(0,.12),(.28,-.12)):
                stamp('nucleus', cell.x+dx*cell.radius, cell.y+dy*cell.radius, cell.radius*.19)
        elif cell.state is State.DIVIDE:
            separation = smooth((cell.elapsed-20)/(DIVISION_TIME-20))
            for sign in (-1,1):
                distance = sign * separation * cell.radius * .68
                stamp('nucleus', cell.x+distance*math.cos(cell.division_angle),
                      cell.y+distance*math.sin(cell.division_angle), cell.radius*(.3-.09*separation))
        else:
            stamp('nucleus', cell.x-.22*cell.radius*math.cos(cell.phase),
                  cell.y-.22*cell.radius*math.sin(cell.phase), cell.radius*.31, .84, cell.phase)
        if cell.state is State.ENCLOSE and cell.target in world.bacteria:
            microbe(world.bacteria[cell.target], captured=True)
        for v in cell.vesicles:
            stamp('microbe', cell.x+cell.radius*v.distance*math.cos(v.angle),
                  cell.y+cell.radius*v.distance*math.sin(v.angle), max(.6,2-v.age*.09))
    for p in (*world.phages.values(), *world.spent_capsids):
        stamp('platelet', p.x, p.y, .85)
        line(p.x,p.y,p.x+2*math.cos(p.angle),p.y+2*math.sin(p.angle),PLATELET[40])
    for burst in world.bursts:
        for i in range(8):
            a = burst.angle + math.tau*i/8
            d = 2+burst.age*9
            if next(world._obstacles(burst.x+d*math.cos(a), burst.y+d*math.sin(a), 1.1), None) is not None:
                continue
            stamp('platelet',burst.x+d*math.cos(a),burst.y+d*math.sin(a),.45)
    return field


GLYPH_FALLBACK = {'≋': '~', 'ᛘ': 'Y', 'ᛦ': 'Y', '·': '.', '•': '*', '●': 'O',
                  '│': '|', '─': '-', '░': ':'}


def ansi_rgb(index):
    if index >= 232:
        return (8 + 10*(index-232),) * 3
    if index < 16:
        return (0,0,0) if index == 0 else (255,255,255)
    levels = (0,95,135,175,215,255)
    value = index - 16
    return levels[value//36], levels[value//6%6], levels[value%6]


@lru_cache(maxsize=2048)
def glyph_cell(char, foreground, bg, bold):
    palette = PALETTES['light']
    fg = ansi_rgb(palette[foreground.value-1][0])
    return surface_cell(char, ink(*fg,bg) | (BOLD_RGB if bold else 0))


# The eight bits in a mask describe two columns by four rows inside one glyph.
# Solid block glyphs preserve contiguous stain even on a bitmap terminal.
MASKS = ((0,' '),(15,'▀'),(192,'▂'),(240,'▄'),(252,'▆'),
         (85,'▌'),(170,'▐'),(5,'▘'),(10,'▝'),(80,'▖'),(160,'▗'),
         (165,'▚'),(90,'▞'),(95,'▛'),(175,'▜'),(245,'▙'),(250,'▟'))


@lru_cache(maxsize=4096)
def components(value):
    return ((value>>11)*255//31, ((value>>5)&63)*255//63, (value&31)*255//31)


@lru_cache(maxsize=256)
def block_for(mask):
    return min(((bits ^ flip, ch, bool(flip)) for bits,ch in MASKS for flip in (0,255)),
               key=lambda entry: (entry[0]^mask).bit_count())


@lru_cache(maxsize=8192)
def stain_tile(samples, blocks):
    colors = [components(value) for value in samples]
    if samples.count(samples[0]) == 8:
        color = colors[0]
        return surface_cell(' ',ink(*color,color))
    light = [sum(c) for c in colors]
    threshold = (min(light)+max(light))/2
    mask = sum(1<<i for i,v in enumerate(light) if v<threshold)
    bits,char,reverse = block_for(mask) if blocks else (0,' ',False)
    def mean(selected):
        return tuple(round(sum(c[i] for c in selected)/len(selected)) for i in range(3))
    a = mean([c for i,c in enumerate(colors) if bits & (1<<i)] or colors)
    b = mean([c for i,c in enumerate(colors) if not bits & (1<<i)] or colors)
    fg,bg = (b,a) if reverse else (a,b)
    return surface_cell(char,ink(*fg,bg))


def terminal_slide(width,height,world,fill,sprite,ascii_mode,glyphs):
    # Physical character cells have an approximately 1:2 aspect ratio.
    # Four vertical samples and two horizontal samples are therefore square.
    stride = width*2
    field = raster(stride,height*4,world,fill,sprite)
    blocks = not ascii_mode and all(glyphs.cell(ch)==ch for _,ch in MASKS)
    cells = []
    for y in range(height):
        for x in range(width):
            i = y*4*stride+x*2
            samples = tuple(field[i+row*stride+col] for row in range(4) for col in range(2))
            cells.append(stain_tile(samples,blocks))

    # Overlay the original anatomical marks in specimen coordinates. Their
    # ink follows the feature and each stain underneath supplies its background.
    scale,ox,oy = projection(width,height*2,world)
    frame = render(world,unicode=not ascii_mode,fill=fill)
    for y,row in enumerate(frame.pixels):
        for x,pixel in enumerate(row):
            if pixel.char in (' ','░') or (fill and pixel.char not in '≋~o●O•*YᛘᛦX:'):
                continue
            col = int(ox+(x+.5)*scale)
            line = int((oy+(2*y+1)*scale)/2)
            if not (0<=col<width and 0<=line<height):
                continue
            char = glyphs.cell(pixel.char,ascii_mode)
            if char=='?':
                char = GLYPH_FALLBACK.get(pixel.char,char)
            pos = line*width+col
            center = field[(4*line+2)*stride+2*col+1]
            color = glyph_cell(char,pixel.ink,components(center),pixel.bold)
            cells[pos] = color
    return (0,0,width,height,tuple(cells))


class Cells:
    name = "Cells"
    layer_only = True
    dispose_on_close = True

    def __init__(self, host):
        self.host = host
        self.sprite = lru_cache(maxsize=48)(specimen)
        self.pixel_view = self.closed = False
        self.pixel_frames = self.pixel_jobs = 0
        self.width, self.height = 88, 25
        self.world = World(self.width, self.height-1, 810,
                           rare_events=False, microscope_events=False)
        self.tick = 0
        self.deadline = 0.
        self.playing = True
        self.fill = True
        self.frame_key = self.frame = None

    def poll_interval(self):
        if self.closed:
            return None
        window = self.host.window('Cells')
        if self.playing and self.host.shown(window) and not window.rolled:
            return max(0., self.deadline - time.monotonic())
        return None

    def poll(self):
        if self.poll_interval() == 0:
            for _ in range(5):
                self.world.update(STEP)
            self.tick += 1
            self.deadline = time.monotonic() + 1 / 6

    def layer(self):
        if self.pixel_view:
            return None
        w, h = self.width, max(1,self.height-1)
        key = (w,h,self.tick,self.fill,self.host.ascii,self.host.glyphs.key)
        if self.frame_key != key:
            self.frame = terminal_slide(w,h,self.world,self.fill,self.sprite,self.host.ascii,self.host.glyphs)
            self.frame_key = key
        return self.frame

    def pixel_key(self):
        _,_,w,h = self.host.bounds(self.host.window(self.name))
        return max(1,w-2)*8, max(1,h-3)*16, self.tick, self.fill

    @property
    def pixel_dirty(self):
        return not self.closed and self.frame_key != self.pixel_key()

    @pixel_dirty.setter
    def pixel_dirty(self, value):
        if value:
            self.frame_key = None

    def render_image(self):
        if self.closed:
            return None
        key = self.pixel_key()
        width,height,tick,fill = key
        if key != self.frame_key:
            self.frame = raster(width,height,self.world,fill,self.sprite).tobytes()
            self.frame_key = key
            self.pixel_frames += 1
        x,y,_,_ = self.host.bounds(self.host.window(self.name))
        ox,oy = self.host.origin
        return self.frame,(x+ox+1)*8,(y+oy+1)*16,width,height

    def lines(self):
        if self.closed:
            return ()
        action = 'pause' if self.playing else 'resume'
        return ('',) * (self.height - 1) + (f'Space {action}   F fill   Engulfed {self.world.engulfed}   Divisions {self.world.divisions}',)

    def key(self, key):
        if key in (' ', 'space'):
            self.playing = not self.playing
        elif key.lower() == 'f':
            self.fill = not self.fill
        else:
            return False
        return True

    def close(self):
        self.closed = True
        self.sprite.cache_clear()
        for cache in (stain_tile, glyph_cell, block_for, components):
            cache.cache_clear()
        self.world = self.frame = self.frame_key = None


def descriptor():
    return dict(id='cells', title='Cells', factory=Cells, category='Experiments',
                preferred_size=(90, 27), minimum_size=(24, 10),
                description='Watch immune cells chase microbes, engulf them and divide.',
                help=(('Cells', ('Immune cells hunt microbes. The counters track captures and cell divisions.',
                                 'Space pauses the simulation. F toggles stain. Powered by kborer/cells (0BSD).')),))
