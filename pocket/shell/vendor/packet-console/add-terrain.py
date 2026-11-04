"""Laptop-only: bake coarse USGS elevation classes into an offline map pack."""
import argparse,base64,gzip,json,pathlib,zlib,math
from PIL import Image
p=argparse.ArgumentParser(description=__doc__);p.add_argument('pack');p.add_argument('elevation');p.add_argument('--source',help='OSM extract for named peaks');a=p.parse_args()
pack=json.load(gzip.open(a.pack,'rt'));r=pack['raster'];raw=zlib.decompress(base64.b64decode(r['data']))
elevation=Image.open(a.elevation)
if elevation.mode!='F':raise ValueError('Expected raw float elevation in meters, got '+elevation.mode)
elevation=elevation.resize((r['width'],r['height']),Image.Resampling.BILINEAR)
result=bytearray();maximum=0
for pixel,height in zip(raw,elevation.getdata()):
 if (pixel&3) or not math.isfinite(height) or height < -500 or height>5000:band=0
 else:
  maximum=max(maximum,height)
  band=sum(height>=threshold for threshold in (200,500,1000,1800,2800))
 result.append((pixel&3)|(band<<2))
r['data']=base64.b64encode(zlib.compress(result,9)).decode()
pack['terrain']=dict(source='USGS 3DEP',source_url='https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer',bands_m=[200,500,1000,1800,2800],meaning='Elevation bands; not vegetation or snow coverage')
pack['layers']=['land','water','elevation','places']
pack['labels']=[p for p in pack['labels'] if p['name']!='Mt Rainier']
pack['labels'].append(dict(name='Mt Rainier',lat=46.853,lon=-121.76,kind='peak',population=0,source='USGS https://www.usgs.gov/volcanoes/mount-rainier/'))
if a.source:
 for node in json.loads(pathlib.Path(a.source).read_text())['elements']:
  if node['type']=='node' and node.get('tags',{}).get('natural')=='peak':
   pack['labels'].append(dict(name=node['tags'].get('name','Peak'),lat=node['lat'],lon=node['lon'],kind='peak',population=0))
with gzip.open(a.pack,'wt') as f:json.dump(pack,f,separators=(',',':'))
pathlib.Path(a.pack[:-8]+'.meta.json').write_text(json.dumps({k:v for k,v in pack.items() if k!='lines'},separators=(',',':')))
print('Terrain max: %.0fm; pack: %d bytes'%(maximum,pathlib.Path(a.pack).stat().st_size))
