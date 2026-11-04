"""One scalar per retained cell; optional explicit PSF2 font repertoire.

Wide scalars, combining marks, controls and format characters become '?', each
occupying one cell. No grapheme shaping or double-width layout is claimed.
Ambiguous-width and private-use scalars are treated as one cell (Powerline uses
private-use scalars). An explicit font restricts these to its Unicode table.
"""
from functools import lru_cache


@lru_cache(maxsize=512)
def single(char):
    if len(char)!=1:return False
    if ' ' <= char <= '~':return True
    import unicodedata
    category=unicodedata.category(char)
    return (category[0] not in 'MZ' or char=='\u00a0') and category not in ('Cc','Cf','Cs','Cn') and unicodedata.east_asian_width(char) not in ('W','F')


class Glyphs:
    __slots__=('supported','key')
    def __init__(self,supported=None):
        self.supported=None if supported is None else frozenset(supported)
        self.key=self.supported
    def cell(self,char,ascii=False):
        if ' ' <= char <= '~' and len(char)==1:return char
        if ascii or not single(char) or self.supported is not None and char not in self.supported:return '?'
        return char
    def text(self,text,ascii=False):
        if text.isascii() and text.isprintable():return text
        return ''.join(self.cell(char,ascii) for char in text)


RICH=Glyphs()


def load_psf(path):
    """Read a bounded font file only; no console ioctl, font install or probing."""
    import struct
    with open(path,'rb') as stream:data=stream.read(131073)
    if len(data)>131072 or len(data)<32:raise ValueError('invalid PSF2 size')
    magic,version,start,flags,count,size,height,width=struct.unpack_from('<8I',data)
    end=start+count*size
    if magic!=0x864ab572 or version!=0 or start<32 or flags!=1 or count not in (256,512) or not 1<=width<=32 or not 1<=height<=32 or size!=height*((width+7)//8) or end>len(data):raise ValueError('expected bounded PSF2 font with Unicode table')
    entries=data[end:].split(b'\xff')
    if len(entries)!=count+1 or entries[-1]:raise ValueError('invalid PSF2 Unicode table')
    supported=set()
    try:
        for entry in entries[:-1]:
            # FE introduces a multi-scalar sequence, not standalone aliases.
            parts=entry.split(b'\xfe');supported.update(parts[0].decode('utf-8'))
            for sequence in parts[1:]:sequence.decode('utf-8')
    except UnicodeError as error:raise ValueError('invalid PSF2 Unicode encoding') from error
    if not set(' ?').issubset(supported):raise ValueError('font needs space and placeholder')
    return Glyphs(supported)
