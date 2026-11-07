# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Preserve the console font and add its dashed window-outline variants."""
from pathlib import Path
import struct,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from cells import Font

def extend(source,destination):
    source=Path(source)
    if source.read_bytes()[:4]==b'\x72\xb5\x4a\x86':
        # Reuse the catalog's bounded geometry/checksum validation. Convert its
        # packaged PSF2 bitmap to PSF1 without changing any glyph pixels.
        from font_preview import FontCatalog
        catalog=FontCatalog(source.parent)
        row=next(item for item in catalog.rows if item['file']==source.name)
        catalog.glyphs(row['id'])
        raw=source.read_bytes();_,_,start,_,count,size,height,width=struct.unpack_from('<8I',raw)
        entries=raw[start+count*size:].split(b'\xff')[:count]
        table=b''.join(b''.join(struct.pack('<H',ord(ch)) for ch in entry.split(b'\xfe')[0].decode('utf-8'))+b'\xff\xff' for entry in entries)
        converted=Path(destination).with_name('base-font.psf')
        converted.write_bytes(b'\x36\x04\x03'+bytes([height])+raw[start:start+count*size]+table)
        source=converted
    font=Font(source)
    glyphs=list(font.glyphs)
    codes=[[] for _ in glyphs]
    for ch,index in font.mapping.items():codes[index].append(ord(ch))
    horizontal=bytes(row&0xdb for row in font.glyph('─'))
    vertical=bytes(row if y%6<4 else 0 for y,row in enumerate(font.glyph('│')))
    for ch,bits in (('┄',horizontal),('┆',vertical)):
        if ch in font.mapping:continue
        slot=next(i for i,values in enumerate(codes) if not values)
        glyphs[slot]=bits;codes[slot]=[ord(ch)]
    data=b'\x36\x04\x03'+bytes([font.height])+b''.join(glyphs)
    for values in codes:data+=b''.join(struct.pack('<H',v) for v in values)+b'\xff\xff'
    Path(destination).write_bytes(data)
    result=Font(destination)
    for ch in font.mapping:assert result.glyph(ch)==font.glyph(ch)
    assert '┄' in result.mapping and '┆' in result.mapping
