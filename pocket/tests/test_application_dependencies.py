"""Use bundled application code without another checkout or installed extras."""
from pathlib import Path
import sys
import tempfile
import time
import unittest
import wave
import importlib.util
import json
import hashlib
from reference_fixtures import maps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'shell'))


class Dependencies(unittest.TestCase):
    def test_packaged_map_worker_has_its_dependency_closure(self):
        project=Path(__file__).resolve().parents[1]
        sys.path.insert(0,str(project/'tools'))
        from package_nokia import runtime_files
        source={}
        for relative in ('apps/map-library-local-v3','vendor/map-library-resources'):
            for path in (project/'shell'/relative).rglob('*'):
                if path.is_file() and '__pycache__' not in path.parts:
                    source[str(path.relative_to(project/'shell'))]=path.read_bytes()
        with tempfile.TemporaryDirectory(prefix='pocket-map-closure-') as temporary:
            root=Path(temporary).resolve()
            for relative,raw in runtime_files(source).items():
                path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            app=root/'apps/map-library-local-v3'
            spec=importlib.util.spec_from_file_location('packaged_map_worker_test',app/'worker.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            inventory=json.loads((app/'dependency-inventory.json').read_text())
            # Generated geographic inputs accompany this temporary package only.
            # The source inventory pins code; downloads are supplied by the user.
            for fixture in maps().iterdir():
                relative='packet-console/maps/'+fixture.name
                target=root/'vendor/map-library-resources'/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                raw=fixture.read_bytes();target.write_bytes(raw)
                inventory['files'].append(dict(path=relative,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
            (app/'dependency-inventory.json').write_text(json.dumps(inventory))
            state=root/'private-state'
            worker=module.Worker('rainier',root/'vendor/map-library-resources/explorations/current-world',
                                 state/'staging',inventory,state_root=state)
            try:
                until=time.monotonic()+10
                while not worker.done and time.monotonic()<until:
                    worker.poll();time.sleep(.01)
                self.assertTrue(worker.done)
                self.assertEqual(worker.returncode,0,worker.error)
                self.assertTrue(worker.result['artifact']['compatible'])
            finally:worker.close()

    def test_workbench_replay_has_its_decoder_dependency_closure(self):
        from workbench_app import load_domain
        with tempfile.TemporaryDirectory(prefix='pocket-workbench-') as temporary:
            root = Path(temporary)
            path = root/'silence.wav'
            with wave.open(str(path),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000)
                wav.writeframes(b'\0\0'*800)
            model = load_domain()(root/'state')
            try:
                def finish():
                    until = time.monotonic()+5
                    while model.snapshot()['status']=='running' and time.monotonic()<until:
                        time.sleep(.005)
                    self.assertEqual(model.snapshot()['status'],'complete',model.snapshot()['error'])
                model.select(str(path));finish()
                model.run_cw(seconds=.1);finish()
                self.assertEqual(model.snapshot()['result']['kind'],'cw')
            finally: model.close()

    def test_document_apps_construct_from_bundled_domains(self):
        from document_apps import ReaderApp,LibraryApp
        with tempfile.TemporaryDirectory(prefix='pocket-docs-') as temporary:
            reader = ReaderApp(Path(temporary)/'reader')
            library = LibraryApp(())
            try:
                end = time.monotonic()+3
                while (reader.model.busy or library.model.busy) and time.monotonic()<end:
                    reader.poll();library.poll();time.sleep(.01)
                self.assertFalse(reader.model.busy)
                self.assertFalse(library.model.busy)
            finally: reader.close();library.close()

if __name__ == '__main__': unittest.main()
