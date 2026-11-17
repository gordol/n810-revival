from pathlib import Path
import hashlib,json,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from stage_runtime import stage
class DoomPackagingTests(unittest.TestCase):
    def fixture(self,root):
        app=root/'doom';(app/'build').mkdir(parents=True)
        data=app/'vendor/freedoom-0.13.0';data.mkdir(parents=True)
        records={}
        for name,key,raw in [('build/doom-engine','engine',b'fixture engine'),('build/bridge.so','bridge',b'fixture bridge'),('vendor/freedoom-0.13.0/freedoom1.wad','wad',b'fictional game data')]:
            (app/name).write_bytes(raw);records[key]=hashlib.sha256(raw).hexdigest()
        for name in ('COPYING.txt','CREDITS.txt','CREDITS-MUSIC.txt'):(data/name).write_text('fixture notice')
        (app/'build/BUILD.json').write_text(json.dumps(records));return app
    def test_binaries_data_notices_and_execution_mode_are_packaged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);app=self.fixture(root);dest=root/'runtime'
            stage(dest,doom_runtime=app)
            record=json.loads((dest/'runtime-profile.json').read_text())
            engine='shell/apps/doom-app/build/doom-engine'
            self.assertIn(engine,record['executables']);self.assertTrue((dest/engine).stat().st_mode&0o111)
            self.assertIn('shell/apps/doom-app/vendor/freedoom-0.13.0/COPYING.txt',record['files'])
            self.assertIn('shell/apps/doom-app/vendor/freedoom-0.13.0/freedoom1.wad',record['files'])
    def test_modified_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);app=self.fixture(root);(app/'build/bridge.so').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):stage(root/'runtime',doom_runtime=app)
if __name__=='__main__':unittest.main()
