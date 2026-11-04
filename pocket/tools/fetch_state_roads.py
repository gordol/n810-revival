"""Cache all WSDOT 1:24K state route lines, with pagination checked."""
from pathlib import Path
import json,gzip,urllib.parse,urllib.request
URL='https://data.wsdot.wa.gov/arcgis/rest/services/Shared/LRSData/FeatureServer/4/query'
def main():
 features=[];offset=0
 while True:
  q=dict(f='json',where='1=1',outSR=4326,outFields='*',returnGeometry='true',maxAllowableOffset=.0001,resultRecordCount=1000,resultOffset=offset,orderByFields='OBJECTID')
  with urllib.request.urlopen(URL+'?'+urllib.parse.urlencode(q),timeout=40) as r:d=json.load(r)
  if d.get('error'):raise ValueError(d['error'])
  rows=d.get('features',[]);features+=rows;print(len(features),'state route segments cached',flush=True)
  if not d.get('exceededTransferLimit'):break
  if not rows:raise ValueError('Incomplete route pagination')
  offset+=len(rows)
 out=Path(__file__).resolve().parents[1]/'data/state-roads-source.json.gz'
 tmp=out.with_suffix('.tmp');tmp.write_bytes(gzip.compress(json.dumps(dict(features=features,source_url=URL),separators=(',',':')).encode()));tmp.replace(out)
if __name__=='__main__':main()
