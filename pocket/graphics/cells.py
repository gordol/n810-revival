"""Experimental live Host -> retained native RGB565 image. No device ownership.

Uses the existing Host damage observer; does not patch the desktop or app state.
Host composition bypasses ANSI serialization. This remains a correctness
bridge, not a GPU glyph renderer or a claimed device performance improvement.
"""
import ctypes as C
from functools import lru_cache
from pathlib import Path
import struct
import sys
import os
from array import array

ROOT = Path(os.environ['POCKET_SOURCE_ROOT']) if 'POCKET_SOURCE_ROOT' in os.environ else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pocket/shell'))
from paint import foreground, background


class Surface(C.Structure):
    _fields_ = [('pixels', C.c_void_p), ('bytes', C.c_size_t),
                ('stride', C.c_size_t), ('width', C.c_uint), ('height', C.c_uint)]


class Font:
    def __init__(self, path):
        data = Path(path).read_bytes()
        if data[:2] != b'\x36\x04':
            raise ValueError('This bridge requires the captured PSF1 console font')
        mode, self.height = data[2:4]
        self.width = 8
        count = 512 if mode & 1 else 256
        end = 4 + count*self.height
        if not self.height or len(data) < end:
            raise ValueError('Truncated console font')
        self.glyphs = tuple(data[4+i*self.height:4+(i+1)*self.height] for i in range(count))
        self.mapping = {}
        if mode & 2:
            index = 0
            sequence = False
            for (code,) in struct.iter_unpack('<H', data[end:]):
                if code == 0xffff:
                    index += 1
                    sequence = False
                elif code == 0xfffe:
                    sequence = True
                elif not sequence:
                    self.mapping[chr(code)] = index
        else:
            self.mapping = {chr(i): i for i in range(count)}

    def add_desktop_glyphs(self):
        """Explicit UI chevrons absent from the captured console font; no fallback."""
        shapes={'›':(0,0,0,0,0x20,0x10,0x08,0x04,0x08,0x10,0x20,0,0,0,0,0),
                '‹':(0,0,0,0,0x04,0x08,0x10,0x20,0x10,0x08,0x04,0,0,0,0,0)}
        if self.height!=16:raise ValueError('Desktop glyphs require16-pixel font')
        shapes['┄']=tuple(row&0xdb for row in self.glyph('─'))
        shapes['┆']=tuple(row if i%6<4 else 0 for i,row in enumerate(self.glyph('│')))
        for char,rows in shapes.items():
            if char not in self.mapping:
                self.mapping[char]=len(self.glyphs);self.glyphs=(*self.glyphs,bytes(rows))

    def glyph(self, char):
        if char not in self.mapping:
            raise ValueError(f'Font does not contain {char!r}; refusing silent substitution')
        return self.glyphs[self.mapping[char]]


def indexed_color(index):
    base = ((0,0,0),(170,0,0),(0,170,0),(170,85,0),(0,0,170),(170,0,170),
            (0,170,170),(170,170,170),(85,85,85),(255,85,85),(85,255,85),
            (255,255,85),(85,85,255),(255,85,255),(85,255,255),(255,255,255))
    if index < 16: return base[index]
    if index < 232:
        index -= 16
        levels = (0,95,135,175,215,255)
        return levels[index//36], levels[(index//6)%6], levels[index%6]
    return (8+10*(index-232),)*3


@lru_cache(maxsize=4096)
def style(fg, bg):
    tokens = list(map(int, (fg+';48;'+bg).split(';')))
    fore = back = None
    bold = underline = reverse = False
    i = 0
    while i < len(tokens):
        code = tokens[i]; i += 1
        if code == 1: bold = True
        elif code == 4: underline = True
        elif code == 7: reverse = True
        elif code in (38,48):
            mode = tokens[i]; i += 1
            if mode == 2:
                value = tuple(tokens[i:i+3]); i += 3
            elif mode == 5:
                value = indexed_color(tokens[i]); i += 1
            else: raise ValueError('Unsupported color mode')
            if code == 38: fore = value
            else: back = value
        elif 30 <= code <= 37: fore = indexed_color(code-30)
        elif 90 <= code <= 97: fore = indexed_color(code-90+8)
        else: raise ValueError(f'Unsupported style {code}')
    if fore is None or back is None: raise ValueError('Incomplete style')
    if reverse: fore, back = back, fore
    def pack(v): return ((v[0]>>3)<<11)|((v[1]>>2)<<5)|(v[2]>>3)
    return pack(fore), pack(back), bold, underline


class LiveCells:
    def __init__(self, host, font, library, *, pixels=None, bulk=False):
        self.host, self.font = host, font
        self.cols, self.rows = host.width, host.height
        width, height = self.cols*font.width, self.rows*font.height
        self.pixels = (C.c_ubyte*(width*height*2)).from_buffer(pixels) if pixels is not None else (C.c_ubyte*(width*height*2))()
        self.surface = Surface(C.addressof(self.pixels), len(self.pixels), width*2, width, height)
        self.lib = C.CDLL(str(library))
        self.lib.mbx_cell_rgb565.argtypes = [C.POINTER(Surface), C.c_uint, C.c_uint,
            C.c_uint, C.c_uint, C.c_void_p, C.c_size_t, C.c_uint16, C.c_uint16]
        self.lib.mbx_cell_rgb565.restype = C.c_int
        self.seen = [None]*(self.cols*self.rows)
        self.previous_observer = host.observe_composition
        host.observe_composition = True
        host.invalidate((0,0,self.cols,self.rows))
        self.cells_drawn = 0
        self.bulk_batches = 0
        self.bulk_enabled=bulk
        self._using_bulk=False
        self._bulk_seen = (C.c_uint32*(self.cols*self.rows*3))()
        ordered=sorted(font.mapping)
        self._font_codes=(C.c_uint32*len(ordered))(*(ord(ch) for ch in ordered))
        self._font_bits=C.create_string_buffer(b''.join(font.glyph(ch) for ch in ordered))
        if hasattr(self.lib,'mbx_cells_rgb565'):
            self.lib.mbx_cells_rgb565.argtypes=[C.POINTER(Surface),C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_uint16,C.c_void_p,C.c_uint]
            self.lib.mbx_cells_rgb565.restype=C.c_int


    def close(self):
        self.host.observe_composition = self.previous_observer
        # Release the mmap export even when an exception traceback retains this
        # adapter. Otherwise cleanup masks the original failure with BufferError.
        self.surface.pixels = None
        self.pixels = None

    def flush(self, budget=2048):
        try:
            return self._flush(budget)
        except Exception:
            # Host has consumed damage; preserve a retry after adapter failure.
            if (self.host.width,self.host.height)==(self.cols,self.rows):
                self.host.invalidate((0,0,self.cols,self.rows))
            raise

    def _flush(self, budget):
        h = self.host
        if (h.width,h.height) != (self.cols,self.rows):
            raise ValueError('Recreate native surface after resize')
        _, changed, computed = h.flush(budget,serialize=False)
        palette = h._ansi_colors()
        shade = round((10 if h.tinted else 18)*(1-h.overview_opacity)+24*h.overview_opacity)
        native=h._native
        if (self.bulk_enabled and native is not None and h.front is native.front and hasattr(native.lib,'export_cells') and
                hasattr(self.lib,'mbx_cells_rgb565') and not os.environ.get('POCKET_PIXEL_REFERENCE')):
            # The existing style resolver remains authoritative. Uncommon text
            # attributes retain the portable path rather than changing output.
            descriptors=[]
            for color in range(len(palette)):
                fallback=(f'2;{shade};{shade};{shade}' if color in (15,16) else
                          '5;232' if color==14 else '2;10;10;10' if color>=4 and h.tinted else '5;233')
                descriptors.append(style(foreground(color,palette),background(color,fallback)))
            simple=True
            for code in palette:
                parts=tuple(map(int,code.split(';')))
                simple &= ((len(parts)==1 and (30<=parts[0]<=37 or 90<=parts[0]<=97)) or
                           (len(parts)==5 and parts[:2]==(38,2)) or (len(parts)==3 and parts[:2]==(38,5)))
            if simple and not any(bold or underline for _,_,bold,underline in descriptors):
                indices=h.composed_indices
                if not isinstance(indices,memoryview):indices=memoryview(array('I',indices))
                records=native.lib.export_cells(native.front.pointer,indices)
                packed=(C.c_uint32*len(descriptors))(*(fg|(bg<<16) for fg,bg,_,_ in descriptors))
                raw=C.create_string_buffer(records)
                fallback=style('38;2;0;0;0','2;10;10;10' if h.tinted else '5;233')[1]
                drawn=self.lib.mbx_cells_rgb565(C.byref(self.surface),raw,len(records),self._font_codes,self._font_bits,len(self._font_codes),self.font.height,packed,len(packed),fallback,self._bulk_seen,self.cols*self.rows)
                if drawn<0:raise ValueError('Native packed cells rejected')
                self._using_bulk=True
                self.cells_drawn+=drawn;self.bulk_batches+=1
                return changed,computed,drawn
        # Switching away from the fast path must refresh its retained comparison.
        C.memset(self._bulk_seen,0,C.sizeof(self._bulk_seen))
        if self._using_bulk:
            self.seen=[None]*(self.cols*self.rows)
            self._using_bulk=False
        updates = []
        for index in h.composed_indices:
            cell = h.front[index]
            color = cell.color
            fallback = (f'2;{shade};{shade};{shade}' if color in (15,16) else
                        '5;232' if color == 14 else '2;10;10;10' if color >= 4 and h.tinted else '5;233')
            resolved = style(foreground(color,palette), background(color,fallback))
            key = (cell.char,resolved)
            if self.seen[index] == key: continue
            fg,bg,bold,underline = resolved
            glyph = self.font.glyph(cell.char)
            if bold: glyph = bytes(v | (v>>1) for v in glyph)
            if underline: glyph = glyph[:-1]+b'\xff'
            updates.append((index,key,glyph,fg,bg))
        # Validate all glyph/style lookups before touching the retained image.
        for index,key,glyph,fg,bg in updates:
            mask = C.create_string_buffer(glyph)
            result = self.lib.mbx_cell_rgb565(C.byref(self.surface),
                (index%self.cols)*8, (index//self.cols)*self.font.height,
                8,self.font.height,mask,len(glyph),fg,bg)
            if result: raise RuntimeError(f'Native cell rejected: {result}')
            self.seen[index] = key
        self.cells_drawn += len(updates)
        return changed, computed, len(updates)
