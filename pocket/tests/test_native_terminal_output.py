"""Check terminal state, rather than requiring redundant byte sequences."""
from array import array
from pathlib import Path
import os, random, re, sys, unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shell'))
from native_cells import load
from native_runtime import select
from paint import FRAME_INK


def rendered(text):
    x = y = 0
    fg = bg = None
    bold = underline = reverse = False
    cells = {}
    for token in re.findall(r'\x1b\[[0-9;]*[HCm]|[^\x1b]', text):
        if token.startswith('\x1b['):
            values = [int(v or 0) for v in token[2:-1].split(';')]
            if token.endswith('C'):
                x += values[0] or 1
                continue
            if token.endswith('H'):
                y, x = values[0]-1, values[1]-1
                continue
            i = 0
            while i < len(values):
                v = values[i]
                if v == 0: fg = bg = None; bold = underline = reverse = False
                elif v == 1: bold = True
                elif v == 4: underline = True
                elif v == 7: reverse = True
                elif v in (38,48):
                    assert values[i+1] == 2
                    rgb = tuple(values[i+2:i+5]); i += 4
                    if v == 38: fg = rgb
                    else: bg = rgb
                else: raise AssertionError(v)
                i += 1
        else:
            cells[x,y] = (token, fg, bg, bold, underline, reverse)
            x += 1
    return cells


def ink(fg, bg):
    return (1<<48) | (fg<<24) | bg


def escape(value):
    channels = [(value>>s)&255 for s in (40,32,24,16,8,0)]
    return '\x1b[0;38;2;%s;48;2;%sm' % (';'.join(map(str,channels[:3])), ';'.join(map(str,channels[3:])))


class NativeTerminalOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = os.environ.get('POCKET_TEST_NATIVE') or select(build=False)['library']
        if not path: raise unittest.SkipTest('native build unavailable')
        cls.lib = load(path)

    def test_rgb_components_styles_gaps_and_external_writes(self):
        rng = random.Random(817)
        frame_color = FRAME_INK | (1<<50) | ink(0xc86432,0x070809)
        colors = [ink(0x123456,0xabcdef), ink(0x123456,0x010203),
                  ink(0xffffff,0x010203), ink(0x040506,0x070809), 1, frame_color]
        styles = ((1, '\x1b[0;1;4;7;38;2;200;100;50;48;2;4;5;6m'),)
        for batch in (1,7,64,140,'budget'):
            front = self.lib.surface(20,7); plane = self.lib.surface(20,7)
            actual = expected = ''
            for frame in range(4):
                indices = sorted(rng.sample(range(140),110))
                values = {i:rng.choice(colors) for i in indices}
                for i,v in values.items(): self.lib.set(plane,i,ord('A')+frame,v)
                # Fresh fronts ensure every selected cell is emitted.
                front = self.lib.surface(20,7)
                size = 140 if batch == 'budget' else batch
                for offset in range(0,len(indices),size):
                    dirty = indices[offset:offset+size]
                    external = '\x1b[9;1H\x1b[0;1;4;7;38;2;9;8;7;48;2;6;5;4m!'
                    actual += external; expected += external
                    args = (front,((plane,0,0),),array('I',dirty),styles,2,1)
                    if batch == 'budget':
                        out, count, computed = self.lib.flush_budget(*args,None,1.)
                        self.assertEqual(computed,len(dirty))
                    else: out, count = self.lib.flush(*args)
                    self.assertEqual(count,len(dirty)); actual += out
                    for i in dirty:
                        v = values[i]
                        expected += '\x1b[%d;%dH' % (i//20+2,i%20+3)
                        style = styles[0][1] if v == 1 else ('\x1b[0;1;4;7;38;2;200;100;50;48;2;7;8;9m' if v == frame_color else escape(v))
                        expected += style + chr(ord('A')+frame)
                # Each dirty cell is written once per frame. Check after every
                # frame, avoiding quadratic re-parsing after each one-cell batch
                # on the physical N810 while still checking all transitions.
                self.assertEqual(rendered(actual),rendered(expected))

    def test_unchanged_components_are_omitted(self):
        plane=self.lib.surface(3,1); front=self.lib.surface(3,1)
        for i,v in enumerate((ink(0x123456,0x010203),ink(0x123456,0x040506),ink(0xabcdef,0x040506))):
            self.lib.set(plane,i,ord('X'),v)
        out,count=self.lib.flush(front,((plane,0,0),),array('I',range(3)),(),0,0)
        self.assertEqual(count,3)
        self.assertIn('X\x1b[48;2;4;5;6mX\x1b[38;2;171;205;239mX',out)
        self.assertEqual(out.count('\x1b[0;'),1)

if __name__ == '__main__': unittest.main()
