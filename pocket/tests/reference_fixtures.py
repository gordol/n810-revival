"""Deterministic fictional reference data for offline integration tests.

Saved-location fixtures use the fictional point 5.5555, 5.5555.
Regional fixtures also exercise public geographic reference systems. Heights, roads,
water, and place records are invented and make no geographic claims. The files
are generated in a temporary directory and removed when the test process exits.
"""
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import atexit
import base64
import gzip
import hashlib
import json
import marshal
import os
from pathlib import Path
import struct
import tempfile
import zlib

_folder = None


def _json(path, value):
    path.write_text(json.dumps(value))


def _layer(segments):
    tile = 5000
    index = {}
    for i, (a, b, c, d) in enumerate(segments):
        for y in range(min(b, d)//tile, max(b, d)//tile+1):
            for x in range(min(a, c)//tile, max(a, c)//tile+1):
                index.setdefault((x, y), []).append(i)
    return dict(tile=tile, segments=struct.pack('<'+'i'*len(segments)*4,
                *(v for row in segments for v in row)), index=index)


def maps():
    return root()/'maps'


def root():
    global _folder
    if _folder is not None:
        return Path(_folder.name)
    _folder = tempfile.TemporaryDirectory(prefix='pocket-reference-fixture-')
    atexit.register(_folder.cleanup)
    destination = Path(_folder.name)
    directory = destination/'maps'
    directory.mkdir()
    coarse = [-126., 44., -119., 52.]
    fine = [5.51455, 5.53455, 5.57455, 5.59455]
    demo_region = [2., 2., 10., 10.]
    size = 512
    labels = [dict(name=name, kind='city', lat=lat, lon=lon) for name,lat,lon in (
        ('Harbor City',47.6038321,-122.330062), ('Teston',47.25,-122.44),
        ('Northport',47.98,-122.2), ('Westport',47.56,-122.63),
        ('Southport',47.04,-122.9), ('Twin City',45.6,-122.6),
        ('Twin City',49.2,-123.1))]
    labels.append(dict(name='Test Peak',kind='peak',lat=46.85,lon=-121.76))
    labels += [dict(row,name='Demo '+row['name'],lat=row['lat']-47.19+5.5555,lon=row['lon']+122.53+5.5555) for row in labels]
    for name,bbox,local in (('Fictional regional relief',coarse,False),
                            ('Fictional fine relief',fine,True),
                            ('Fictional regional relief',demo_region,False)):
        pixels = bytes((((x+y)%6)<<2) | (1 if x%32<8 else 2 if x%32<12 else 0)
                       for y in range(size) for x in range(size))
        pack_labels = labels
        pack = dict(version=1,name=name,bbox=bbox,labels=pack_labels,lines=[],
                    attribution='Generated fictional fixture',water_classes=True,
                    fast_samples=local,close_roads='fixture.roads.gz',
                    max_span_km=5 if local else 48000,
                    terrain=dict(render='hillshade' if local else 'bands'),
                    raster=dict(width=size,height=size,data=base64.b64encode(zlib.compress(pixels)).decode()))
        (directory/('fine.json.gz' if local else 'demo-regional.json.gz' if bbox==demo_region else 'regional.json.gz')).write_bytes(
            gzip.compress(json.dumps(pack).encode(),mtime=0))
    # Parallel invented roads and a creek cross the default test views.
    roads = _layer([(550555,y,562555,y) for y in range(549555,560556,200)])
    (directory/'fixture.roads.gz').write_bytes(gzip.compress(json.dumps(
        [[[508555,561555,608555,561555], [[508555,561555],[608555,561555]]],
         [[-12300000,556550,-12200000,556550], [[-12300000,556550],[-12200000,556550]]]]
    ).encode(),mtime=0))
    major = _layer([(408555,556555,708555,556555)])
    streams = _layer([(554555,546555,554555,562555),
                      (557055,546555,557055,562555)])
    grids = []
    for bbox,local in ((coarse,False),(demo_region,False),(fine,True)):
        grids.append(dict(name='Fictional grid',bbox=bbox,width=size,height=size,
                     pixels=bytes(1+(x+y)%6 for y in range(size) for x in range(size)),
                     heights=local,fine=bytes((x+y)%200 for y in range(size) for x in range(size))))
    (directory/'walk-layers.n8w').write_bytes(b'N8W1'+zlib.compress(marshal.dumps(
        dict(version=1,grids=grids,roads=[roads,major],streams=streams),2)))
    level = dict(width=size,height=size,spacing_m=[200,200],
                 heights=struct.pack('<'+'h'*size*size, *((x*7+y*11)%200 for y in range(size) for x in range(size))),
                 shade=bytes((x+y)%6 for y in range(size) for x in range(size)))
    (directory/'terrain-next.n8t').write_bytes(b'N8T1'+zlib.compress(marshal.dumps(
        dict(nodata=-32768,layers=[dict(name='Fictional heights',bbox=box,levels=[level]) for box in (coarse,demo_region)]),2)))
    _elevation(destination)
    shore = dict(bbox=coarse,land=[dict(bbox=[-122.5,46,-121,49],
                 rings=[[[-122.5,46],[-121,46],[-121,49],[-122.5,49],[-122.5,46]]])],lakes=[])
    (destination/'shoreline-puget.json.gz').write_bytes(gzip.compress(json.dumps(shore).encode(),mtime=0))
    return destination


def _elevation(destination):
    # Repeated flat tiles keep a 10 m sampling domain compact. A second coarse
    # pack exercises coverage fallback. Realistic topography is not required to
    # verify interpolation, sampling density, curvature and source selection.
    packs=[]
    for name,west,south,step,nx,nz,height in (
        ('fictional-fine',-123.2,46.9,.0001,10240,8192,100),
        ('fictional-regional',-125.,45.,.02,256,320,2500),
        ('fictional-demo-fine',5.0,5.0,.0001,10240,8192,100),
        ('fictional-demo-regional',3.,3.,.02,256,320,2500)):
        folder=destination/name;folder.mkdir();tiles={}
        for ty in range((nz+255)//256):
            for tx in range((nx+255)//256):
                w=min(256,nx-tx*256);h=min(256,nz-ty*256)
                if name=='fictional-demo-regional':
                    values=[50+10*((x+y)%200) for y in range(h) for x in range(w)]
                    raw=zlib.compress(struct.pack('<'+'h'*(w*h),*values))
                else:
                    raw=zlib.compress(struct.pack('<h',height)*(w*h))
                filename=f'{tx}-{ty}.i16.zlib';(folder/filename).write_bytes(raw)
                tiles[f'{tx},{ty}']=dict(file=filename,width=w,height=h,sha256=hashlib.sha256(raw).hexdigest())
        metadata=dict(tile_size=256,units='meters',nx=nx,nz=nz,
                      latitude_first=south,longitude_first=west,latitude_step=step,longitude_step=step,
                      nodata=-32768,source=name,accessed='generated by test',tiles=tiles,
                      extent=dict(xmin=west,ymin=south,xmax=west+(nx-1)*step,ymax=south+(nz-1)*step))
        _json(folder/'index.json',metadata);packs.append(name+'/index.json')
    _json(destination/'elevation.json',dict(version=1,packs=packs))
    for name,west,south,step,size,height in (
        ('tahoma-3dep',-122.,46.6,.002,256,2500),
        ('pnw-etopo1',-125.,45.,.025,256,2500)):
        raw=zlib.compress(struct.pack('<h',height)*(size*size))
        (destination/(name+'.i16.zlib')).write_bytes(raw)
        _json(destination/(name+'.json'),dict(nx=size,nz=size,units='meters',
            latitude_first=south,longitude_first=west,latitude_step=step,longitude_step=step,
            source='Fictional legacy grid',accessed='generated by test',nodata=-32768,sha256=hashlib.sha256(raw).hexdigest()))


def activate():
    """Select generated data before importing application modules."""
    os.environ['POCKET_DATA_ROOT']=str(root())
