#!/usr/bin/env python3
"""Laptop-only: compile local USGS elevation and OSM water into shaded relief."""
import argparse,base64,gzip,json,math
from pathlib import Path
import zlib
import numpy as np
from PIL import Image,ImageDraw
from shapely.geometry import LineString,Polygon,box
from shapely.ops import polygonize,unary_union
from shapely.strtree import STRtree


def build(elevation,metadata,osm,output):
    extent=json.loads(Path(metadata).read_text())['extent']
    west,south,east,north=[extent[k] for k in ('xmin','ymin','xmax','ymax')]
    height=np.asarray(Image.open(elevation),dtype=np.float32).copy();rows,cols=height.shape
    valid=np.isfinite(height)&(height>-500)&(height<5000)
    if not valid.any():raise ValueError('No valid elevation samples')
    height[~valid]=float(np.median(height[valid]))
    dx=(east-west)*111320*math.cos(math.radians((north+south)/2))/(cols-1)
    dy=(north-south)*111320/(rows-1)
    smooth=sum(np.roll(np.roll(height,y,axis=0),x,axis=1) for y in (-1,0,1) for x in (-1,0,1))/9
    gy,gx=np.gradient(smooth,dy,dx);nx=-gx*2;ny=gy*2
    light=(-nx+ny+1)/np.sqrt(nx*nx+ny*ny+1)/math.sqrt(3)
    shade=np.clip(np.floor((light-.28)*9),0,3).astype(np.uint8)
    boundary=box(west,south,east,north);coasts=[];segments=[];lakes=[]
    source=json.loads(Path(osm).read_text())
    for el in source['elements']:
        tags=el.get('tags',{});pts=[(p['lon'],p['lat']) for p in el.get('geometry',[]) if 'lon' in p]
        if tags.get('natural')=='coastline' and len(pts)>1:
            line=LineString(pts)
            if not line.intersects(boundary):continue
            coasts.append(line.intersection(boundary))
            segments.extend(LineString([a,b]) for a,b in zip(pts,pts[1:]) if a!=b)
        elif tags.get('natural')=='water':
            if len(pts)>3 and pts[0]==pts[-1]:lakes.append(Polygon(pts))
            elif el['type']=='relation':
                outer=[];inner=[]
                for member in el.get('members',[]):
                    points=[(p['lon'],p['lat']) for p in member.get('geometry',[]) if 'lon' in p]
                    if len(points)>1:(inner if member.get('role')=='inner' else outer).append(LineString(points))
                holes=unary_union(list(polygonize(unary_union(inner)))) if inner else None
                if outer:lakes.extend(p.difference(holes) if holes is not None else p for p in polygonize(unary_union(outer)))
    water=Image.new('L',(cols,rows));draw=ImageDraw.Draw(water)
    def pixels(points):return [((x-west)/(east-west)*(cols-1),(north-y)/(north-south)*(rows-1)) for x,y in points]
    def paint(poly,value):
        if poly.is_empty:return
        if poly.geom_type!='Polygon':
            for part in getattr(poly,'geoms',[]):paint(part,value)
            return
        draw.polygon(pixels(poly.exterior.coords),fill=value)
        for ring in poly.interiors:draw.polygon(pixels(ring.coords),fill=0)
    if segments:
        tree=STRtree(segments)
        for face in polygonize(unary_union(coasts+[boundary.boundary])):
            point=face.representative_point();a,b=segments[int(tree.nearest(point))].coords
            if (b[0]-a[0])*(point.y-a[1])-(b[1]-a[1])*(point.x-a[0])<0:paint(face,1)
    for lake in lakes:
        if lake.intersects(boundary):paint(lake.intersection(boundary),2)
    raw=(np.asarray(water,dtype=np.uint8)|(shade<<2)).tobytes()
    pack=dict(version=1,name='Lakewood fine relief',bbox=[west,south,east,north],labels=[],lines=[],max_span_km=20,fast_samples=True,
              water_classes={'1':'sea','2':'inland water'},
              terrain=dict(render='hillshade',source='USGS 3DEP',source_url='https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer',spacing_m=[round(dx,1),round(dy,1)],elevation_range_m=[round(float(height.min()),1),round(float(height.max()),1)],vertical_exaggeration=2),
              raster=dict(width=cols,height=rows,encoding='zlib-base64-u8',data=base64.b64encode(zlib.compress(raw,9)).decode()),
              attribution='Elevation: USGS 3DEP (public domain); water: OpenStreetMap contributors (ODbL)',license_url='https://www.openstreetmap.org/copyright')
    output=Path(output)
    with gzip.open(output,'wt') as f:json.dump(pack,f,separators=(',',':'))
    Path(str(output)[:-8]+'.meta.json').write_text(json.dumps({k:v for k,v in pack.items() if k!='lines'},separators=(',',':')))
    print(json.dumps(dict(spacing_m=pack['terrain']['spacing_m'],elevation_range_m=pack['terrain']['elevation_range_m'],size_bytes=output.stat().st_size,pixels=[cols,rows])))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('elevation','metadata','osm','output'):p.add_argument(name)
    args=p.parse_args();build(args.elevation,args.metadata,args.osm,args.output)
