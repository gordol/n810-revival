"""Acquire the small Rainier walk DEM on explicit request; publish both files together."""
from datetime import date
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
from urllib.parse import urlencode
from urllib.request import urlopen

SHELL = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SHELL))
from data_paths import rainier_cache, rainier_root

FILES = ('tahoma-3dep.json','tahoma-3dep.i16.zlib')
SERVICE = 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage'


def installed():
    path=rainier_root()
    return path if all((path/name).is_file() for name in FILES) else None


def download():
    if installed():return
    target=rainier_cache()/'regional'
    target.parent.mkdir(parents=True,exist_ok=True)
    params=dict(bbox='-122.1,46.53,-121.42,47.06',bboxSR=4326,imageSR=4326,size='257,257',
                format='tiff',pixelType='F32',interpolation='RSP_BilinearInterpolation',
                adjustAspectRatio='false',renderingRule='{"rasterFunction":"None"}',f='json')
    url=SERVICE+'?'+urlencode(params)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        stage=Path(tmp)
        with urlopen(url,timeout=45) as response:export=json.load(response)
        if (export.get('width'),export.get('height'))!=(257,257):raise ValueError('USGS did not return the requested Rainier grid')
        # ArcGIS JSON can be cached longer than its temporary TIFF URL.
        image_url=SERVICE+'?'+urlencode(dict(params,f='image'))
        with urlopen(image_url,timeout=60) as response:raw=response.read(2**20+1)
        if len(raw)>2**20:raise ValueError('USGS image exceeded the expected size')
        image=stage/'raw.tif';image.write_bytes(raw)
        record=stage/'export.json';record.write_text(json.dumps(dict(request_url=url,response=export,accessed=date.today().isoformat())))
        out=stage/'grid'
        if os.environ.get('POCKET_TERMUX')=='1':
            script=stage/'import_3dep.py'
            script.write_bytes((SHELL/script.name).read_bytes())
            subprocess.run(['proot-distro','login','pocket-maps','--bind',str(stage),'--','/usr/bin/python3',
                            str(script),str(image),str(record),str(out)],check=True)
        else:
            from import_3dep import prepare
            prepare(image,record,out)
        try:out.rename(target)
        except OSError:
            if not installed():raise
