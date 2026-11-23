"""Pocket's phone home screen and bottom navigation."""
from app_widgets import Canvas
from panel import Panels


class MobilePanels(Panels):
    """Reserve the bottom strip for navigation, including in maximized apps."""
    buttons = (('Home', 'launch:window:Pocket Home'), ('Apps', 'key:,'), ('Windows', 'key:d'))

    def __init__(self):
        super().__init__('bottom')

    def layout(self, columns, rows):
        height = min(3, max(1, rows - 12))
        bar = self.panels[0]
        self.panels = [bar]
        self.selected = bar
        bar.dock = 'bottom'
        bar.rect = (0, rows - height, columns, height)
        bar.cache = None
        self.overlay_bottom = 0
        return 0, 0, columns, rows - height

    def render(self, widgets, states=None, icons=None, sink=None):
        bar = self.panels[0]
        x, top, width, height = bar.rect
        if bar.cache == bar.rect:
            return ''
        bar.cache = bar.rect
        bar.hits = []
        output = []
        for index, (label, action) in enumerate(self.buttons):
            left = width * index // len(self.buttons)
            right = width * (index + 1) // len(self.buttons)
            for row in range(height):
                text = (label if row == height // 2 else '').center(right - left)
                bar.hits.append((left, top + row, right - left, action))
                if sink:
                    sink(left, top + row, text, '97', 24)
                else:
                    output.append(f'\x1b[{top+row+1};{left+1}H\x1b[0;97;48;5;24m{text}')
        return ''.join(output)


class Home:
    navigation_form = None  # The tile grid owns its keyboard and touch navigation.
    favorites = ('Station Map', 'Stations', 'Messages', 'Field Log', 'Field Guide',
                 'Offline Data', 'Phrasebook', 'Connections')

    # Two bitmap rows per text row keep the symbols square in the console font.
    symbols = {
        'Station Map': ('0111110','1100011','1101011','0111110','0011100','0001000'),
        'Stations':    ('0101010','1001001','0101010','0001000','0011100','0110110'),
        'Messages':    ('1111111','1000001','1011101','1000001','1111111','0110000'),
        'Field Log':   ('0111110','1100010','0111010','1100010','0111010','0111110'),
        'Field Guide': ('1100011','1011101','1001001','1001001','1011101','1100011'),
        'Offline Data':('0001000','0001000','0101010','0011100','1001001','1111111'),
        'Phrasebook':  ('0111000','0101000','0111111','0101010','0000100','0001010'),
        'Connections': ('0100010','0100010','1111111','0111110','0001000','0001110'),
    }

    def __init__(self, host, launch):
        self.apps = [name for name in self.favorites if name in host.focus_order]
        self.launch = launch
        self.width, self.height = 40, 16
        self.selected = 0

    def tiles(self):
        columns = 4 if self.width >= 88 else 2
        rows = (len(self.apps) + columns - 1) // columns
        for index, name in enumerate(self.apps):
            row, col = divmod(index, columns)
            left = col * self.width // columns
            right = (col + 1) * self.width // columns
            top = row * self.height // rows
            bottom = (row + 1) * self.height // rows
            yield index, name, left, top, right, bottom

    def lines(self):
        canvas = Canvas(self.width, self.height)
        for index, name, left, top, right, bottom in self.tiles():
            label = ('› ' if index == self.selected else '  ') + name
            middle = (top + bottom - 1) // 2
            if bottom-top >= 6:
                bits = self.symbols[name]
                for i in range(0, len(bits), 2):
                    glyphs = ''.join(' ▄▀█'[2*int(a)+int(b)] for a,b in zip(bits[i],bits[i+1]))
                    canvas.put(left, middle-2+i//2, glyphs.center(right-left), right-left)
                middle += 2
            canvas.put(left, middle, label.center(right-left), right-left)
            for y in range(top, max(top+1,bottom-1)):
                canvas.role(left+1, y, right-left-2, 'selected' if index == self.selected else 'control')
        self.styles = canvas.spans
        return canvas.lines()

    def spans(self):
        return getattr(self, 'styles', ())

    def key(self, key):
        columns = 4 if self.width >= 88 else 2
        delta = {'left':-1, 'right':1, 'up':-columns, 'down':columns, '\t':1, 'backtab':-1}
        if not self.apps:
            return False
        if key in delta:
            self.selected = (self.selected + delta[key]) % len(self.apps)
        elif key in ('\r', '\n'):
            self.launch('window:' + self.apps[self.selected])
        else:
            return False
        return True

    def pointer(self, column, row, width, button=0, released=False):
        if button != 0 or released:
            return False
        for index, name, left, top, right, bottom in self.tiles():
            if left <= column < right and top <= row < bottom:
                self.selected = index
                self.launch('window:' + name)
                return True
        return False
