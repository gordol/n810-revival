#!/usr/bin/env python3
"""Resume raw USGS exports; publish verified regional elevation packs atomically."""
import argparse,concurrent.futures,json,shutil,sys,time,urllib.parse,urllib.request
from pathlib import Path
from prepare_elevation_tiles import prepare
BASE='https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage'
def fetch(job):
 name,bbox,root,downloads=job;target=root/(name+'-guarded')
 if (target/'index.json').is_file() and json.loads((target/'index.json').read_text()).get('sparse_tiff_safe') and json.loads((target/'index.json').read_text()).get('maximum_allowed_m')==5000:return name,'cached'
 folder=downloads/name;folder.mkdir(parents=True,exist_ok=True)
 for attempt in range(5):
  try:
   width=max(256,round(4096*(bbox[2]-bbox[0])/.5))
   params=dict(bbox=','.join(map(str,bbox)),bboxSR=4326,imageSR=4326,size=f'{width},3072',format='tiff',pixelType='F32',interpolation='RSP_BilinearInterpolation',adjustAspectRatio='false',renderingRule=json.dumps({'rasterFunction':'None'}),f='json')
   url=BASE+'?'+urllib.parse.urlencode(params)
   if not (folder/'raw.tif').is_file():
    with urllib.request.urlopen(url,timeout=180) as response:d=json.load(response)
    if 'href' not in d:raise ValueError(str(d))
    (folder/'export.json').write_text(json.dumps(dict(request_url=url,response=d)))
    with urllib.request.urlopen(d['href'],timeout=240) as response,(folder/'raw.part').open('wb') as out:shutil.copyfileobj(response,out)
    (folder/'raw.part').replace(folder/'raw.tif')
   temporary=root/(name+'-guarded.building')
   if temporary.exists():shutil.rmtree(temporary)
   # Western Washington's highest summit is below 5000 m. Larger values in
   # coastal NoData boundaries are invalid export artifacts, not terrain.
   report=prepare(folder/'raw.tif',folder/'export.json',temporary,maximum_allowed_m=5000,allow_empty=True)
   backup=root/(name+'.previous')
   if backup.exists():shutil.rmtree(backup)
   if target.exists():target.rename(backup)
   temporary.replace(target)
   if backup.exists():shutil.rmtree(backup)
   return name,report
  except Exception as error:
   if 'truncated' in str(error).lower() and (folder/'raw.tif').exists():
    (folder/'raw.tif').replace(folder/f'rejected-{attempt}.tif')
   if attempt==4:return name,dict(error=str(error))
   time.sleep(min(30,2**attempt))
def main():
 p=argparse.ArgumentParser();p.add_argument('--workers',type=int,default=2);p.add_argument('--limit',type=int);a=p.parse_args()
 project=Path(__file__).resolve().parents[1];root=project/'data/elevation-fine';downloads=project.parent/'outputs/regional-fine-dem-20261102'
 root.mkdir(parents=True,exist_ok=True);downloads.mkdir(parents=True,exist_ok=True)
 jobs=[]
 for iy in range(8):
  for ix in range(9):
   west=round(-124.8+ix*.5,6);south=round(46.3+iy*.3,6)
   jobs.append((f'wa-{ix:02}-{iy:02}',(west,south,min(-120.6,round(west+.5,6)),round(south+.3,6)),root,downloads))
 jobs.sort(key=lambda job:abs((job[1][0]+job[1][2])/2+122.8)+abs((job[1][1]+job[1][3])/2-47.1))
 if a.limit:jobs=jobs[:a.limit]
 results={}
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
  futures=[pool.submit(fetch,job) for job in jobs]
  for f in concurrent.futures.as_completed(futures):
   name,result=f.result();results[name]=result
   print(json.dumps(dict(tile=name,result=result,completed=len(results),total=len(jobs))),flush=True)
   (downloads/'progress.json').write_text(json.dumps(results,indent=2))
 failures={k:v for k,v in results.items() if isinstance(v,dict) and 'error' in v}
 print(json.dumps(dict(finished=len(results),failures=failures)),flush=True)
 return bool(failures)
if __name__=='__main__':sys.exit(main())
