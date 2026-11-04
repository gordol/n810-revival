import json,sys,tempfile,unittest,zlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from prepare_elevation_tiles import prepare
class PreparationTests(unittest.TestCase):
 def test_invalid_coastal_boundary_is_unknown_not_a_false_peak(self):
  import numpy as np
  from PIL import Image
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);a=np.full((16,16),100,dtype=np.float32);a[8,8]=1e30;a[8,9]=4000
   Image.fromarray(a).save(root/'raw.tif')
   envelope=dict(request_url='test',response=dict(width=16,height=16,extent=dict(xmin=-123,ymin=47,xmax=-122,ymax=48,spatialReference=dict(wkid=4326))))
   (root/'export.json').write_text(json.dumps(envelope))
   prepare(root/'raw.tif',root/'export.json',root/'tiles')
   values=np.frombuffer(zlib.decompress((root/'tiles/0-0.i16.zlib').read_bytes()),dtype='<i2').reshape(16,16)
   self.assertEqual(values[7,9],-32768);self.assertEqual(values[0,0],100)
   metadata=json.loads((root/'tiles/index.json').read_text())
   self.assertEqual(metadata['range_m'],[100,100]);self.assertEqual(metadata['maximum_bounds']['values'],[32767])
 def test_sparse_tiff_zero_offset_does_not_read_header_as_elevation(self):
  import struct,numpy as np
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);tags={256:(4,1,256),257:(4,1,128),258:(3,1,32),259:(3,1,1),262:(3,1,1),277:(3,1,1),284:(3,1,1),322:(4,1,128),323:(4,1,128),324:(4,2,0),325:(4,2,0),339:(3,1,3)}
   offset=8+2+len(tags)*12+4;tags[324]=(4,2,offset);tags[325]=(4,2,offset+8)
   raw=b'II'+struct.pack('<HI',42,8)+struct.pack('<H',len(tags))
   raw+=b''.join(struct.pack('<HHII',tag,*value) for tag,value in sorted(tags.items()))+struct.pack('<I',0)
   raw+=struct.pack('<IIII',offset+16,0,128*128*4,0)+np.full((128,128),100,dtype='<f4').tobytes()
   (root/'raw.tif').write_bytes(raw)
   (root/'export.json').write_text(json.dumps(dict(request_url='test',response=dict(width=256,height=128,extent=dict(xmin=-123,ymin=47,xmax=-122,ymax=48,spatialReference=dict(wkid=4326))))))
   report=prepare(root/'raw.tif',root/'export.json',root/'tiles')
   self.assertEqual(report['range_m'],[100,100]);self.assertEqual(report['valid'],126*128)
   values=np.frombuffer(zlib.decompress((root/'tiles/0-0.i16.zlib').read_bytes()),dtype='<i2').reshape(128,256)
   self.assertTrue((values[:,128:]==-32768).all())
