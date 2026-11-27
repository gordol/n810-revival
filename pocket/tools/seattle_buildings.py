"""Extract simple OSM building ways with height evidence from local .osm files.

Usage: python tools/seattle_buildings.py downtown.osm center.osm > buildings.json
Coordinates in output are longitude/latitude in integer ten-millionths of a degree.
"""
import json
import sys
import xml.etree.ElementTree as ET

def triangles(points):
    def cross(a,b,c):
        return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    ring=list(range(len(points)))
    area=sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1]))
    if area<0:ring.reverse()
    result=[]
    while len(ring)>2:
        for j,b in enumerate(ring):
            a,c=ring[j-1],ring[(j+1)%len(ring)]
            p,q,r=(points[k] for k in (a,b,c))
            turn=cross(p,q,r)
            if turn<0:continue
            if turn and any(cross(p,q,points[k])>=0 and cross(q,r,points[k])>=0 and
                            cross(r,p,points[k])>=0 for k in ring if k not in (a,b,c)):continue
            if turn:result.extend((a,b,c))
            ring.pop(j)
            break
        else:return []
    return result

def extract(path):
    root=ET.parse(path).getroot()
    nodes={n.get('id'):[round(float(n.get(k))*1e7) for k in ('lon','lat')] for n in root.findall('node')}
    compound={m.get('ref') for rel in root.findall('relation')
              if any(t.get('k')=='type' and t.get('v')=='multipolygon' for t in rel.findall('tag'))
              for m in rel.findall('member') if m.get('type')=='way'}
    result={}
    for way in root.findall('way'):
        tags={t.get('k'):t.get('v') for t in way.findall('tag')}
        refs=[n.get('ref') for n in way.findall('nd')]
        if way.get('id') in compound or 'building' not in tags or len(refs)<4 or refs[0]!=refs[-1]:continue
        pts=[nodes[k] for k in refs[:-1]]
        if len({tuple(p) for p in pts})!=len(pts):continue
        key='height' if tags.get('height') else 'building:levels'
        try:value=float(tags[key].removesuffix(' m'))
        except (KeyError,ValueError):continue
        if not 0<value<400:continue
        roof=triangles(pts)
        if roof:result[int(way.get('id'))]=[key,value,pts,roof]
    return result

if __name__=='__main__':
    buildings={}
    for path in sys.argv[1:]:buildings.update(extract(path))
    print(json.dumps(buildings,sort_keys=True,separators=(',',':')))
