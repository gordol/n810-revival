"""Generate exact ambient(0) tables on a build host, never during device startup."""
from pathlib import Path
import hashlib
import inspect
import json
import struct
import sys
import zlib

ROOT=Path(__file__).resolve().parents[1]/'shell'
sys.path.insert(0,str(ROOT))
from loading import _ambient_reference
from loader_ambient import MAGIC
palette=[];index={};chunks=[];offsets=[0]
for height in range(1,33):
    for width in range(1,65):
        raw=bytearray()
        for glyph,color in _ambient_reference(0,width,height):
            assert glyph=='▄' and color&0xffffff==0
            value=(color>>24)&0xffffff
            if value not in index:index[value]=len(palette);palette.append(value)
            raw.append(index[value])
        packed=zlib.compress(raw,9);chunks.append(packed);offsets.append(offsets[-1]+len(packed))
assert len(palette)<=256
payload=struct.pack('<8sHHH',MAGIC,64,32,len(palette))+struct.pack('<'+'I'*len(palette),*palette)+struct.pack('<'+'I'*len(offsets),*offsets)+b''.join(chunks)
output=ROOT/'data/loader-ambient.zlib';output.write_bytes(payload)
metadata=dict(version=1,entries=2048,palette_colors=len(palette),bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),reference_sha256=hashlib.sha256(inspect.getsource(_ambient_reference).encode()).hexdigest(),generator='tools/prepare_loader_ambient.py',purpose='Exact static ambient step0 only; runtime decodes at most2048 palette indices for requested size. Other steps use reference math.')
output.with_suffix('.json').write_text(json.dumps(metadata,indent=2)+'\n');print(json.dumps(metadata,indent=2))
