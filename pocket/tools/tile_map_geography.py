"""Spatially tile a regional named-road/stream snapshot for bounded map reads."""
from pathlib import Path
import gzip,json,math,hashlib,argparse

def build(source,out):
 raw=source.read_bytes();d=json.loads(gzip.decompress(raw));step=.25;groups={};coverage=d['coverage'];w,s,e,n=coverage
 for kind in ('roads','streams'):
  for row in d.get(kind,[]):
   a,b,c,f=row['bbox']
   for iy in range(math.floor(max(b,s)/step),math.floor(min(f,n)/step)+1):
    for ix in range(math.floor(max(a,w)/step),math.floor(min(c,e)/step)+1):groups.setdefault((ix,iy),dict(roads=[],streams=[]))[kind].append(row)
 digest=hashlib.sha256(raw).hexdigest();folder=out/digest[:16];folder.mkdir(parents=True,exist_ok=True);tiles={}
 for (ix,iy),rows in groups.items():
  name=f'{ix}_{iy}.json.gz';encoded=gzip.compress(json.dumps(rows,separators=(',',':')).encode());(folder/name).write_bytes(encoded)
  tiles[f'{ix},{iy}']=dict(file=f'{folder.name}/{name}',sha256=hashlib.sha256(encoded).hexdigest())
 from shapely.geometry import LineString
 overview=[]
 for row in d['roads']:
  if row['kind'] not in ('motorway','trunk','primary'):continue
  value=dict(row);value['points']=list(LineString(row['points']).simplify(.001).coords);overview.append(value)
 index=dict(version=2,coverage=coverage,step=step,tiles=tiles,labels=d['labels'],roads=[],overview_roads=overview,water=[],source_sha256=digest,attribution=d['attribution'],license_url=d['license_url'],downloaded=d['downloaded'])
 p=out/'index.tmp';p.write_text(json.dumps(index,separators=(',',':')));p.replace(out/'index.json');print(dict(tiles=len(tiles),roads=len(d['roads']),streams=len(d['streams'])),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();build(a.source,a.output)
