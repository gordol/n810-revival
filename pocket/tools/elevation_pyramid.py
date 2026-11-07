"""Build display-only elevation overviews from the acquired fine tile catalogue.

No network or second DEM. LOS continues to read only the fine index. Unknown
samples stay unknown when reducing resolution; display smoothing cannot certify
path clearance. All storage uses the existing compressed, metre-valued I16 tiles.
"""
import hashlib
import json
from pathlib import Path
import zlib

VERSION = 2


def write_json(path, value):
    data = (json.dumps(value, sort_keys=True, separators=(',',':'))+'\n').encode()
    if path.is_file() and path.read_bytes() == data:
        return
    temporary = path.with_suffix(path.suffix+'.part')
    temporary.write_bytes(data)
    temporary.replace(path)


def read_grid(path, metadata):
    import numpy as np
    result = np.full((metadata['nz'], metadata['nx']), metadata['nodata'], dtype='<i2')
    for key, item in metadata['tiles'].items():
        tx, ty = map(int, key.split(','))
        raw = (path.parent/item['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Elevation source tile checksum differs: '+key)
        expected = item['width']*item['height']*2
        decoder = zlib.decompressobj()
        payload = decoder.decompress(raw, expected+1)
        if len(payload) != expected or not decoder.eof or decoder.unused_data:
            raise ValueError('Invalid elevation source tile: '+key)
        block = np.frombuffer(payload, dtype='<i2').reshape(item['height'], item['width'])
        result[ty*256:ty*256+item['height'], tx*256:tx*256+item['width']] = block
    return result


def build(index):
    import numpy as np
    index = Path(index)
    metadata = json.loads(index.read_text())
    identity = hashlib.sha256(json.dumps({k:v for k,v in metadata.items() if k not in ('overviews','overview_build')}, sort_keys=True).encode()).hexdigest()
    stamp = dict(version=VERSION, source_sha256=identity)
    if metadata.get('overview_build') == stamp and all((index.parent/row['index']).is_file() for row in metadata.get('overviews', [])):
        write_json(index,metadata)
        for row in metadata.get('overviews', []):
            level=index.parent/row['index'];write_json(level,json.loads(level.read_text()))
        return dict(cached=True, levels=len(metadata.get('overviews', [])))
    values = read_grid(index, metadata)
    levels = []
    factor = 1
    lon, lat = metadata['longitude_first'], metadata['latitude_first']
    dx, dy = metadata['longitude_step'], metadata['latitude_step']
    while min(values.shape) > 32:
        # Retain only complete blocks. Fine data remains the edge/NoData fallback.
        h, w = values.shape
        blocks = values[:h-h%2, :w-w%2].reshape(h//2, 2, w//2, 2)
        valid = (blocks != metadata['nodata']).all(axis=(1,3))
        averaged = np.rint(blocks.astype(np.float64).mean(axis=(1,3)))
        values = np.where(valid, averaged, metadata['nodata']).astype('<i2')
        lon += dx/2; lat += dy/2; dx *= 2; dy *= 2; factor *= 2
        folder = index.parent/'overviews'/str(factor)
        folder.mkdir(parents=True, exist_ok=True)
        tiles = {}
        h, w = values.shape
        for y in range(0, h, 256):
            for x in range(0, w, 256):
                block = values[y:y+256, x:x+256]
                raw = zlib.compress(block.tobytes(), 6)
                name = f'{x//256}-{y//256}.i16.zlib'
                target = folder/name
                if not target.is_file() or target.read_bytes() != raw:
                    target.write_bytes(raw)
                tiles[f'{x//256},{y//256}'] = dict(file=name, width=block.shape[1], height=block.shape[0], bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        level = {k:v for k,v in metadata.items() if k not in ('tiles','maximum_bounds','overviews','overview_build')}
        known=values!=metadata['nodata']
        level.update(valid_samples=int(known.sum()),missing_samples=int(values.size-known.sum()),
                     range_m=[int(values[known].min()),int(values[known].max())] if known.any() else [None,None],
                     nx=w,nz=h,longitude_first=lon,latitude_first=lat,longitude_step=dx,latitude_step=dy,tiles=tiles,
                     purpose='display',overview_factor=factor,
                     extent=dict(xmin=lon-dx/2,ymin=lat-dy/2,xmax=lon+(w-.5)*dx,ymax=lat+(h-.5)*dy,spatialReference={'wkid':4326}))
        write_json(folder/'index.json', level)
        levels.append(dict(factor=factor,index=f'overviews/{factor}/index.json'))
    metadata.update(overviews=levels, overview_build=stamp)
    write_json(index, metadata)
    return dict(cached=False, levels=len(levels))
