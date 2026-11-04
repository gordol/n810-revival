"""Projection/topology tests use synthetic regions, with no special place rules."""
import sys,json,gzip,hashlib,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import map_hydrography as hydro
class HydrographyTests(unittest.TestCase):
 def test_tiny_water_body_does_not_expand_to_a_whole_cell(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);path=root/'index.json'
   pond=[[.245,.245],[.255,.245],[.255,.255],[.245,.255],[.245,.245]]
   raw=gzip.compress(json.dumps([dict(rings=[pond])]).encode());(root/'tile.gz').write_bytes(raw)
   path.write_text(json.dumps(dict(complete=True,defines_land=True,coverage=[0,0,1,1],step=1,tiles={'0,0':dict(file='tile.gz',sha256=hashlib.sha256(raw).hexdigest())})))
   with patch.object(hydro,'PATH',path):
    hydro.index.cache_clear();hydro.tile.cache_clear()
    wide=hydro.mask(SimpleNamespace(center=(.25,.25),span=111.32,width=5,height=3,cell_aspect=2))
    close=hydro.mask(SimpleNamespace(center=(.25,.25),span=.1,width=5,height=3,cell_aspect=2))
    self.assertEqual(int(wide[2,2]),1)
    self.assertEqual(int(close[2,2]),0)
   hydro.index.cache_clear();hydro.tile.cache_clear()
 def test_water_islands_overlap_and_unknown_coverage(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);path=root/'index.json'
   shell=[[.2,.2],[.8,.2],[.8,.8],[.2,.8],[.2,.2]]
   hole=[[.4,.4],[.6,.4],[.6,.6],[.4,.6],[.4,.4]]
   raw=gzip.compress(json.dumps([dict(rings=[shell,hole])]).encode());(root/'tile.gz').write_bytes(raw)
   data=dict(complete=True,defines_land=True,coverage=[0,0,1,1],step=1,tiles={'0,0':dict(file='tile.gz',sha256=hashlib.sha256(raw).hexdigest())})
   path.write_text(json.dumps(data))
   with patch.object(hydro,'PATH',path):
    hydro.index.cache_clear();hydro.tile.cache_clear()
    def sample(lat,lon):
     view=SimpleNamespace(center=(lat,lon),span=.01,width=3,height=2,cell_aspect=2)
     result=hydro.mask(view);return None if result is None else int(result[1,1])
    self.assertEqual(sample(.25,.25),0);self.assertEqual(sample(.5,.5),1)
    self.assertEqual(sample(.9,.9),1);self.assertIsNone(sample(-.1,.5))
    pond=[[.45,.45],[.55,.45],[.55,.55],[.45,.55],[.45,.45]]
    raw=gzip.compress(json.dumps([dict(rings=[pond]),dict(rings=[shell,hole])]).encode())
    (root/'tile.gz').write_bytes(raw);data['tiles']['0,0']['sha256']=hashlib.sha256(raw).hexdigest()
    path.write_text(json.dumps(data));hydro.index.cache_clear();hydro.tile.cache_clear()
    self.assertEqual(sample(.5,.5),0);self.assertEqual(sample(.42,.42),1)
    data['defines_land']=False;path.write_text(json.dumps(data));hydro.index.cache_clear()
    self.assertEqual(sample(.25,.25),0);self.assertEqual(sample(.9,.9),-1)
    # A bad tile cannot silently classify missing water as land.
    (root/'tile.gz').write_bytes(b'bad');hydro.tile.cache_clear()
    with self.assertRaises(ValueError):sample(.25,.25)
   hydro.index.cache_clear();hydro.tile.cache_clear()
