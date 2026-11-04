#!/usr/bin/env python3
"""Build a portable offline console map from an OpenStreetMap Overpass extract."""
import argparse, datetime, gzip, json, math, pathlib, urllib.parse, urllib.request


def simplify(points, tolerance):
    if len(points) < 3:
        return points
    # Iterative Douglas-Peucker, in approximate kilometers.
    scale = math.cos(math.radians(sum(p[1] for p in points)/len(points)))
    xy = [(p[0]*111.32*scale, p[1]*111.32) for p in points]
    keep = {0, len(points)-1}; stack = [(0,len(points)-1)]
    while stack:
        a,b = stack.pop(); ax,ay=xy[a]; bx,by=xy[b]; dx,dy=bx-ax,by-ay
        best,index=0,None
        for i in range(a+1,b):
            x,y=xy[i]; t=max(0,min(1,((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy))) if dx or dy else 0
            dist=math.hypot(x-ax-t*dx,y-ay-t*dy)
            if dist>best: best,index=dist,i
        if best>tolerance:
            keep.add(index); stack.extend([(a,index),(index,b)])
    return [[round(x,5),round(y,5)] for i,(x,y) in enumerate(points) if i in keep]


def build(data, name, bbox, tolerance):
    if data.get('remark'):
        raise ValueError('Overpass reported an incomplete extract: '+data['remark'])
    lines=[]; labels=[]
    for e in data['elements']:
        tags=e.get('tags',{})
        if e['type']=='node' and tags.get('place') in ('city','town') and tags.get('name'):
            labels.append(dict(name=tags['name'],lon=e['lon'],lat=e['lat'],kind=tags['place'],population=int(''.join(c for c in tags.get('population','0') if c.isdigit()) or '0')))
        geometries=[]
        if e['type']=='way': geometries=[e.get('geometry',[])]
        elif e['type']=='relation': geometries=[m.get('geometry',[]) for m in e.get('members',[]) if m.get('role')=='outer']
        for geom in geometries:
            points=[[p['lon'],p['lat']] for p in geom if 'lon' in p and 'lat' in p]
            if len(points)<2: continue
            coast=tags.get('natural')=='coastline'
            road=tags.get('highway') in ('motorway','trunk')
            # Omit tiny ponds; retain coast segments of any size.
            width=(max(p[0] for p in points)-min(p[0] for p in points))*75
            height=(max(p[1] for p in points)-min(p[1] for p in points))*111
            if not coast and not road and max(width,height)<1.5: continue
            lines.append(dict(kind='road' if road else ('coast' if coast else 'water'),points=simplify(points,tolerance)))
    if not lines: raise ValueError('No geographic lines found')
    return dict(version=1,name=name,bbox=bbox,generated=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                attribution='(c) OpenStreetMap contributors | ODbL',license_url='https://www.openstreetmap.org/copyright',
                source_timestamp=data.get('osm3s',{}).get('timestamp_osm_base'),lines=lines,labels=labels)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bbox',nargs=4,type=float,metavar=('WEST','SOUTH','EAST','NORTH'),required=True)
    p.add_argument('--name',required=True);p.add_argument('--output',required=True)
    p.add_argument('--input',help='Previously downloaded Overpass JSON (no network)')
    p.add_argument('--save-source',help='Save raw extract for repeatable local builds')
    p.add_argument('--tolerance-km',type=float,default=.15)
    p.add_argument('--endpoint',default='https://overpass-api.de/api/interpreter')
    a=p.parse_args();w,s,e,n=a.bbox
    if not (-180<=w<e<=180 and -90<=s<n<=90) or a.tolerance_km<=0: p.error('Invalid bounds or tolerance')
    if a.input: data=json.loads(pathlib.Path(a.input).read_text())
    else:
        bbox=f'{s},{w},{n},{e}'
        query=f'[out:json][timeout:120];(way["natural"="coastline"]({bbox});way["natural"="water"]["water"!="swimming_pool"]({bbox});relation["natural"="water"]({bbox});node["place"~"^(city|town)$"]({bbox});way["highway"~"^(motorway|trunk)$"]({bbox}););out geom;'
        req=urllib.request.Request(a.endpoint,data=urllib.parse.urlencode({'data':query}).encode(),headers={'User-Agent':'N810-Offline-Map-Builder/1.0'})
        with urllib.request.urlopen(req,timeout=160) as response: data=json.load(response)
    if a.save_source: pathlib.Path(a.save_source).write_text(json.dumps(data))
    pack=build(data,a.name,a.bbox,a.tolerance_km)
    with gzip.open(a.output,'wt',encoding='utf-8') as f: json.dump(pack,f,separators=(',',':'))
    pathlib.Path(a.output[:-8]+'.meta.json').write_text(json.dumps({k:v for k,v in pack.items() if k!='lines'},separators=(',',':')))
    print(f'{a.output}: {len(pack["lines"])} lines, {len(pack["labels"])} places, {pathlib.Path(a.output).stat().st_size:,} bytes')

if __name__=='__main__':main()
