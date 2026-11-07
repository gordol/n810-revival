"""Build offline map shorelines from WSDOT hydrography and retained OSM lakes.

The source polygons describe WATER, including ocean and Puget Sound. Subtract
them from coverage to obtain land; never substitute a small-scale land outline.
"""
from pathlib import Path
import argparse,gzip,json,hashlib
from shapely.geometry import LineString,box,shape,Point
from shapely.ops import unary_union,polygonize
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--water-source',type=Path,required=True,help='WSDOT shoreline GeoJSON.gz')
parser.add_argument('--lake-source',type=Path,required=True,help='OSM map JSON.gz with water lines')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
source=args.lake_source
d=json.loads(gzip.decompress(source.read_bytes()))
bbox=[-124.8,46.3,-120.6,48.7];boundary=box(*bbox)
land_source=args.water_source
water_data=json.loads(gzip.decompress(land_source.read_bytes()))
water=unary_union([shape(feature['geometry']) for feature in water_data['features']])
clipped=boundary.difference(water)
land=[clipped] if clipped.geom_type=='Polygon' else list(clipped.geoms)
waterlines=[LineString(row['points']) for row in d['lines'] if row['kind']=='water' and len(row['points'])>1]
lakes=list(polygonize(unary_union(waterlines)))
assert not any(p.covers(Point(-122.61,47.203)) for p in land),'Known Puget water incorrectly classified as land'
assert any(p.covers(Point(-122.4443,47.2529)) for p in land),'Tacoma city-center land incorrectly classified as water'
# These nearby sites distinguish real Puget topology from the old regional
# Natural Earth outline, which erased the peninsulas and filled local inlets.
assert any(p.covers(Point(-122.65,47.30)) for p in land),'Key Peninsula missing'
assert not any(p.covers(Point(-122.56,47.25)) for p in land),'Chambers Bay filled'
def polygons(geometries):
 out=[]
 for poly in geometries:
  if poly.is_empty or poly.geom_type!='Polygon':continue
  out.append(dict(bbox=list(poly.bounds),rings=[list(poly.exterior.coords)]+[list(r.coords) for r in poly.interiors]))
 return out
payload=dict(version=2,bbox=bbox,land=polygons(land),lakes=polygons(lakes),sources=[dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in (land_source,source)],shoreline_url='https://data.wsdot.wa.gov/ArcGIS/rest/services/Shared/MajorShorelinesData/FeatureServer/0',attribution='Washington State Department of Transportation Major Shorelines; OpenStreetMap contributors lake geometry (ODbL)',license_url=d['license_url'])
out=args.output;out.parent.mkdir(parents=True,exist_ok=True)
temporary=out.with_suffix('.tmp');temporary.write_bytes(gzip.compress(json.dumps(payload,separators=(',',':')).encode(),mtime=0));temporary.replace(out)
print(dict(land=len(land),lakes=len(lakes),bytes=out.stat().st_size))
