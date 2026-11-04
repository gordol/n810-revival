"""Build consistent regional coast, water and named-road data from a complete OSM PBF.

Requires osmium and Shapely only on the build host. No site coordinates or local
repair patches: all geometry comes from the input snapshot and requested bbox.
"""
from pathlib import Path
import argparse,gzip,json,hashlib,datetime,math
import osmium
from shapely.geometry import Polygon,LineString,box,mapping,shape
from shapely.ops import unary_union,polygonize_full
from shapely.strtree import STRtree
from shapely import from_wkb,make_valid
from build_hydrography import build

class Region(osmium.SimpleHandler):
 def __init__(self,bbox):
  super().__init__();self.boundary=box(*bbox);self.bbox=bbox;self.roads=[];self.streams=[];self.labels=[];self.water=[];self.coasts=[];self.errors=0;self.factory=osmium.geom.WKBFactory()
 def node(self,n):
  kind=n.tags.get('place') or ('bay' if n.tags.get('natural')=='bay' else 'lake' if n.tags.get('natural')=='water' else None);name=n.tags.get('name')
  if name and kind in ('city','town','village','suburb','bay','lake') and self.boundary.covers(__import__('shapely').geometry.Point(n.location.lon,n.location.lat)):
   self.labels.append(dict(name=name,kind=kind,lon=n.location.lon,lat=n.location.lat))
 def way(self,w):
  t=w.tags;coast=t.get('natural')=='coastline';highway=t.get('highway');stream=t.get('waterway') in ('river','stream','canal')
  forest=highway in ('track','unclassified') and (t.get('ref','').startswith(('NF','FR','FS','USFS')) or 'forest' in t.get('name','').lower())
  road=highway in ('motorway','trunk','primary','secondary','tertiary','residential','living_street','unclassified') or highway=='service' and bool(t.get('name')) or forest
  if not (coast or road or stream):return
  try:p=[(n.lon,n.lat) for n in w.nodes]
  except osmium.InvalidLocationError:self.errors+=1;return
  if len(p)<2:return
  g=LineString(p)
  if not g.intersects(self.boundary):return
  if coast:self.coasts.append(g)
  bounds=list(g.bounds)
  if road:self.roads.append(dict(id='w'+str(w.id),name=t.get('name',t.get('ref','')),kind='forest' if forest else highway,points=p,bbox=bounds,max_span=30 if forest else {'motorway':2000,'trunk':2000,'residential':3,'living_street':1.5,'service':1,'unclassified':5}.get(highway,100)))
  if stream:self.streams.append(dict(id='w'+str(w.id),name=t.get('name',''),points=p,bbox=bounds,kind=t.get('waterway')))
 def area(self,a):
  t=a.tags
  if t.get('natural')!='water' and t.get('waterway')!='riverbank' and t.get('landuse') not in ('reservoir','basin'):return
  try:g=from_wkb(self.factory.create_multipolygon(a))
  except (RuntimeError,ValueError):self.errors+=1;return
  if g.is_empty or not g.intersects(self.boundary):return
  if not g.is_valid:g=make_valid(g)
  self.water.append(dict(type='Feature',id='a'+str(a.id),geometry=mapping(g),properties=dict(WB_CART_FTR_CD=421,WB_GNIS_NM=t.get('name'))))

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--bbox',nargs=4,type=float,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--coverage-file',type=Path);a=p.parse_args();region=Region(a.bbox)
 if a.coverage_file:
  rings=[];points=[]
  for line in a.coverage_file.read_text().splitlines()[1:]:
   words=line.split()
   if len(words)==2:points.append(tuple(map(float,words)))
   elif line.strip()=='END' and points:rings.append(Polygon(points));points=[]
  region.boundary=region.boundary.intersection(unary_union(rings))
 print('Reading regional OSM snapshot',flush=True);region.apply_file(str(a.source),locations=True,idx='flex_mem')
 print(dict(coasts=len(region.coasts),water=len(region.water),roads=len(region.roads),streams=len(region.streams),errors=region.errors),flush=True)
 boundary=region.boundary;clipped=[g.intersection(boundary) for g in region.coasts]
 faces,cuts,dangles,invalid=polygonize_full(unary_union(clipped+[boundary.boundary]))
 if not region.coasts or not faces.geoms or not dangles.is_empty or not invalid.is_empty or not cuts.is_empty:
  raise ValueError(f'Incomplete coastline topology: faces={len(faces.geoms)}, cuts={len(cuts.geoms)}, dangles={len(dangles.geoms)}, invalid={len(invalid.geoms)}; previous map retained')
 segments=[LineString([x,y]) for g in region.coasts for x,y in zip(g.coords,list(g.coords)[1:]) if x!=y];tree=STRtree(segments);sea=[];land=[]
 for face in faces.geoms:
  pt=face.representative_point();x,y=segments[int(tree.nearest(pt))].coords
  (land if (y[0]-x[0])*(pt.y-x[1])-(y[1]-x[1])*(pt.x-x[0])>0 else sea).append(face)
 if not land or not sea:raise ValueError('Cannot establish both land and marine water; previous map retained')
 features=region.water+[dict(type='Feature',geometry=mapping(g),properties=dict(WB_CART_FTR_CD=116,WB_GNIS_NM=None)) for g in sea]
 stamp=datetime.datetime.now(datetime.timezone.utc).isoformat();digest=hashlib.sha256(a.source.read_bytes()).hexdigest();a.output.mkdir(parents=True,exist_ok=True)
 source=a.output/'osm-water-source.geojson.gz';source.write_bytes(gzip.compress(json.dumps(dict(features=features,coverage=a.bbox,coverage_geometry=mapping(boundary),complete=True,feature_count=len(features),source_url='https://www.openstreetmap.org/copyright',downloaded=stamp,defines_land=True,source_sha256=digest),separators=(',',':')).encode()))
 build(source,a.output/'hydrography')
 # Keep official forest inventory in the same road layer without discarding OSM.
 prior=a.output/'map-geography.json.gz'
 if prior.exists():region.roads.extend(r for r in json.load(gzip.open(prior,'rt'))['roads'] if r.get('kind')=='forest' and 'status' in r)
 payload=dict(version=2,coverage=a.bbox,roads=region.roads,streams=region.streams,labels=region.labels,water=[],source_sha256=digest,downloaded=stamp,attribution='OpenStreetMap contributors; US Forest Service',license_url='https://www.openstreetmap.org/copyright')
 from tile_map_geography import build as tile_geography
 target=a.output/'regional-geography-source.json.gz';temporary=target.with_suffix('.tmp');temporary.write_bytes(gzip.compress(json.dumps(payload,separators=(',',':')).encode()));temporary.replace(target)
 tile_geography(target,a.output/'geography')
 print(dict(land_faces=len(land),sea_faces=len(sea),topology='complete',geography_bytes=target.stat().st_size),flush=True)
if __name__=='__main__':main()
