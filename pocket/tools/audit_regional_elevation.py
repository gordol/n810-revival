"""Verify every published regional tile against its index and write a coverage report."""
from pathlib import Path
import hashlib,json,zlib
root=Path(__file__).resolve().parents[1]/'data/elevation-fine';report=[]
for path in sorted(root.glob('*-guarded/index.json')):
 m=json.loads(path.read_text());assert m.get('sparse_tiff_safe') and m.get('maximum_allowed_m')==5000,path
 total=0
 for item in m['tiles'].values():
  raw=(path.parent/item['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==item['sha256'],path
  assert len(zlib.decompress(raw))==item['width']*item['height']*2,path
  total+=len(raw)
 report.append(dict(pack=path.parent.name,extent=m['extent'],valid=m['valid_samples'],missing=m['missing_samples'],range_m=m['range_m'],bytes=total,index_bytes=path.stat().st_size,spacing_degrees=[m['longitude_step'],m['latitude_step']]))
summary=dict(packs=len(report),expected_packs=72,valid_samples=sum(p['valid'] for p in report),missing_samples=sum(p['missing'] for p in report),tile_bytes=sum(p['bytes'] for p in report),index_bytes=sum(p['index_bytes'] for p in report),packs_detail=report)
out=Path(__file__).resolve().parents[2]/'outputs/regional-fine-dem-20261102/audit.json';out.write_text(json.dumps(summary,indent=2))
print(json.dumps({k:v for k,v in summary.items() if k!='packs_detail'}))
if len(report)!=72:raise SystemExit('Incomplete regional coverage')
