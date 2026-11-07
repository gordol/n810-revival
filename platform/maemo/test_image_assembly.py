"""Exercise partition preservation using a scaled, synthetic file image."""
import contextlib,importlib.util,io,struct,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
path=Path(__file__).resolve().parents[1]/'scripts/assemble-clean-n810-emmc.py'
spec=importlib.util.spec_from_file_location('assembler',path);assembler=importlib.util.module_from_spec(spec);spec.loader.exec_module(assembler)
class ImageTests(unittest.TestCase):
    def test_layout_preservation_and_overwrite_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);p1,p2,out=d/'p1',d/'p2',d/'image'
            p1.write_bytes(b'A'*1024);p2.write_bytes(b'B'*1536)
            args=['assemble','--partition1',str(p1),'--partition2',str(p2),'--output',str(out)]
            with patch.multiple(assembler,P1_START=1,P1_SECTORS=2,P2_START=3,P2_SECTORS=3,IMAGE_SECTORS=6),patch.object(sys,'argv',args),contextlib.redirect_stdout(io.StringIO()):
                assembler.main();data=out.read_bytes()
                self.assertEqual(data[512:1536],p1.read_bytes());self.assertEqual(data[1536:],p2.read_bytes())
                self.assertEqual(data[510:512],b'\x55\xaa')
                self.assertEqual(struct.unpack_from('<II',data,454),(1,2))
                with contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):assembler.main()
                self.assertEqual(out.read_bytes(),data)
    def test_device_output_rejected_before_input_access(self):
        with patch.object(sys,'argv',['assemble','--partition1','absent','--partition2','absent','--output','/dev/never-open']),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):assembler.main()
if __name__=='__main__':unittest.main()
