"""Build a compact offline grid from a USGS F32 export and its request metadata.

Usage (development Python with Pillow):
    python import_3dep.py export.tiff export.json

export.json must contain request_url and the unmodified exportImage response.
The viewer itself needs only the standard library and the prepared data files.
"""
import array,hashlib,json,math,sys,zlib
from pathlib import Path


def prepare(tiff,export_file,directory):
    from PIL import Image
    image=Image.open(tiff)
    if image.mode!='F':raise ValueError('expected one-band raw floating-point elevations')
    values=list(image.getdata());width,height=image.size
    if not all(math.isfinite(v) and -1000<=v<=9000 for v in values):raise ValueError('invalid/no-data elevation samples')
    export=json.loads(Path(export_file).read_text());extent=export['response']['extent']
    if extent['spatialReference']['wkid']!=4326:raise ValueError('expected geographic longitude/latitude export')
    ordered=[round(values[(height-1-y)*width+x]) for y in range(height) for x in range(width)]
    packed=array.array('h',ordered)
    if sys.byteorder!='little':packed.byteswap()
    compressed=zlib.compress(packed.tobytes(),9)
    metadata={'source':'USGS 3DEP Bare Earth DEM Dynamic service','service_url':'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer','request_url':export['request_url'],'accessed':'2026-10-16','export_extent':extent,'nx':width,'nz':height,'longitude_first':extent['xmin']+(extent['xmax']-extent['xmin'])/(2*width),'latitude_first':extent['ymin']+(extent['ymax']-extent['ymin'])/(2*height),'longitude_step':(extent['xmax']-extent['xmin'])/width,'latitude_step':(extent['ymax']-extent['ymin'])/height,'encoding':'zlib compressed signed little-endian int16, south-to-north rows, west-to-east columns, elevations rounded to meters','units':'meters','resampling':'service bilinear export; renderer samples every second grid point','range_m':[min(ordered),max(ordered)],'sha256':hashlib.sha256(compressed).hexdigest(),'note':'Export grid spacing is not a claim about native source resolution or validated RF accuracy.'}
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    (directory/'tahoma-3dep.i16.zlib').write_bytes(compressed)
    (directory/'tahoma-3dep.json').write_text(json.dumps(metadata,indent=2)+'\n')

if __name__=='__main__':
    prepare(sys.argv[1],sys.argv[2],Path(__file__).with_name('data'))
