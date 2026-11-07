"""Area-selected, resumable elevation acquisition; derive all display levels locally."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
import urllib.parse
import urllib.request
if __package__:
    from .elevation_pyramid import build as build_overviews, write_json
    from .prepare_elevation_tiles import prepare
else:
    from elevation_pyramid import build as build_overviews, write_json
    from prepare_elevation_tiles import prepare

BASE = 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage'


def validate_bbox(bbox):
    if len(bbox)!=4 or not all(math.isfinite(v) for v in bbox) or not (-180<=bbox[0]<bbox[2]<=180 and -90<bbox[1]<bbox[3]<90):
        raise ValueError('Use west south east north within geographic bounds')
    return tuple(bbox)


def extent(metadata):
    m = metadata['extent']
    return tuple(m[k] for k in ('xmin','ymin','xmax','ymax'))


def intersection(a,b):
    result=(max(a[0],b[0]),max(a[1],b[1]),min(a[2],b[2]),min(a[3],b[3]))
    return result if result[2]-result[0]>1e-9 and result[3]-result[1]>1e-9 else None


def subtract(area, covered):
    cut=intersection(area,covered)
    if cut is None:return [area]
    w,s,e,n=area;cw,cs,ce,cn=cut
    return [r for r in ((w,s,cw,n),(ce,s,e,n),(cw,s,ce,cs),(cw,cn,ce,n)) if r[2]-r[0]>1e-9 and r[3]-r[1]>1e-9]


def spacing(metadata):
    # North/south is the conservative dimension for geographic cells here.
    return max(abs(metadata['latitude_step'])*111320,
               abs(metadata['longitude_step'])*111320*math.cos(math.radians((extent(metadata)[1]+extent(metadata)[3])/2)))


def plan(bbox, output, metres=15, downloads=None):
    bbox=validate_bbox(bbox)
    if not math.isfinite(metres) or metres<1:raise ValueError('Elevation spacing must be at least one metre')
    remaining=[bbox];cached=[]
    for path in sorted((Path(output)/'elevation-fine').glob('*-guarded/index.json')):
        m=json.loads(path.read_text())
        if m.get('purpose')=='display' or not m.get('sparse_tiff_safe') or spacing(m)>metres*(1+1e-9):continue
        if any(intersection(r,extent(m)) for r in remaining):
            cached.append(path)
            remaining=[part for r in remaining for part in subtract(r,extent(m))]
    cached_raw=[]
    downloads=Path(downloads) if downloads is not None else Path(output)/'downloads/usgs'
    if remaining:
        for record in sorted(downloads.rglob('export.json')):
            image=record.with_name('raw.tif')
            if not image.is_file():continue
            envelope=json.loads(record.read_text());response=envelope['response'];box=extent(response)
            m=dict(extent=response['extent'],longitude_step=(box[2]-box[0])/response['width'],latitude_step=(box[3]-box[1])/response['height'])
            if spacing(m)>metres*(1+1e-9):continue
            if any(intersection(r,box) for r in remaining):
                request=dict(bbox=list(box),width=response['width'],height=response['height'])
                request['id']=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()[:24]
                cached_raw.append((image,record,request['id']))
                remaining=[part for r in remaining for part in subtract(r,box)]
            if not remaining:break
    requests=[]
    for area in remaining:
        # Bound each export to <=4096 pixels per axis, retaining one shared grid.
        max_y=metres*4096/111320
        closest=0 if area[1]<=0<=area[3] else min(abs(area[1]),abs(area[3]))
        max_x=max_y/max(.01,math.cos(math.radians(closest)))
        cols=max(1,math.ceil((area[2]-area[0])/max_x));rows=max(1,math.ceil((area[3]-area[1])/max_y))
        for row in range(rows):
            for col in range(cols):
                w=area[0]+(area[2]-area[0])*col/cols;e=area[0]+(area[2]-area[0])*(col+1)/cols
                s=area[1]+(area[3]-area[1])*row/rows;n=area[1]+(area[3]-area[1])*(row+1)/rows
                width=max(2,math.ceil((e-w)*111320*math.cos(math.radians((s+n)/2))/metres))
                height=max(2,math.ceil((n-s)*111320/metres))
                request=dict(bbox=[w,s,e,n],width=min(4096,width),height=min(4096,height))
                request['id']=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()[:24]
                requests.append(request)
    return dict(bbox=list(bbox),spacing_m=metres,cached=cached,raw=cached_raw,requests=requests,
                estimated_raw_bytes=sum(r['width']*r['height']*4 for r in requests))


def acquire(request, downloads, output, *, offline=False):
    target=Path(output)/'elevation-fine'/(request['id']+'-guarded')
    folder=Path(downloads)/request['id'];folder.mkdir(parents=True,exist_ok=True)
    image=folder/'raw.tif';record=folder/'export.json'
    params=dict(bbox=','.join(map(str,request['bbox'])),bboxSR=4326,imageSR=4326,size=f"{request['width']},{request['height']}",format='tiff',pixelType='F32',interpolation='RSP_BilinearInterpolation',adjustAspectRatio='false',renderingRule=json.dumps({'rasterFunction':'None'}),f='json')
    url=BASE+'?'+urllib.parse.urlencode(params)
    if not image.is_file() or not record.is_file():
        if offline:raise ValueError('Fine elevation is missing; run elevation acquisition explicitly')
        with urllib.request.urlopen(url,timeout=180) as response:export=json.load(response)
        if 'href' not in export:raise ValueError('USGS export failed: '+str(export))
        write_json(record,dict(request_url=url,response=export))
        partial=folder/'raw.part'
        try:
            with urllib.request.urlopen(export['href'],timeout=240) as response,partial.open('wb') as destination:shutil.copyfileobj(response,destination)
            partial.replace(image)
        finally:partial.unlink(missing_ok=True)
    return prepare_source(image,record,output,request['id'])


def prepare_source(image,record,output,identity):
    target=Path(output)/'elevation-fine'/(identity+'-guarded')
    target.parent.mkdir(parents=True,exist_ok=True)
    if not (target/'index.json').is_file():
        temporary=Path(tempfile.mkdtemp(prefix=identity+'.',dir=target.parent))
        try:
            prepare(image,record,temporary,maximum_allowed_m=9000,allow_empty=True)
            # Keep the unmodified F32 input for native GIS readers; never fetch a
            # coarse export or create another local crop from it.
            m=json.loads((temporary/'index.json').read_text())
            m['source']='USGS 3DEP selected-area export'
            with image.open('rb') as raw:m['raw_source_sha256']=hashlib.file_digest(raw,'sha256').hexdigest()
            write_json(temporary/'index.json',m)
            temporary.replace(target)
        finally:
            if temporary.exists():shutil.rmtree(temporary)
    return target/'index.json'


def run(bbox, output, downloads, *, metres=15, workers=2, offline=False, plan_only=False):
    output=Path(output);downloads=Path(downloads)
    selected=plan(bbox,output,metres,downloads)
    report=dict(bbox=selected['bbox'],spacing_m=metres,cached_packs=len(selected['cached']),cached_raw_exports=len(selected['raw']),downloads=len(selected['requests']),estimated_raw_bytes=selected['estimated_raw_bytes'])
    if plan_only:return report
    if not 1<=workers<=16:raise ValueError('Use between one and sixteen workers')
    if offline and any(not (downloads/r['id']/'raw.tif').is_file() or not (downloads/r['id']/'export.json').is_file() for r in selected['requests']):
        raise ValueError('Missing fine elevation; offline derivation will not download a coarse replacement')
    with ThreadPoolExecutor(max_workers=workers) as pool:
        acquired=list(pool.map(lambda request:acquire(request,downloads,output,offline=offline),selected['requests']))
    paths=selected['cached']+[prepare_source(image,record,output,identity) for image,record,identity in selected['raw']]+acquired
    levels=[build_overviews(path) for path in paths]
    manifest=dict(version=1,bbox=selected['bbox'],spacing_m=metres,packs=[str(p.relative_to(output)) for p in paths],
                  display='Local mean overviews; analysis uses fine samples')
    output.mkdir(parents=True,exist_ok=True)
    write_json(output/'elevation.json',manifest)
    report.update(packs=len(paths),overview_rebuilds=sum(not row['cached'] for row in levels),overviews=sum(row['levels'] for row in levels))
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bbox',type=float,nargs=4,required=True,metavar=('WEST','SOUTH','EAST','NORTH'))
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'data')
    parser.add_argument('--downloads',type=Path)
    parser.add_argument('--spacing-m',type=float,default=15)
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--plan',action='store_true',help='Show reuse, export count and uncompressed-byte estimate without changing files')
    args=parser.parse_args(argv)
    try:print(json.dumps(run(args.bbox,args.output,args.downloads or args.output/'downloads/usgs',metres=args.spacing_m,workers=args.workers,offline=args.offline,plan_only=args.plan)))
    except ValueError as error:parser.error(str(error))

if __name__=='__main__':main()
