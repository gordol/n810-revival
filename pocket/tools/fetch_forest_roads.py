"""Cache the official USFS road inventory for the western Washington region."""
from pathlib import Path
import urllib.parse,urllib.request,json,gzip
ROOT=Path(__file__).resolve().parents[1]
URL='https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_RoadBasic_01/MapServer/0/query'
def main():
 features=[];offset=0
 while True:
  q=dict(f='geojson',where='1=1',geometry='-124.8,46.3,-120.6,48.7',geometryType='esriGeometryEnvelope',inSR=4326,outSR=4326,outFields='objectid,id,name,route_status,oper_maint_level,surface_type,openforuseto,symbol_name',returnGeometry='true',maxAllowableOffset=.00005,resultOffset=offset,resultRecordCount=2000,orderByFields='objectid')
  with urllib.request.urlopen(URL+'?'+urllib.parse.urlencode(q),timeout=45) as r:data=json.load(r)
  if data.get('error'):raise ValueError(data['error'])
  batch=data.get('features',[])
  if not batch:break
  features+=batch;print(len(features),'forest road segments cached',flush=True)
  if len(batch)<2000:break
  offset+=len(batch)
 payload=dict(type='FeatureCollection',features=features,source_url=URL,bbox=[-124.8,46.3,-120.6,48.7])
 out=ROOT/'data/forest-roads-source.geojson.gz';tmp=out.with_suffix('.tmp');tmp.write_bytes(gzip.compress(json.dumps(payload,separators=(',',':')).encode()));tmp.replace(out)
if __name__=='__main__':main()
