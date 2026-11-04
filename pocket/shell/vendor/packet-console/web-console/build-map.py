"""Export existing offline geography for native browser canvas; no downloads."""
import gzip
import importlib.util
import json
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parent.parent
out=Path(__file__).resolve().parent/'assets';out.mkdir(exist_ok=True)
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,root/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
geometry=module('web_geometry','n810-walk-map.py');palette=module('web_palette','n810-map-rgb.py')
atlas=geometry.Atlas(str(root/'maps'));rasters=[]
for i,grid in enumerate(atlas.grids):
    image=Image.new('RGB',(grid['width'],grid['height']))
    image.putdata([palette.REGIONAL[min(7,value)] for value in grid['pixels']]);image.save(out/('terrain-%d.png'%i))
    rasters.append(dict(file='terrain-%d.png'%i,bbox=grid['bbox']))
roads=[]
for role,layer in list(enumerate(atlas.roads))+([(2,atlas.streams)] if atlas.streams else []):
    roads.append(dict(role=role,coords=list(layer['coords'])))
metadata=module('web_metadata','n810-map.py').Atlas(str(root/'maps'))
places=module('web_model','n810-map-next.py').canonical_places(metadata.packs)
data=dict(rasters=rasters,roads=roads,places=places,attribution='OpenStreetMap contributors · USGS 3DEP · NOAA ETOPO1',source='Existing shared N810 geography packs; regional elevation classes')
(out/'map.json.gz').write_bytes(gzip.compress(json.dumps(data,separators=(',',':')).encode()))
print('Offline browser geography built:',len(places),'places;',sum(len(r['coords'])//4 for r in roads),'segments')
