"""Build compact named arterial/forest-road and water layers from cached OSM XML."""
from pathlib import Path
import xml.etree.ElementTree as ET
import argparse,gzip,json,hashlib
from shapely.geometry import Polygon,LineString,box,Point
from shapely.ops import polygonize,unary_union
from shapely.strtree import STRtree
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--osm',type=Path,required=True)
parser.add_argument('--forest-source',type=Path,required=True)
parser.add_argument('--state-source',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
nodes={};ways={};relations={};sources=[]
inputs=sorted(args.osm.glob('*.osm'))+sorted(args.osm.glob('*.osm.gz'))
if not inputs:parser.error('No OSM extracts found in --osm directory')
for p in inputs:
 tree=ET.fromstring(gzip.decompress(p.read_bytes()) if p.suffix=='.gz' else p.read_bytes())
 sources.append(dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
 for e in tree:
  if e.tag=='node':nodes[e.attrib['id']]=e
  elif e.tag=='way':ways[e.attrib['id']]=e
  elif e.tag=='relation':relations[e.attrib['id']]=e

def tags(e):return {t.attrib['k']:t.attrib['v'] for t in e.findall('tag')}
def coords(e):return [[float(nodes[n.attrib['ref']].attrib['lon']),float(nodes[n.attrib['ref']].attrib['lat'])] for n in e.findall('nd') if n.attrib['ref'] in nodes]
def polys(g):
 if g.is_empty:return []
 if g.geom_type=='Polygon':return [dict(bbox=list(g.bounds),rings=[list(g.exterior.coords)]+[list(r.coords) for r in g.interiors])]
 return [p for part in getattr(g,'geoms',[]) for p in polys(part)]
roads=[];labels=[];water=[];coasts=[];segments=[]
for e in nodes.values():
 t=tags(e)
 if t.get('name') and (t.get('place') in ('city','town','village','suburb') or t.get('natural') in ('bay','water')):
  labels.append(dict(name=t['name'],lon=float(e.attrib['lon']),lat=float(e.attrib['lat']),kind='bay' if t.get('natural') else t['place']))
for e in ways.values():
 t=tags(e);p=coords(e)
 if len(p)<2:continue
 highway=t.get('highway');forest=highway=='track' and (t.get('ref') or t.get('name'))
 if t.get('natural')=='coastline':
  coasts.append(LineString(p));segments.extend(LineString([a,b]) for a,b in zip(p,p[1:]) if a!=b)
 if highway in ('motorway','trunk','primary','secondary','tertiary','primary_link','secondary_link','tertiary_link') or forest:
  roads.append(dict(id=e.attrib['id'],name=t.get('name',t.get('ref','')),kind='forest' if forest else highway,points=p,max_span=12 if forest else 80))
 if t.get('natural')=='water' and len(p)>3 and p[0]==p[-1]:
  g=Polygon(p)
  if g.is_valid:
   water+=polys(g)
   if t.get('name'):
    c=g.representative_point();labels.append(dict(name=t['name'],lon=c.x,lat=c.y,kind='lake'))
for e in relations.values():
 t=tags(e)
 if t.get('natural')!='water':continue
 outer=[];inner=[]
 for m in e.findall('member'):
  if m.attrib['type']!='way' or m.attrib['ref'] not in ways:continue
  p=coords(ways[m.attrib['ref']])
  if len(p)>1:(inner if m.attrib.get('role')=='inner' else outer).append(LineString(p))
 if not outer:continue
 g=unary_union(list(polygonize(unary_union(outer))))
 if inner:g=g.difference(unary_union(list(polygonize(unary_union(inner)))))
 water+=polys(g)
 if not g.is_empty and t.get('name'):
  c=g.representative_point();labels.append(dict(name=t['name'],lon=c.x,lat=c.y,kind='lake'))
forest=args.forest_source
if forest.is_file():
 for f in json.load(gzip.open(forest,'rt'))['features']:
  g=f.get('geometry');p=f.get('properties',{})
  if not g:continue
  lines=[g['coordinates']] if g['type']=='LineString' else g['coordinates'] if g['type']=='MultiLineString' else []
  for line in lines:
   roads.append(dict(name=('NF-'+str(p.get('id',''))+' '+str(p.get('name') or '')).strip(),kind='forest',points=line,max_span=30,status=p.get('symbol_name'),openforuseto=p.get('openforuseto')))
state=args.state_source
if state.is_file():
 for f in json.load(gzip.open(state,'rt'))['features']:
  p=f['attributes']
  if p.get('RT_TYPEA') not in ('IS','US','SR'):continue
  number=str(p.get('StateRouteNumber',p.get('RouteID',''))).lstrip('0') or '0'
  route=('I-' if p.get('RT_TYPEA') in ('IS','I') else 'US ' if p.get('RT_TYPEA')=='US' else 'SR ')+number
  for line in f.get('geometry',{}).get('paths',[]):roads.append(dict(name=route,kind='highway',points=line,max_span=2000))
for r in roads:
 r['points']=[p[:2] for p in r['points']]
 r['bbox']=[min(p[0] for p in r['points']),min(p[1] for p in r['points']),max(p[0] for p in r['points']),max(p[1] for p in r['points'])]
payload=dict(version=1,roads=roads,labels=labels,water=water,sources=sources,attribution='OpenStreetMap contributors; US Forest Service; Washington State Department of Transportation',license_url='https://www.openstreetmap.org/copyright')
out=args.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(gzip.compress(json.dumps(payload,separators=(',',':')).encode(),mtime=0))
print(dict(roads=len(roads),labels=len(labels),water=len(water),bytes=out.stat().st_size))
