"""Build Pocket's offline scenery database from an OSM or Overture GeoJSON sequence."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'graphics'))
from pnw.terrain import layout, pixel

def build(files,target,*,buildings=(),places=()):
    cx,cy,spacing=layout('sound')
    def project(lon,lat):
        x,y=pixel(lat,lon,9)
        return round((x-cx)*spacing*5),round((cy-y)*spacing*5)
    db=sqlite3.connect(target)
    db.execute('CREATE TABLE features (tx INTEGER,tz INTEGER,model TEXT,data BLOB)')
    counts=Counter()
    def store(x,z,kind,data):
        counts[kind]+=1
        db.execute('INSERT INTO features VALUES (?,?,?,?)',(x//5120,z//5120,kind,
                   zlib.compress(json.dumps(data,separators=(',',':')).encode(),1)))
    inputs = [(file, 'tagged') for file in files]
    inputs.extend((file, 'building') for file in buildings)
    inputs.extend((file, 'place') for file in places)
    for file, layer in inputs:
        with file.open('rb') as source:
            for line in source:
                feature=json.loads(line.lstrip(b'\x1e'))
                props=feature['properties'];geometry=feature['geometry']
                if not geometry:continue
                coords=geometry['coordinates'];kind=geometry['type']
                name=props.get('name') or (props.get('names') or {}).get('primary','')
                if kind=='Point':
                    if props.get('natural')=='tree':model='tree'
                    elif name and (layer=='place' or any(props.get(k) for k in ('amenity','shop','tourism','categories'))):model='place'
                    else:continue
                    x,z=project(*coords[:2]);store(x,z,model,[x,z,name])
                elif kind in ('MultiPolygon','Polygon') and (layer=='building' or 'building' in props or props.get('subtype')=='building' or 'num_floors' in props):
                    try:height=float(props.get('height') or float(props.get('building:levels') or props.get('num_floors') or 0)*3.15)
                    except (TypeError,ValueError):height=0
                    if not 1<height<500:height=7.5
                    for polygon in coords if kind=='MultiPolygon' else [coords]:
                        ring=[project(*p[:2]) for p in polygon[0][:-1]]
                        if len(ring)<3:continue
                        x=sum(p[0] for p in ring)//len(ring);z=sum(p[1] for p in ring)//len(ring)
                        store(x,z,'building',[round(height,1),[[px-x,pz-z] for px,pz in ring],x,z,len(polygon)==1])
    db.execute('CREATE INDEX tiles ON features(tx,tz)')
    db.commit();db.close()
    return counts

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('output',type=Path);p.add_argument('geojsonseq',nargs='*',type=Path)
    p.add_argument('--overture-buildings', action='append', type=Path, default=[],
                   help='GeoJSON sequence exported from the Overture building layer')
    p.add_argument('--overture-places', action='append', type=Path, default=[],
                   help='GeoJSON sequence exported from the Overture place layer')
    args=p.parse_args()
    if not (args.geojsonseq or args.overture_buildings or args.overture_places):
        p.error('supply at least one input sequence')
    print(build(args.geojsonseq,args.output,buildings=args.overture_buildings,places=args.overture_places))
