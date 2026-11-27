"""Acquire the private USGS 3DEP grid covering the summit approach and snow viewpoint."""
from array import array
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlencode
from urllib.request import urlopen
import zlib

# Cells in the bundled 253-square summit inset, including one transition cell.
WEST,SOUTH=119,74
COLUMNS,ROWS=14,24
DIVISIONS=12
WIDTH,HEIGHT=COLUMNS*DIVISIONS+1,ROWS*DIVISIONS+1
DX,DZ=.68/257/6/DIVISIONS,.53/257/6/DIVISIONS
LEFT=-122.1+(.5+107+WEST/6)*.68/257-DX/2
BOTTOM=46.53+(.5+133+SOUTH/6)*.53/257-DZ/2
TOP=BOTTOM+HEIGHT*DZ
SERVICE='https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage'


def convert(image_path,output):
    from PIL import Image
    with Image.open(image_path) as image:
        if image.size!=(WIDTH,HEIGHT) or image.mode!='F':raise ValueError('Unexpected approach raster')
        sx,sz,*_=image.tag_v2[33550]
        i,j,_,lon,lat,_=image.tag_v2[33922]
        if not all(math.isclose(a,b,rel_tol=0,abs_tol=1e-8) for a,b in
                   zip((sx,sz,lon-i*sx,lat+j*sz),(DX,DZ,LEFT,TOP))):
            raise ValueError('Approach raster outside requested grid')
        data=array('f')
        for row in reversed(range(HEIGHT)):
            data.extend(image.crop((0,row,WIDTH,row+1)).getdata())
        if not all(2000<v<4500 for v in data):raise ValueError('Invalid approach elevation')
        if sys.byteorder!='little':data.byteswap()
        output.write_bytes(zlib.compress(data.tobytes()))


def samples():
    from data_paths import rainier_cache
    target=rainier_cache()/'summit-approach-v1.f32.zlib'
    def read(path):
        raw=zlib.decompress(path.read_bytes())
        if len(raw)!=WIDTH*HEIGHT*4:raise ValueError('Incomplete approach grid')
        data=array('f')
        data.frombytes(raw)
        if sys.byteorder!='little':data.byteswap()
        return data
    try:return read(target)
    except (FileNotFoundError,zlib.error,ValueError):pass
    params=dict(bbox=','.join(map(str,(LEFT,BOTTOM,LEFT+WIDTH*DX,TOP))),size=f'{WIDTH},{HEIGHT}',
                bboxSR=4326,imageSR=4326,adjustAspectRatio='false',format='tiff',pixelType='F32',
                interpolation='RSP_BilinearInterpolation',renderingRule='{"rasterFunction":"None"}',f='image')
    target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        stage=Path(tmp)
        with urlopen(SERVICE+'?'+urlencode(params),timeout=12) as response:raw=response.read(2**20+1)
        if len(raw)>2**20:raise ValueError('Oversize approach raster')
        image,output=stage/'terrain.tif',stage/'grid'
        image.write_bytes(raw)
        if os.environ.get('POCKET_TERMUX')=='1':
            script=stage/'summit_approach.py'
            script.write_bytes(Path(__file__).read_bytes())
            subprocess.run(['proot-distro','login','pocket-maps','--bind',tmp,'--','/usr/bin/python3',
                            str(script),str(image),str(output)],check=True,timeout=30)
        else:convert(image,output)
        data=read(output)
        output.replace(target)
        return data


if __name__=='__main__':convert(Path(sys.argv[1]),Path(sys.argv[2]))
