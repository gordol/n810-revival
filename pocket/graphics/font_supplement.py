# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Supplement the console font with build-time native Mac UI glyphs."""
from pathlib import Path
import struct

def load(path,mode='console'):
    if mode not in ('console','crisp','smooth'):raise ValueError('Unknown graphical font mode')
    import cells
    base=cells.Font
    class Font(base):
        mac_supplement=True
        def __init__(self,path):
            super().__init__(path)
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
