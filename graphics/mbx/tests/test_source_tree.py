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
