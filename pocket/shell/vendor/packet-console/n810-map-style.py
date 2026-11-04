"""Shared terminal map palette, relief shading and high-contrast markers."""
import curses
colored=False

def ink(number):
    return curses.color_pair(number) if colored and number<curses.COLOR_PAIRS else 0


def init_screen(win):
    global colored
    colored=False
    if not curses.has_colors():return
    curses.start_color()
    if curses.COLORS<8:return
    bright=curses.COLORS>=16
    for number,foreground,background in ((1,7,0),(2,7,0),(3,3,0),(4,2,0),(5,5,4),(6,4,0),(7,0,11 if bright else 3),(72,15 if bright else 7,0),(73,0,10 if bright else 2)):
        if number<curses.COLOR_PAIRS:curses.init_pair(number,foreground,background)
    terrain=[4,2,1,3,5,6,7,0]
    relief=[4,0,8 if bright else 0,7,15 if bright else 7,7,7,0]
    for base,shades in ((8,terrain),(80,relief)):
        for top in range(8):
            for bottom in range(8):
                number=base+top*8+bottom
                if number<curses.COLOR_PAIRS:curses.init_pair(number,shades[top],shades[bottom])
    colored=True;win.bkgd(' ',ink(1))


def cell_attr(kind,terrain=True):
    if kind.startswith(('tone','relief')):
        top,bottom=map(int,kind[-2:]);base=80 if kind.startswith('relief') else 8
        if not terrain:top=0 if top==0 else 7;bottom=0 if bottom==0 else 7;base=8
        return ink(base+top*8+bottom)
    if kind=='road':return ink(2)|curses.A_DIM
    return ink(5 if kind=='fill' else 6 if kind=='half' else 2)
