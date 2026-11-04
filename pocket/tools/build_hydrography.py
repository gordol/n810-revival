"""Build spatial tiles from a complete polygon hydrography snapshot, any region."""
from pathlib import Path
import argparse,json,gzip,hashlib,math,os
from shapely.geometry import shape,box,mapping
from shapely import make_valid
WATER_CODES={100,101,106,107,109,110,116,400,401,402,407,408,412,414,419,420,421,425}
def build(source,out,step=.25):
 raw=source.read_bytes();data=json.loads(gzip.decompress(raw))
 if not data.get('complete') or len(data['features'])!=data['feature_count']:raise ValueError('Hydrography snapshot is incomplete')
 west,south,east,north=data['coverage'];coverage=box(west,south,east,north)
 if data.get('coverage_geometry'):coverage=coverage.intersection(shape(data['coverage_geometry']))
 groups={};labels=[];classes={};repairs=0
 for f in data['features']:
  p=f['properties'];code=int(p.get('WB_CART_FTR_CD') or 0);classes[code]=classes.get(code,0)+1
  if code not in WATER_CODES or not f.get('geometry'):continue
  g=shape(f['geometry'])
  if not g.is_valid:g=make_valid(g);repairs+=1
  g=g.intersection(coverage)
  if g.is_empty:continue
  name=p.get('WB_GNIS_NM')
  if name:
   point=g.representative_point();labels.append(dict(name=name,lon=point.x,lat=point.y,kind='lake',max_span=max(4,min(150,math.sqrt(g.area)*2200))))
  a,b,c,d=g.bounds
  for iy in range(math.floor(b/step),math.floor(d/step)+1):
   for ix in range(math.floor(a/step),math.floor(c/step)+1):
    tilebox=box(ix*step,iy*step,(ix+1)*step,(iy+1)*step);part=g.intersection(tilebox)
    if part.is_empty:continue
    parts=[part] if part.geom_type=='Polygon' else list(getattr(part,'geoms',[]))
    for poly in parts:
     if poly.geom_type!='Polygon' or poly.is_empty:continue
     groups.setdefault((ix,iy),[]).append(dict(rings=[list(poly.exterior.coords)]+[list(r.coords) for r in poly.interiors]))
 identity=hashlib.sha256(raw).hexdigest();folder=out/identity[:16];folder.mkdir(parents=True,exist_ok=True);tiles={}
 for (ix,iy),polys in groups.items():
  raw=gzip.compress(json.dumps(polys,separators=(',',':')).encode());name=f'{ix}_{iy}.json.gz';(folder/name).write_bytes(raw)
  tiles[f'{ix},{iy}']=dict(file=f'{folder.name}/{name}',sha256=hashlib.sha256(raw).hexdigest())
 index=dict(version=1,coverage=data['coverage'],coverage_geometry=data.get('coverage_geometry'),step=step,tiles=tiles,labels=labels,complete=True,defines_land=data.get('defines_land',False),source_sha256=identity,source_url=data['source_url'],downloaded=data['downloaded'],feature_count=data['feature_count'],classes=classes,repaired=repairs)
 temporary=out/'index.tmp';temporary.write_text(json.dumps(index,separators=(',',':')));temporary.replace(out/'index.json')
 print(dict(features=data['feature_count'],tiles=len(tiles),labels=len(labels),repaired=repairs),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();build(a.source,a.output)
