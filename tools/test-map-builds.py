#!/usr/bin/env python3
"""Exercise map preparation offline with generated, explicitly fictional inputs."""
import argparse,base64,gzip,json,marshal,subprocess,sys,zlib
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,required=True);a=p.parse_args()
out=a.work.resolve();out.mkdir(parents=True,exist_ok=False)
v=ROOT/'pocket/shell/vendor/packet-console'
def run(script,*args):subprocess.run([sys.executable,str(script),*map(str,args)],check=True)
# A northbound coast leaves land to its west; the named road lies on that land.
source=out/'fixture.osm'
source.write_text('''<osm version="0.6" generator="n810-test">
<node id="1" lat="-1" lon="1"/><node id="2" lat="3" lon="1"/>
<node id="3" lat="0.5" lon="0.2"/><node id="4" lat="1.5" lon="0.2"/>
<node id="5" lat="1" lon="0.3"><tag k="place" v="town"/><tag k="name" v="Fixture Town"/></node>
<way id="1"><nd ref="1"/><nd ref="2"/><tag k="natural" v="coastline"/></way>
<way id="2"><nd ref="3"/><nd ref="4"/><tag k="highway" v="primary"/><tag k="name" v="Fixture Road"/></way>
</osm>''')
run(ROOT/'pocket/tools/maps.py','build','--source',source,'--bbox',0,0,2,2,'--output',out/'data','--maps',out/'maps')
pack=json.loads(gzip.decompress((out/'maps/puget-sound.json.gz').read_bytes()));r=pack['raster'];pixels=zlib.decompress(base64.b64decode(r['data']))
assert pixels[(r['height']//2)*r['width']+r['width']//4]==0
assert pixels[(r['height']//2)*r['width']+3*r['width']//4]==1
assert pack['labels'][0]['name']=='Fixture Town'
assert json.loads((out/'data/geography/index.json').read_text())['tiles']
assert json.loads((out/'data/hydrography/index.json').read_text())['complete']
size=64;heights=np.tile(np.linspace(0,150,size,dtype=np.float32),(size,1));Image.fromarray(heights).save(out/'heights.tif')
(out/'extent.json').write_text(json.dumps({'extent':{'xmin':0,'ymin':0,'xmax':2,'ymax':2}}))
run(v/'tools/build-terrain-next.py','--regional',out/'heights.tif','--regional-meta',out/'extent.json','--local',out/'heights.tif','--local-meta',out/'extent.json','--output',out/'terrain.n8t')
terrain=marshal.loads(zlib.decompress((out/'terrain.n8t').read_bytes()[4:]));assert len(terrain['layers'])==2
water={'bbox':[0,0,2,2],'raster':{'width':size,'height':size,'data':base64.b64encode(zlib.compress(bytes(size*size))).decode()}}
(out/'water.json.gz').write_bytes(gzip.compress(json.dumps(water).encode(),mtime=0))
run(v/'tools/build-elevation-bands.py',out/'heights.tif',out/'extent.json',out/'water.json.gz',out/'bands')
assert (out/'bands/grid.n8b').is_file()
# Historical walk conversion also receives generated fixture inputs.
(out/'maps/pnw-overview.json.gz').write_bytes((out/'maps/puget-sound.json.gz').read_bytes())
(out/'maps/lakewood-walk.roads.gz').write_bytes((out/'maps/puget-sound.roads.gz').read_bytes())
(out/'streams.json').write_text(json.dumps({'elements':[{'geometry':[{'lon':.1,'lat':.1},{'lon':.2,'lat':.2}]}]}))
run(v/'tools/build-walk-layers.py','--maps',out/'maps','--bands',out/'bands/grid.n8b','--output',out/'walk.n8w','--elevation',out/'heights.tif','--streams',out/'streams.json')
walk=marshal.loads(zlib.decompress((out/'walk.n8w').read_bytes()[4:]));assert len(walk['grids'])==3 and len(walk['roads'])==2 and walk['streams']
print('PASS: synthetic OSM import, geography/water tiles, terminal coast raster, terrain pyramid elevation bands and walk layers; no downloads.')
