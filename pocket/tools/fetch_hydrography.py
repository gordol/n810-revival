"""Cache complete DNR water polygons for a requested region; publish atomically."""
from pathlib import Path
import argparse,json,gzip,urllib.parse,urllib.request,datetime
URL='https://gis.dnr.wa.gov/site2/rest/services/Public_Forest_Practices/WADNR_PUBLIC_FP_Hydro/MapServer/1/query'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bbox',nargs=4,type=float,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 features=[];offset=0;ids=set()
 while True:
  q=dict(f='geojson',where='1=1',geometry=','.join(map(str,a.bbox)),geometryType='esriGeometryEnvelope',inSR=4326,outSR=4326,outFields='OBJECTID,WB_CART_FTR_CD,WB_CART_FTR_LABEL_NM,WB_HYDR_FTR_LABEL_NM,WB_GNIS_NM',returnGeometry='true',maxAllowableOffset=.00001,resultOffset=offset,resultRecordCount=1000,orderByFields='OBJECTID')
  with urllib.request.urlopen(URL+'?'+urllib.parse.urlencode(q),timeout=60) as r:d=json.load(r)
  if d.get('error'):raise ValueError(d['error'])
  rows=d.get('features',[])
  for f in rows:
   ident=f.get('id',f.get('properties',{}).get('OBJECTID'))
   if ident in ids:raise ValueError('Repeated page: refusing incomplete dataset')
   ids.add(ident)
  features+=rows;print(len(features),'water polygons downloaded',flush=True)
  if not d.get('exceededTransferLimit') and len(rows)<1000:break
  if not rows:break
  offset+=len(rows)
 # Confirm pagination independently before publishing any replacement.
 q=dict(f='json',where='1=1',geometry=','.join(map(str,a.bbox)),geometryType='esriGeometryEnvelope',inSR=4326,returnCountOnly='true')
 with urllib.request.urlopen(URL+'?'+urllib.parse.urlencode(q),timeout=60) as r:count=json.load(r)['count']
 if count!=len(features):raise ValueError(f'Incomplete download: {len(features)} of {count}')
 payload=dict(type='FeatureCollection',features=features,coverage=a.bbox,source_url=URL,downloaded=datetime.datetime.now(datetime.timezone.utc).isoformat(),complete=True,feature_count=count)
 a.output.parent.mkdir(parents=True,exist_ok=True);tmp=a.output.with_suffix('.tmp');tmp.write_bytes(gzip.compress(json.dumps(payload,separators=(',',':')).encode()));tmp.replace(a.output)
if __name__=='__main__':main()
