# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Supplement the console font with build-time native Mac UI glyphs."""
from pathlib import Path
import struct

def box_glyphs(font):
    """One-pixel GUI strokes, with shared joins at x=3/y=7 in 8x16 cells.

    Console fonts may mix two-pixel verticals with one-pixel rounded corners.
    These geometric UI glyphs belong to the pixel frontend, not the terminal's
    font or its text/terrain bitmaps.
    """
    joins={'─':'lr','│':'ud','┌':'rd','┐':'ld','└':'ru','┘':'lu',
           '├':'urd','┤':'uld','┬':'lrd','┴':'lru','┼':'lrud'}
    shapes={}
    for ch,directions in joins.items():
        points={(3,7)}
        if 'l' in directions:points.update((x,7) for x in range(4))
        if 'r' in directions:points.update((x,7) for x in range(3,8))
        if 'u' in directions:points.update((3,y) for y in range(8))
        if 'd' in directions:points.update((3,y) for y in range(7,16))
        shapes[ch]=points
    shapes['╭']={(x,7) for x in range(5,8)}|{(4,8)}|{(3,y) for y in range(9,16)}
    shapes['╮']={(x,7) for x in range(2)}|{(2,8)}|{(3,y) for y in range(9,16)}
    shapes['╰']={(3,y) for y in range(6)}|{(4,6)}|{(x,7) for x in range(5,8)}
    shapes['╯']={(3,y) for y in range(6)}|{(2,6)}|{(x,7) for x in range(2)}
    shapes['┄']={(x,7) for x in range(8) if x%4<3}
    shapes['┆']={(3,y) for y in range(16) if y%6<4}
    glyphs=list(font.glyphs)
    for ch,points in shapes.items():
        bits=bytes(sum(128>>x for x,y in points if y==row) for row in range(16))
        if ch not in font.mapping or any(other!=ch and index==font.mapping[ch] for other,index in font.mapping.items()):
            font.mapping[ch]=len(glyphs);glyphs.append(bits)
        else:glyphs[font.mapping[ch]]=bits
    font.glyphs=tuple(glyphs)

def load(path,mode='console'):
    if mode not in ('console','crisp','smooth'):raise ValueError('Unknown graphical font mode')
    import cells
    base=cells.Font
    class Font(base):
        mac_supplement=True
        def __init__(self,path):
            super().__init__(path)
            box_glyphs(self)
            sidecar=Path(path).with_suffix('.glyphs')
            if not sidecar.exists():
                if mode!='console':raise ValueError('Smooth font unavailable; choose --font-mode console')
                self.coverage={};return
            data=sidecar.read_bytes()
            if len(data)%20:raise ValueError('Truncated native font supplement')
            glyphs=list(self.glyphs)
            for at in range(0,len(data),20):
                code=struct.unpack_from('<I',data,at)[0];ch=chr(code)
                if ch not in self.mapping:
                    self.mapping[ch]=len(glyphs);glyphs.append(data[at+4:at+20])
            self.coverage={}
            smooth=Path(path).with_suffix('.smooth')
            if mode!='console':
                if not smooth.exists():raise ValueError('Smooth font is unavailable; build on macOS or choose --font-mode console')
                data=smooth.read_bytes()
                if len(data)%132:raise ValueError('Truncated smooth font coverage')
                for at in range(0,len(data),132):
                    code=struct.unpack_from('<I',data,at)[0];ch=chr(code);coverage=data[at+4:at+132]
                    if not 32<=code<127:raise ValueError('Smooth text coverage must preserve graphics glyphs')
                    if mode=='smooth':self.coverage[ch]=coverage
                    bits=bytes(sum((128>>x) for x in range(8) if coverage[y*8+x]>=128) for y in range(16))
                    if ch not in self.mapping:self.mapping[ch]=len(glyphs);glyphs.append(bits)
                    else:glyphs[self.mapping[ch]]=bits
            self.glyphs=tuple(glyphs)
    return Font(path)
