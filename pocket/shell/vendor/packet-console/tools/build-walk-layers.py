#!/usr/bin/env python3
"""Laptop-only preparation of Walk bands, water fallback, and indexed roads."""
import argparse,base64,gzip,json,marshal,math,struct,zlib
from pathlib import Path
import numpy as np
from PIL import Image
from shapely.geometry import LineString
from shapely.affinity import scale


def read(path):
    with gzip.open(path,'rt') as f:return json.load(f)


def roads(path,tile,tolerance):
    original=read(path);segments=[];index={}
    for bounds,points in original:
        if tolerance:
            line=scale(LineString([(x/100000,y/100000) for x,y in points]),xfact=.68,yfact=1,origin=(0,0))
            line=scale(line.simplify(tolerance/111320,preserve_topology=False),xfact=1/.68,yfact=1,origin=(0,0))
            points=[(round(x*100000),round(y*100000)) for x,y in line.coords]
        for (x,y),(xx,yy) in zip(points,points[1:]):
            if (x,y)==(xx,yy):continue
            i=len(segments)//4;segments.extend((x,y,xx,yy))
            for by in range(min(y,yy)//tile,max(y,yy)//tile+1):
                for bx in range(min(x,xx)//tile,max(x,xx)//tile+1):index.setdefault((bx,by),[]).append(i)
    return dict(tile=tile,segments=struct.pack('<%di'%len(segments),*segments),index={k:tuple(v) for k,v in index.items()}),len(segments)//4


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--maps',required=True);p.add_argument('--bands',required=True);p.add_argument('--output',required=True);p.add_argument('--elevation',required=True);p.add_argument('--streams',required=True);a=p.parse_args();folder=Path(a.maps)
    raw=Path(a.bands).read_bytes();band=marshal.loads(zlib.decompress(raw[4:]));grids=[]
    for name in ('pnw-overview','puget-sound'):
        d=read(folder/(name+'.json.gz'));r=d['raster'];pixels=zlib.decompress(base64.b64decode(r['data']))
        grids.append(dict(name=d['name'],bbox=d['bbox'],width=r['width'],height=r['height'],pixels=bytes(0 if v&3 else 1+(v>>2) for v in pixels),heights=False,regional_bands_m=d.get('terrain',{}).get('bands_m',[])))
    grids.append(dict(name='Lakewood 25 m bands',bbox=band['bbox'],width=band['width'],height=band['height'],pixels=band['pixels'],heights=True))
    heights=np.asarray(Image.open(a.elevation));fine=np.clip(np.floor(heights/5)+1,0,254).astype(np.uint8);fine[np.frombuffer(band['pixels'],dtype=np.uint8).reshape(heights.shape)==0]=255
    grids[-1]['fine']=fine.tobytes()
    streams=json.loads(Path(a.streams).read_text());ways=[]
    for way in streams['elements']:
        points=[(round(v['lon']*100000),round(v['lat']*100000)) for v in way['geometry']]
        ways.append((None,points))
    stream_path=Path(a.output+'.streams.tmp.gz')
    with gzip.open(stream_path,'wt') as f:json.dump(ways,f)
    water,wc=roads(stream_path,500,2);stream_path.unlink()
    local,lc=roads(folder/'lakewood-walk.roads.gz',500,3)
    major,mc=roads(folder/'puget-sound.roads.gz',5000,0)
    pack=dict(version=1,grids=grids,roads=[local,major],streams=water,thresholds=band['thresholds'],palette=band['palette'],height_source_sha256=band['source_sha256'],profiles={'walk_max_km':5,'walk':'local streets + major routes','wide':'major motorway/trunk routes'},meaning='Local 25m fills with scale-dependent 5/10/25m boundaries and indexed streams. Outside local heights: regional land/water only.')
    payload=marshal.dumps(pack,2);data=b'N8W1'+zlib.compress(payload,9);Path(a.output).write_bytes(data)
    report=dict(file_bytes=len(data),decoded_bytes=len(payload),local_segments=lc,major_segments=mc,thresholds=band['thresholds'],grids=[{k:v for k,v in g.items() if k not in ('pixels','fine')} for g in grids])
    Path(a.output+'.meta.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
