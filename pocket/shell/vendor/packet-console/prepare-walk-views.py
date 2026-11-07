#!/usr/bin/env python3
"""Laptop-only: pre-render common walk views with the deployed map fingerprint."""
import argparse,importlib.util,json,math
from pathlib import Path
ROOT=Path(__file__).parent

def module(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('logs');p.add_argument('fingerprint');p.add_argument('output');p.add_argument('--callsign',default='N0DEM')
 args=p.parse_args();maps=module('prepared_maps','n810-map.py');history=module('prepared_history','n810-walk-history.py')
 archive=history.load(args.logs,args.callsign)
 if not archive:p.error('No saved walk found')
 track=archive[0]['track'];a=maps.Atlas(str(ROOT/'maps'),args.output)
 a.fingerprint=[tuple(r) for r in json.loads(Path(args.fingerprint).read_text())]
 low,high=min(p['lat'] for p in track),max(p['lat'] for p in track);west,east=min(p['lon'] for p in track),max(p['lon'] for p in track)
 center=((low+high)/2,(west+east)/2)
 span=max(.5,(east-west)*111.32*math.cos(math.radians(center[0]))*1.2,(high-low)*111.32*130/27/2*1.2)
 for width in (130,65):
  for scale in (span,span/2,span*2,.5,1,2,4):a.background(center,scale,width,27,True)
 for scale in (span,span/2,span*2):
  for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
   c=(round(center[0]+dy*scale*.2/111.32,6),round(center[1]+dx*scale*.2/(111.32*math.cos(math.radians(center[0]))),6))
   a.background(c,scale,130,27,True)
 files=list(Path(args.output).glob('*.bin'))
 print('Prepared',len(files),'views;',sum(f.stat().st_size for f in files),'bytes')
