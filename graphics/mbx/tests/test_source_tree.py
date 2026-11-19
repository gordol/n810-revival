import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('source_tree',ROOT/'source_tree.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class SourceTreeTests(unittest.TestCase):
    def test_portable_build_uses_maintained_driver_and_matching_abi(self):
        with tempfile.TemporaryDirectory() as folder:
            output=module.assemble(ROOT,Path(folder)/'driver')
            overlay=ROOT.parents[1]/'pocket/graphics/driver/mbx'
            for component in ('mesa','kernel','common'):
                for source in (overlay/component).iterdir():
                    if source.suffix in ('.c','.h'):
                        self.assertEqual((output/component/source.name).read_bytes(),source.read_bytes(),str(source))
            self.assertTrue((output/'mesa/prepare_mesa.py').is_file())
            self.assertTrue((output/'build-inputs/Module.symvers').is_file())

    def test_component_build_uses_same_effective_sources_as_full_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            full = module.assemble(ROOT, Path(folder) / 'full')
            for target in ('kernel', 'mesa'):
                with self.subTest(target=target):
                    output = module.assemble(ROOT, Path(folder) / target, target=target)
                    self.assertEqual({p.name for p in output.iterdir()}, {'common', target})
                    for component in ('common', target):
                        def contents(tree):
                            root = tree / component
                            return {p.relative_to(root): p.read_bytes()
                                    for p in root.rglob('*') if p.is_file()}
                        self.assertEqual(contents(output), contents(full))
