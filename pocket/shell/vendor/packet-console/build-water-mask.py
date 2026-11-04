"""Laptop-only: compile OSM coastlines/lakes to a small raster base for the N810.
Requires Pillow and Shapely. The runtime viewer needs neither.
"""
import argparse,base64,gzip,json,math,pathlib,zlib
from PIL import Image,ImageDraw
from shapely.geometry import LineString,Point,box,Polygon
from shapely.ops import unary_union,polygonize
from shapely.strtree import STRtree

p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('pack');a=p.parse_args()
source=json.loads(pathlib.Path(a.source).read_text());pack=json.load(gzip.open(a.pack,'rt'))
w,s,e,n=pack['bbox'];boundary=box(w,s,e,n);coasts=[];segments=[];lakes=[];roads=[]
for el in source['elements']:
 tags=el.get('tags',{});geom=el.get('geometry',[])
 pts=[(g['lon'],g['lat']) for g in geom if 'lon' in g and 'lat' in g]
 if tags.get('natural')=='coastline' and len(pts)>1:
  coasts.append(LineString(pts))
  segments.extend(LineString([x,y]) for x,y in zip(pts,pts[1:]) if x!=y)
 elif tags.get('highway') in ('motorway','trunk') and len(pts)>1:roads.append(pts)
 elif tags.get('natural')=='water':
  if len(pts)>3 and pts[0]==pts[-1]:lakes.append(Polygon(pts))
  elif el['type']=='relation':
   outers=[];inners=[]
   for member in el.get('members',[]):
    pp=[(g['lon'],g['lat']) for g in member.get('geometry',[]) if 'lon' in g]
    if len(pp)>1:(inners if member.get('role')=='inner' else outers).append(LineString(pp))
   outer=list(polygonize(unary_union(outers))) if outers else []
   inner=unary_union(list(polygonize(unary_union(inners)))) if inners else None
   lakes.extend(poly.difference(inner) if inner is not None else poly for poly in outer)
faces=list(polygonize(unary_union([line.intersection(boundary) for line in coasts]+[boundary.boundary])))
tree=STRtree(segments);width,height=960,round((n-s)/(e-w)*960)
image=Image.new('L',(width,height));draw=ImageDraw.Draw(image)
def pixel(points):return [((x-w)/(e-w)*(width-1),(n-y)/(n-s)*(height-1)) for x,y in points]
def paint(poly,value):
 if poly.is_empty:return
 if poly.geom_type!='Polygon':
  for part in getattr(poly,'geoms',[]):paint(part,value)
  return
 draw.polygon(pixel(poly.exterior.coords),fill=value)
 for ring in poly.interiors:draw.polygon(pixel(ring.coords),fill=0)
water=0
for face in faces:
 pt=face.representative_point();segment=segments[int(tree.nearest(pt))];(x,y),(xx,yy)=segment.coords
 # OSM coastlines have land on the left, sea on the right.
 cross=(xx-x)*(pt.y-y)-(yy-y)*(pt.x-x)
 if cross<0:paint(face,1);water+=1
for lake in lakes:
 if lake.area>.00015:paint(lake.intersection(boundary),2)
road=Image.new('L',image.size);rd=ImageDraw.Draw(road)
for pts in roads:rd.line(pixel(pts),fill=2,width=1)
raw=bytes(x|y for x,y in zip(image.tobytes(),road.tobytes()))
pack['raster']=dict(width=width,height=height,encoding='zlib-base64-u8',data=base64.b64encode(zlib.compress(raw,9)).decode())
with gzip.open(a.pack,'wt') as f:json.dump(pack,f,separators=(',',':'))
pathlib.Path(a.pack[:-8]+'.meta.json').write_text(json.dumps({k:v for k,v in pack.items() if k!='lines'},separators=(',',':')))
image.point(lambda p:180 if p else 30).save('/tmp/puget-water-mask.png')
pack['water_classes']={'1':'sea','2':'inland water'}
# Rewrite metadata after adding the water-class contract.
with gzip.open(a.pack,'wt') as f:json.dump(pack,f,separators=(',',':'))
pathlib.Path(a.pack[:-8]+'.meta.json').write_text(json.dumps({k:v for k,v in pack.items() if k!='lines'},separators=(',',':')))
print(len(faces),'coast faces;',water,'water faces;',len(lakes),'lakes;',len(raw),'raw pixels;',len(pack['raster']['data']),'encoded bytes')
