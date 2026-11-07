#!/usr/bin/env python3
"""Prepare offline, filtered height/shade levels from existing USGS TIFFs."""
import argparse, hashlib, json, marshal, math, zlib
from pathlib import Path
import numpy as np
from PIL import Image

NODATA=-32768

def pyramid(image,metadata,name):
    extent=json.loads(Path(metadata).read_text())['extent']
    bbox=[extent[k] for k in ('xmin','ymin','xmax','ymax')]
    with np.errstate(invalid='ignore'):a=np.asarray(Image.open(image),dtype=np.float64)
    a=np.where(np.isfinite(a)&(a>-500)&(a<6000),a,np.nan)
    levels=[]
    while True:
        h,w=a.shape
        dx=(bbox[2]-bbox[0])*111320*math.cos(math.radians((bbox[1]+bbox[3])/2))/w
        dy=(bbox[3]-bbox[1])*111320/h
        valid=np.isfinite(a);safe=np.where(valid,a,0)
        gy,gx=np.gradient(safe,dy,dx);nx=-gx*2;ny=gy*2
        light=(-nx+ny+1)/np.sqrt(nx*nx+ny*ny+1)/math.sqrt(3)
        shade=np.clip(np.floor((light-.28)*9),0,3).astype(np.uint8)
        border=valid.copy()
        border[1:]&=valid[:-1];border[:-1]&=valid[1:];border[:,1:]&=valid[:,:-1];border[:,:-1]&=valid[:,1:]
        shade[~border]=1
        heights=np.where(valid,np.rint(a),NODATA).astype('<i2')
        shade[~valid]=255
        levels.append(dict(width=w,height=h,spacing_m=[dx,dy],heights=heights.tobytes(),shade=shade.tobytes()))
        if min(w,h)<32:break
        padded=np.full((h+h%2,w+w%2),np.nan);padded[:h,:w]=a
        blocks=padded.reshape((padded.shape[0]//2,2,padded.shape[1]//2,2))
        count=np.isfinite(blocks).sum(axis=(1,3));total=np.nansum(blocks,axis=(1,3))
        a=np.divide(total,count,out=np.full_like(total,np.nan),where=count>0)
    return dict(name=name,bbox=bbox,source_sha256=hashlib.sha256(Path(image).read_bytes()).hexdigest(),levels=levels)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--regional',required=True);p.add_argument('--regional-meta',required=True)
    p.add_argument('--local',required=True);p.add_argument('--local-meta',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();layers=[pyramid(a.regional,a.regional_meta,'Puget USGS 3DEP'),pyramid(a.local,a.local_meta,'Lakewood USGS 3DEP')]
    payload=marshal.dumps(dict(version=1,nodata=NODATA,layers=layers),2)
    data=b'N8T1'+zlib.compress(payload,9);Path(a.output).write_bytes(data)
    report=dict(file_bytes=len(data),decoded_bytes=len(payload),layers=[dict(name=l['name'],bbox=l['bbox'],source_sha256=l['source_sha256'],levels=[{k:v for k,v in level.items() if k not in ('heights','shade')} for level in l['levels']]) for l in layers])
    Path(a.output+'.meta.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
