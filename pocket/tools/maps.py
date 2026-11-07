"""Download public map inputs and build Pocket's local offline map files."""
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import base64
import gzip
import hashlib
import json
import marshal
from pathlib import Path
import shutil
import subprocess
import struct
import sys
import urllib.request
import urllib.parse
import zlib

if __package__:
    from .elevation_pipeline import run as elevation,validate_bbox
    from .elevation_pyramid import write_json
else:
    from elevation_pipeline import run as elevation,validate_bbox
    from elevation_pyramid import write_json

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'


def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        print(f'Using existing input: {destination}')
        return
    temporary = destination.with_suffix(destination.suffix + '.part')
    try:
        request = urllib.request.Request(url, headers={'User-Agent': 'N810-Revival-Map-Builder/1.0'})
        with urllib.request.urlopen(request, timeout=180) as response, temporary.open('wb') as target:
            shutil.copyfileobj(response, target)
        with temporary.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        temporary.replace(destination)
        destination.with_suffix(destination.suffix + '.source.json').write_text(json.dumps(
            {'url': url, 'sha256': digest}, indent=2) + '\n')
    finally:
        temporary.unlink(missing_ok=True)


def run(script, *args):
    subprocess.run([sys.executable, str(script), *map(str, args)], check=True)


def index_roads(roads,tile_size):
    """Compile already parsed roads directly; no temporary gzip or legacy builder."""
    segments=[];index={}
    for road in roads:
        points=[(round(x*100000),round(y*100000)) for x,y in road['points']]
        for (x,y),(xx,yy) in zip(points,points[1:]):
            if (x,y)==(xx,yy):continue
            number=len(segments)//4;segments.extend((x,y,xx,yy))
            for by in range(min(y,yy)//tile_size,max(y,yy)//tile_size+1):
                for bx in range(min(x,xx)//tile_size,max(x,xx)//tile_size+1):index.setdefault((bx,by),[]).append(number)
    return dict(tile=tile_size,segments=struct.pack('<%di'%len(segments),*segments),index={key:tuple(value) for key,value in index.items()})


def build_views(data, maps, bbox):
    """Compile the imported water polygons and roads for the terminal renderer."""
    from PIL import Image, ImageDraw
    from shapely.geometry import shape, box
    source = json.loads(gzip.decompress((data / 'osm-water-source.geojson.gz').read_bytes()))
    geography = json.loads(gzip.decompress((data / 'regional-geography-source.json.gz').read_bytes()))
    west, south, east, north = bbox
    width, height = 960, max(32, round(960 * (north - south) / (east - west)))
    height = min(height, 2048)
    image = Image.new('L', (width, height), 0)
    draw = ImageDraw.Draw(image)
    def pixels(ring):
        return [((x-west)/(east-west)*(width-1), (north-y)/(north-south)*(height-1)) for x,y in ring]
    for feature in source['features']:
        geometry = shape(feature['geometry']).intersection(box(*bbox))
        polygons = [geometry] if geometry.geom_type == 'Polygon' else getattr(geometry, 'geoms', [])
        value = 1 if feature['properties'].get('WB_CART_FTR_CD') == 116 else 2
        for polygon in polygons:
            if polygon.geom_type != 'Polygon' or polygon.is_empty:
                continue
            draw.polygon(pixels(polygon.exterior.coords), fill=value)
            for ring in polygon.interiors:
                draw.polygon(pixels(ring.coords), fill=0)
    maps.mkdir(parents=True, exist_ok=True)
    pack = dict(version=1, name='Selected region',
                bbox=bbox, attribution='OpenStreetMap contributors',
                license_url='https://www.openstreetmap.org/copyright',
                source_sha256=geography['source_sha256'], labels=geography['labels'], lines=[],
                raster=dict(width=width,height=height,data=base64.b64encode(zlib.compress(image.tobytes())).decode()))
    roads = [(road['bbox'], [[round(x*100000), round(y*100000)] for x,y in road['points']])
             for road in geography['roads'] if road['kind'] in ('motorway','trunk','primary')]
    road_name = 'puget-sound.roads.gz'
    (maps / road_name).write_bytes(gzip.compress(json.dumps(roads).encode(), mtime=0))
    pack['close_roads'] = road_name
    (maps / 'puget-sound.json.gz').write_bytes(gzip.compress(json.dumps(pack).encode(), mtime=0))
    (maps / 'puget-sound.meta.json').write_text(json.dumps({k:v for k,v in pack.items() if k not in ('raster','lines')}, indent=2)+'\n')
    indexed=[]
    for values,tile_size in ((geography['roads'],500),
                             ([r for r in geography['roads'] if r['kind'] in ('motorway','trunk','primary')],5000),
                             (geography.get('streams',[]),500)):
        indexed.append(index_roads(values,tile_size))
    walk=dict(version=1,grids=[dict(name=pack['name'],bbox=bbox,width=width,height=height,
              pixels=bytes(0 if value else 1 for value in image.tobytes()),heights=False,regional_bands_m=[])],
              roads=indexed[:2],streams=indexed[2],thresholds=[],palette=[4,0,8,2,3,6,7,0])
    (maps/'walk-layers.n8w').write_bytes(b'N8W1'+zlib.compress(marshal.dumps(walk,2),9))



def terrain(output, bbox, *, spacing=15, workers=2, offline=False, plan_only=False):
    report=elevation(bbox,output,output/'downloads/usgs',metres=spacing,workers=workers,offline=offline,plan_only=plan_only)
    print(json.dumps(report))
    return report


def build_identity(source,coverage,bbox):
    def stamp(path):
        info=path.stat();return [str(path.resolve()),info.st_size,info.st_mtime_ns]
    dependencies=[TOOLS/name for name in ('maps.py','import_osm_region.py','build_hydrography.py','tile_map_geography.py')]
    return dict(source=stamp(source),coverage=stamp(coverage) if coverage.is_file() else None,bbox=list(bbox),
                builders={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies})


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('configure','download','build','elevation','terrain','plan'))
    parser.add_argument('--source',type=Path)
    parser.add_argument('--url')
    parser.add_argument('--output',type=Path,default=ROOT/'data')
    parser.add_argument('--maps',type=Path)
    parser.add_argument('--coverage-file',type=Path)
    parser.add_argument('--bbox',nargs=4,type=float)
    parser.add_argument('--spacing-m',type=float,default=15)
    parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args(argv)
    selection=args.output/'map-area.json'
    config=json.loads(selection.read_text()) if selection.is_file() else {}
    source=args.source or Path(config.get('source',args.output/'downloads/region.osm.pbf'))
    url=args.url or config.get('url')
    bbox=args.bbox or config.get('bbox')
    maps=args.maps or args.output/'maps'
    if args.action!='download':
        if bbox is None:parser.error('Select an area first: maps configure --bbox WEST SOUTH EAST NORTH, or supply --bbox')
        try:bbox=list(validate_bbox(bbox))
        except ValueError as error:parser.error(str(error))
    if args.action=='configure':
        args.output.mkdir(parents=True,exist_ok=True)
        write_json(selection,dict(version=1,bbox=bbox,source=str(source.resolve()),url=url))
        print('Saved map area; no data downloaded.')
        return
    if args.action=='download':
        if source.is_file():print('Using existing input: '+str(source));return
        if not url:parser.error('Set --url for the chosen OSM extract; no region is downloaded implicitly')
        download(url,source)
        if url.startswith('https://download.geofabrik.de/') and url.endswith('.osm.pbf'):download(url[:-8]+'.poly',source.with_suffix('.poly'))
        return
    if args.action in ('terrain','elevation','plan'):
        try:terrain(args.output,bbox,spacing=args.spacing_m,workers=args.workers,offline=args.action=='terrain',plan_only=args.action=='plan')
        except ValueError as error:parser.error(str(error))
        return
    if not source.is_file():parser.error('Map input is missing. Run maps download or set --source to an existing OSM file.')
    coverage=args.coverage_file or source.with_suffix('.poly')
    identity=build_identity(source,coverage,bbox)
    identity['maps']=str(maps.resolve())
    receipt=args.output/'map-build.json'
    required=[args.output/'geography/index.json',args.output/'hydrography/index.json',maps/'walk-layers.n8w',maps/'puget-sound.json.gz',maps/'puget-sound.meta.json',maps/'puget-sound.roads.gz']
    if receipt.is_file() and json.loads(receipt.read_text())==identity and all(p.is_file() for p in required):
        print('Map inputs and builders unchanged; using existing geography and terminal views.')
        return
    extra=['--coverage-file',coverage] if coverage.is_file() else []
    run(TOOLS/'import_osm_region.py',source,'--bbox',*bbox,'--output',args.output,*extra)
    build_views(args.output,maps,bbox)
    write_json(receipt,identity)
    print('Built shared geography and terminal views. Elevation: maps elevation; no resource mirrors created.')

if __name__=='__main__':main()
