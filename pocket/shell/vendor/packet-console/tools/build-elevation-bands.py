#!/usr/bin/env python3
"""Laptop-only: exclusive categorical grid and lossless tiled band polygons."""
import argparse,base64,gzip,hashlib,json,marshal,math,struct,time,zlib
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import LineString,box
from shapely.ops import polygonize,unary_union
from shapely.strtree import STRtree

THRESHOLDS=(25,50,75,100,125)
Q=16
TILE=64

def spans(bits):
    changes=np.flatnonzero(np.diff(np.r_[False,bits,False]))
    return zip(changes[::2],changes[1::2])

def polygons(labels):
    height,width=labels.shape;lines=[]
    for y in range(height+1):
        different=np.ones(width,dtype=bool) if y in (0,height) else labels[y-1]!=labels[y]
        lines.extend(LineString(((int(a),y),(int(b),y))) for a,b in spans(different))
    for x in range(width+1):
        different=np.ones(height,dtype=bool) if x in (0,width) else labels[:,x-1]!=labels[:,x]
        lines.extend(LineString(((x,int(a)),(x,int(b)))) for a,b in spans(different))
    faces=[];bands=[]
    for face in polygonize(unary_union(lines)):
        p=face.representative_point();band=int(labels[min(height-1,int(p.y)),min(width-1,int(p.x))])
        faces.append(face.simplify(0,preserve_topology=True));bands.append(band)
    if abs(sum(p.area for p in faces)-width*height)>1e-6:raise ValueError('Non-exclusive or incomplete topology')
    return faces,bands,len(lines)

def components(shape):
    if shape.is_empty:return
    if shape.geom_type=='Polygon':yield shape
    else:
        for part in getattr(shape,'geoms',()):yield from components(part)

def vectorize(labels):
    height,width=labels.shape;faces,bands,line_count=polygons(labels);tree=STRtree(faces)
    points=[];rings=[];features=[];index={};nx=math.ceil(width/TILE);ny=math.ceil(height/TILE)
    for ty in range(ny):
        for tx in range(nx):
            tile=box(tx*TILE,ty*TILE,min(width,(tx+1)*TILE),min(height,(ty+1)*TILE));ids=[]
            for i in tree.query(tile,predicate='intersects'):
                for p in components(faces[int(i)].intersection(tile)):
                    if p.area<=0:continue
                    first=len(rings)
                    for ring in (p.exterior,*p.interiors):
                        xy=[(round(x*Q),round(y*Q)) for x,y in list(ring.coords)[:-1]]
                        rings.append((len(points)//2,len(xy)))
                        for x,y in xy:points.extend((x,y))
                    features.append((bands[int(i)],*[round(v*Q) for v in p.bounds],first,len(rings)-first));ids.append(len(features)-1)
            index[ty*nx+tx]=tuple(ids)
    raw=struct.pack('<%dH'%len(points),*points)
    return dict(q=Q,tile=TILE,nx=nx,ny=ny,features=features,rings=rings,points=raw,index=index),dict(original_polygons=len(faces),original_holes=sum(len(p.interiors) for p in faces),boundary_segments=line_count,tiled_features=len(features),tiled_rings=len(rings),vertices=len(points)//2,coordinate_bytes=len(raw))

def save(path,value):
    raw=marshal.dumps(value,2);packed=b'N8B1'+zlib.compress(raw,9);path.write_bytes(packed)
    return dict(file_bytes=len(packed),decoded_bytes=len(raw))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('elevation');p.add_argument('metadata');p.add_argument('water_pack');p.add_argument('output')
    a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True);start=time.monotonic()
    heights=np.asarray(Image.open(a.elevation),dtype=np.float32)
    valid=np.isfinite(heights)&(heights>-500)&(heights<5000)
    if not valid.all():raise ValueError('Prototype requires explicit handling of invalid source heights')
    meta=json.loads(Path(a.metadata).read_text());e=meta['extent'];bbox=[e[k] for k in ('xmin','ymin','xmax','ymax')]
    water_pack=json.load(gzip.open(a.water_pack,'rt'));r=water_pack['raster']
    if heights.shape!=(r['height'],r['width']) or not np.allclose(bbox,water_pack['bbox']):raise ValueError('Water/height grids differ')
    water=np.frombuffer(zlib.decompress(base64.b64decode(r['data'])),dtype=np.uint8).reshape(heights.shape)&3
    labels=(np.digitize(heights,THRESHOLDS)+1).astype(np.uint8);labels[water!=0]=0
    height,width=labels.shape
    common=dict(version=1,bbox=bbox,width=width,height=height,thresholds=THRESHOLDS,no_data=7,palette=(4,0,8,2,3,6,7,0),source_sha256=hashlib.sha256(Path(a.elevation).read_bytes()).hexdigest(),meaning='0 water; land 1:<25m, 2:25-50m, 3:50-75m, 4:75-100m, 5:100-125m, 6:>=125m; 7 outside coverage')
    grid=dict(common,kind='grid',pixels=labels.tobytes())
    vectors,stats=vectorize(labels);vector=dict(common,kind='vector',**vectors)
    report=dict(source=common,grid=save(out/'grid.n8b',grid),vector=save(out/'vector.n8b',vector),topology=stats,prepare_seconds=time.monotonic()-start)
    (out/'manifest.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
