"""Terrain consumers share the selected offline data root."""
import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import model_scene,terrain_elevation,scenery_geo

class CommonDataRoot(unittest.TestCase):
    def tearDown(self):
        model_scene.tahoma.cache_clear()
        terrain_elevation.grid.cache_clear()
        terrain_elevation.regional_grid.cache_clear()
    def test_model_profile_and_reference_use_selected_data(self):
        import json,zlib,struct,hashlib
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);size=257
            values=[2500]*(size*size);values[(size//2)*size+size//2]=3500
            raw=zlib.compress(struct.pack('<'+'h'*len(values),*values))
            metadata=dict(nx=size,nz=size,units='meters',latitude_first=46.,longitude_first=-123.,latitude_step=.005,longitude_step=.005,sha256=hashlib.sha256(raw).hexdigest())
            (root/'tahoma-3dep.json').write_text(json.dumps(metadata))
            (root/'tahoma-3dep.i16.zlib').write_bytes(raw)
            with patch.dict(os.environ,{'POCKET_DATA_ROOT':folder}):
                model=model_scene.tahoma(stride=8)
                self.assertEqual(max(model.terrain.values),3500)
                self.assertEqual(max(terrain_elevation.grid()[1]),3500)
                self.assertIn('latitude',scenery_geo.reference(model.camera))
    def test_missing_selected_data_does_not_use_another_directory(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'POCKET_DATA_ROOT':folder}):
            for load in (model_scene.tahoma,terrain_elevation.grid):
                with self.subTest(loader=load.__name__),self.assertRaises(FileNotFoundError) as error:load()
                self.assertTrue(str(error.exception.filename).startswith(folder))

if __name__=='__main__':unittest.main()
