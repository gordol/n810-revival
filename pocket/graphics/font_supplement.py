# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Supplement the console font with build-time native Mac UI glyphs."""
from pathlib import Path
import struct

def install():
    import cells
    base=cells.Font
    if getattr(base,'mac_supplement',False):return
    class Font(base):
        mac_supplement=True
        def __init__(self,path):
            super().__init__(path)
            sidecar=Path(path).with_suffix('.glyphs')
            if not sidecar.exists():return
            data=sidecar.read_bytes()
            if len(data)%20:raise ValueError('Truncated native font supplement')
            glyphs=list(self.glyphs)
            for at in range(0,len(data),20):
                code=struct.unpack_from('<I',data,at)[0];ch=chr(code)
                if ch not in self.mapping:
                    self.mapping[ch]=len(glyphs);glyphs.append(data[at+4:at+20])
            self.glyphs=tuple(glyphs)
    cells.Font=Font
