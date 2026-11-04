import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from data_paths import data_root,content_identity
import build_identity
class VersionTests(unittest.TestCase):
    def test_product_version_is_visible_alongside_exact_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'build-info.json'
            path.write_text(json.dumps(dict(schema_version=1,product_version='0.1.0',release_id='abc123',framework_commit='abc123')))
            value=build_identity.load(path)
            self.assertEqual(value['product_version'],'0.1.0')
            self.assertIn(('Product version','0.1.0'),build_identity.details(value))
            self.assertEqual(value['release_id'],'abc123')
    def test_explicit_reference_dataset_does_not_move_user_state(self):
        with patch.dict(os.environ,{'POCKET_DATA_ROOT':'/tmp/reference-check'}):
            self.assertEqual(data_root(),Path('/tmp/reference-check'))
    def test_old_manifest_reports_unknown_product_version(self):
        self.assertEqual(build_identity.load('/missing/build-info.json')['product_version'],'UNKNOWN')

class CacheIdentityTests(unittest.TestCase):
    def test_copying_unchanged_data_keeps_persisted_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);first=root/'old'/'pack';second=root/'new'/'pack'
            first.mkdir(parents=True);second.mkdir(parents=True)
            a=first/'index.json';b=second/'index.json'
            a.write_text('{"tiles": {"0,0": "same digest"}}')
            b.write_bytes(a.read_bytes());os.utime(b,ns=(1000000000,1000000000))
            self.assertEqual(content_identity(a),content_identity(b))
            b.write_text('{"tiles": {"0,0": "new digest"}}')
            self.assertNotEqual(content_identity(a),content_identity(b))
