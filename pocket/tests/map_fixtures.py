"""Tiny fictional map packs for UI tests; no downloaded geography required."""
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import base64,gzip,json,marshal,tempfile,zlib
from pathlib import Path

def install(test, renderer):
    folder=tempfile.TemporaryDirectory(prefix='pocket-map-fixture-');test.addCleanup(folder.cleanup)
    root=Path(folder.name);size=32;bbox=[-125,46,-120,49]
    pack=dict(version=1,name='Fictional test grid',bbox=bbox,labels=[],lines=[],attribution='Generated test fixture',
              raster=dict(width=size,height=size,data=base64.b64encode(zlib.compress(bytes(size*size))).decode()))
    (root/'fixture.json.gz').write_bytes(gzip.compress(json.dumps(pack).encode(),mtime=0))
    layer=dict(tile=500,segments=b'',index={})
    walk=dict(version=1,grids=[dict(name='Fictional test grid',bbox=bbox,width=size,height=size,pixels=bytes([1])*(size*size),heights=False)],roads=[layer,layer])
    (root/'walk-layers.n8w').write_bytes(b'N8W1'+zlib.compress(marshal.dumps(walk,2)))
    renderer.maps=root


def regional_data_available():
    from data_paths import data_root
    root=data_root()
    return (root/'geography/index.json').is_file() and (root/'hydrography/index.json').is_file()
