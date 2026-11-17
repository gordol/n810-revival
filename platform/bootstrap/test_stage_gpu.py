import hashlib
import json
import tempfile
import shutil
import unittest
from pathlib import Path

from stage_gpu import inputs


def sha(data):
    return hashlib.sha256(data).hexdigest()


class GpuInputs(unittest.TestCase):
    def test_requires_one_kernel_symbol_set_and_scene_mesa(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            runtime, module, mesa, kernel = (base / name for name in ('runtime', 'module', 'mesa', 'kernel'))
            for path in (runtime, module, mesa, kernel):
                path.mkdir()
            (kernel / 'Module.symvers').write_bytes(b'kernel symbols')
            (kernel / 'BUILD.json').write_text(json.dumps({'release': '5.15.224-test'}))
            (module / 'n810_mbx_gpu_probe.ko').write_bytes(b'\x7fELF\x01' + b'\0' * 13 + b'\x28\0' + b'\0' * 16)
            build = {'target': 'module', 'kernel_release': '5.15.224-test', 'crc_checks': 87,
                     'kernel_symvers_sha256': sha(b'kernel symbols'),
                     'source_sha256': {'build-inputs/Module.symvers': sha(b'historical reference symbols')}}
            (module / 'BUILD.json').write_text(json.dumps(build))
            (mesa / 'libOSMesa.so.8').write_bytes(b'mesa')
            (mesa / 'BUILD.json').write_text(json.dumps({'target': 'mesa'}))
            graphics = runtime / 'build/graphics'
            graphics.mkdir(parents=True)
            frontend = {'scene_gl': True, 'gpu_renderer': True, 'mesa_sha256': sha(b'mesa')}
            (graphics / 'BUILD.json').write_text(json.dumps(frontend))
            (graphics / 'libOSMesa.so.8').write_bytes(b'mesa')
            (graphics / 'window.so').write_bytes(b'window')
            (graphics / '_cellengine.abi3.so').write_bytes(b'native')
            (graphics / 'renderer.so').write_bytes(b'renderer')
            names = ('BUILD.json', 'libOSMesa.so.8', 'window.so', '_cellengine.abi3.so', 'renderer.so')
            (runtime / 'runtime-profile.json').write_text(json.dumps({'profile': 'release',
                'source_commit': 'fixture', 'files': {'build/graphics/' + name: sha((graphics / name).read_bytes())
                                                     for name in names}}))
            self.assertEqual(inputs(runtime, module, mesa, kernel)[1], '5.15.224-test')
            from stage_gpu import stage
            root=base/'root';staged=root/'usr/local/share/pocket'
            shutil.copytree(runtime,staged);(staged/'INSTALL.json').write_text('{}')
            unit=root/'etc/systemd/system/pocket-desktop.service';unit.parent.mkdir(parents=True)
            unit.write_text('ExecStart=/usr/bin/python3 /usr/local/lib/pocket/bootstrap_desktop.py --user nokia\nRestart=on-failure\n')
            stage(root,runtime,module,mesa,kernel)
            selected=(root/'usr/local/lib/n810-graphics/current').resolve()
            self.assertEqual((selected/'room-pixels.so').readlink(),Path('renderer.so'))
            manifest=json.loads((selected/'MANIFEST.json').read_text())
            self.assertEqual(manifest['files']['room-pixels.so'],sha((selected/'room-pixels.so').read_bytes()))
            build['kernel_symvers_sha256'] = sha(b'other symbols')
            (module / 'BUILD.json').write_text(json.dumps(build))
            with self.assertRaisesRegex(ValueError, 'different kernel symbols'):
                inputs(runtime, module, mesa, kernel)


if __name__ == '__main__':unittest.main()
