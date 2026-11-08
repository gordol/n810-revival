"""Verify release artifacts, not merely the developer source's default flags."""
import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from runtime_profile import profile_files, release_source
from stage_runtime import stage


class RuntimeProfileTests(unittest.TestCase):
    def test_release_erases_features_and_preserves_validation(self):
        raw = b'DEVELOPMENT=True\nif DEVELOPMENT:\n import debug_only\n def diagnostic(): pass\nassert required, "required validation"\nvalue=debug() if DEVELOPMENT and enabled else work()\n'
        output = release_source(raw, 'fixture.py')
        self.assertNotIn(b'import debug_only', output)
        self.assertNotIn(b'def diagnostic', output)
        self.assertNotIn(b'debug()', output)
        self.assertIn(b'assert required', output)
        self.assertIn(b'work()', output)
        self.assertEqual(profile_files({'fixture.py':raw}, 'dev')['fixture.py'], raw)

    def test_release_omits_implementations_and_debug_controls(self):
        files = {n:(ROOT/'shell'/n).read_bytes() for n in ('desktop.py','draw_metrics.py','pointer_trace.py','flurry_trial.py')}
        release = profile_files(files)
        self.assertEqual(set(release), {'desktop.py'})
        tree = ast.parse(release['desktop.py'])
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertFalse(imports & {'draw_metrics','pointer_trace','flurry_trial'})
        literals = {n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
        self.assertFalse(literals & {'--pointer-trace','--metrics','--flurry-trial','Render Debug'})
        gui = ast.parse(release_source((ROOT/'graphics/full.py').read_bytes(), 'full.py'))
        self.assertNotIn('record_frame', {n.name for n in ast.walk(gui) if isinstance(n,ast.FunctionDef)})
        self.assertNotIn('history', {n.value for n in ast.walk(gui) if isinstance(n,ast.Constant) and isinstance(n.value,str)})

    def test_generated_release_starts_without_development_modules(self):
        frontend = ROOT/'build/graphics/frontend.json'
        if not frontend.exists():self.skipTest('run make graphics-native first')
        with tempfile.TemporaryDirectory(prefix='pocket-release-',dir='/tmp') as d:
            target=Path(d)/'runtime'
            files=stage(target,frontend=frontend)
            self.assertNotIn('graphics/launch.py',files)
            self.assertNotIn('graphics/desktop.py',files)
            help_result=subprocess.run([sys.executable,'-I',str(target/'graphics/run.py'),'--help'],capture_output=True,timeout=15,cwd=d)
            self.assertEqual(help_result.returncode,0,help_result.stderr.decode())
            self.assertNotIn(b'--report',help_result.stdout)
            self.assertNotIn(b'--actions',help_result.stdout)
            self.assertFalse(any('tests' in Path(n).parts or Path(n).name.startswith(('test_','test-')) for n in files))
            self.assertFalse(any(Path(n).name in ('draw_metrics.py','pointer_trace.py','flurry_trial.py','build.py') for n in files if not n.startswith('shell/vendor/')))
            # Real model/platform initialization and one complete frame; no
            # display, services, device input, network or developer source path.
            code='''
import json,sys,os
from pathlib import Path
r=Path(sys.argv[1]);sys.path.insert(0,str(r/'graphics'))
from full import Platform
assert not hasattr(Platform,'record_frame')
c=json.loads((r/'build/graphics/frontend.json').read_text());c={k:str(r/v) for k,v in c.items()}
d=str(r.parent/'state');Path(d).mkdir()
os.environ.update(HOME=d,XDG_STATE_HOME=d+'/state',XDG_CONFIG_HOME=d+'/config',XDG_CACHE_HOME=d+'/cache')
p=Platform(c['font'],c['gpu_library'],None,cell_renderer='cpu',frames=1)
p.run(['--shell','--session',d+'/desktop.json','--app-state',d,'--station-db',d+'/directory.sqlite3','--native',c['native_library'],'--no-local-services','--no-save','--no-animation'])
assert not any(n in sys.modules for n in ('draw_metrics','pointer_trace','flurry_trial'))
assert not any(w.name=='Render Debug' for w in p.host.windows)
assert p.frames==1
assert p.host._native is not None, p.host.native_error
'''
            result=subprocess.run([sys.executable,'-I','-c',code,str(target)],capture_output=True,timeout=60,cwd=d)
            self.assertEqual(result.returncode,0,result.stderr.decode())


if __name__ == '__main__':unittest.main()
