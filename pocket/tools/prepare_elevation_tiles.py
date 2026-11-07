"""Convert an acquired USGS F32 export into bounded offline elevation tiles.

Run inside the GIS conversion container with read-only input and no network.
"""
import argparse
from array import array
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import zlib


def prepare(tiff,export,destination,maximum_allowed_m=9000,allow_empty=False):
    from PIL import Image
    Image.MAX_IMAGE_PIXELS=20000000
    envelope=json.loads(Path(export).read_text());response=envelope['response'];extent=response['extent']
    if extent['spatialReference']['wkid']!=4326:raise ValueError('Expected geographic USGS export')
    image=Image.open(tiff)
    width,height=image.size
    if image.mode!='F' or (width,height)!=(response['width'],response['height']) or width*height>20000000:
        raise ValueError('Expected bounded single-band raw F32 elevations')
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    if (destination/'index.json').exists():raise ValueError('Prepare into a new directory')
    size=256;tiles={};valid=0;missing=0;minimum=9000;maximum=-1000
    try:import numpy as np
    except ImportError:np=None
    if np is not None:
        offsets=image.tag_v2.get(324);counts=image.tag_v2.get(325)
        if offsets is not None and image.tag_v2.get(259)==1:
            # ArcGIS emits sparse uncompressed TIFF tiles: offset/count zero
            # means missing, not image bytes at file offset zero. Pillow does
            # not handle these reliably and can turn TIFF headers into heights.
            pixels=np.full((height,width),np.nan,dtype=np.float32)
            tw,th=image.tag_v2[322],image.tag_v2[323];across=(width+tw-1)//tw
            with Path(tiff).open('rb') as source:
                endian='<' if source.read(2)==b'II' else '>'
                for i,(offset,count) in enumerate(zip(offsets,counts)):
                    if offset==0 and count==0:continue
                    if count!=tw*th*4 or offset<=0:raise ValueError('Unsupported TIFF tile length')
                    source.seek(offset);raw=source.read(count)
                    if len(raw)!=count:raise ValueError('Truncated source TIFF tile')
                    tile=np.frombuffer(raw,dtype=endian+'f4').reshape(th,tw)
                    y,x=(i//across)*th,(i%across)*tw
                    pixels[y:min(y+th,height),x:min(x+tw,width)]=tile[:min(th,height-y),:min(tw,width-x)]
        else:pixels=np.asarray(image)
        valid_pixels=np.isfinite(pixels)&(pixels>=-1000)&(pixels<=maximum_allowed_m)
        # USGS coastal F32 exports can contain plausible-looking garbage next to
        # extreme NoData values. Keep a conservative two-cell unknown halo.
        bad=~valid_pixels
        for axis in (0,1):
            expanded=bad.copy()
            for shift in (1,2):
                left=[slice(None),slice(None)];right=left.copy()
                left[axis]=slice(shift,None);right[axis]=slice(None,-shift)
                expanded[tuple(left)]|=bad[tuple(right)];expanded[tuple(right)]|=bad[tuple(left)]
            bad=expanded
        valid_pixels=~bad
    for ty in range((height+size-1)//size):
        for tx in range((width+size-1)//size):
            tw=min(size,width-tx*size);th=min(size,height-ty*size)
            # Reverse source north-to-south image rows into south-to-north storage.
            block=image.crop((tx*size,height-ty*size-th,tx*size+tw,height-ty*size)) if np is None else None
            if np is not None:
                source=pixels[height-ty*size-th:height-ty*size,tx*size:tx*size+tw][::-1]
                mask=valid_pixels[height-ty*size-th:height-ty*size,tx*size:tx*size+tw][::-1]
                count=int(mask.sum());valid+=count;missing+=tw*th-count
                if count:minimum=min(minimum,int(np.rint(source[mask]).min()));maximum=max(maximum,int(np.rint(source[mask]).max()))
                packed=np.rint(np.where(mask,source,-32768)).astype('<i2').tobytes()
            else:
                source=list(block.getdata());values=[]
                for y in range(th-1,-1,-1):
                    for value in source[y*tw:(y+1)*tw]:
                        if not math.isfinite(value) or not -1000<=value<=maximum_allowed_m:values.append(-32768);missing+=1
                        else:
                            rounded=round(value);values.append(rounded);valid+=1
                            minimum=min(minimum,rounded);maximum=max(maximum,rounded)
                packed=array('h',values)
                if sys.byteorder!='little':packed.byteswap()
                packed=packed.tobytes()
            raw=zlib.compress(packed,9);name=f'{tx}-{ty}.i16.zlib'
            (destination/name).write_bytes(raw)
            tiles[f'{tx},{ty}']=dict(file=name,width=tw,height=th,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    image.close()
    if not valid and not allow_empty:raise ValueError('USGS export contains no valid elevations')
    index=dict(version=1,source=envelope.get('source','USGS 3DEP export'),request_url=envelope['request_url'],
               accessed=datetime.now(timezone.utc).date().isoformat(),nx=width,nz=height,tile_size=size,
               longitude_first=extent['xmin']+(extent['xmax']-extent['xmin'])/(2*width),
               latitude_first=extent['ymin']+(extent['ymax']-extent['ymin'])/(2*height),
               longitude_step=(extent['xmax']-extent['xmin'])/width,latitude_step=(extent['ymax']-extent['ymin'])/height,
               extent=extent,units='meters',nodata=-32768,maximum_allowed_m=maximum_allowed_m,nodata_guard_pixels=2 if np is not None else 0,valid_samples=valid,missing_samples=missing,
               sparse_tiff_safe=True,range_m=[minimum,maximum] if valid else [None,None],tiles=tiles,note='Export spacing is not native DEM resolution or a guarantee of RF clearance')
    (destination/'index.json').write_text(json.dumps(index,indent=2)+'\n')
    if __package__:
        from .build_elevation_bounds import build
    else:
        from build_elevation_bounds import build
    build(destination)
    return dict(tiles=len(tiles),valid=valid,missing=missing,bytes=sum(t['bytes'] for t in tiles.values()),range_m=index['range_m'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('tiff');parser.add_argument('export');parser.add_argument('output')
    args=parser.parse_args();print(json.dumps(prepare(args.tiff,args.export,args.output)))
