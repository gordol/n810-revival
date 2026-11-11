import sys,unittest,tempfile,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from symbian_catalog import applications,resolve

class CatalogTests(unittest.TestCase):
    def test_apparc_names_and_paths_are_separate_from_pocket_registry(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home)/'.local/share/symbian-private/runtime';folder=root/'data/drives/c/sys/bin';folder.mkdir(parents=True)
            (folder/'example.exe').write_bytes(struct.pack('<III',0x1000007a,0x100039ce,0x20001234))
            (root/'apps.tsv').write_text('20001234\tC:\\system\\programs\\example.exe\tExample game\n')
            rows=applications(home);self.assertEqual(len(rows),1)
            self.assertEqual(rows[0],{'id':'20001234','title':'Example game','path':'C:\\sys\\bin\\example.exe'})
            self.assertEqual(resolve('20001234',home),rows[0]);self.assertIsNone(resolve('../shell',home))
            (folder/'example.exe').unlink();self.assertEqual(applications(home),[])
    def test_bad_uid_path_and_external_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home)/'.local/share/symbian-private/runtime';folder=root/'data/drives/c/sys/bin';folder.mkdir(parents=True)
            outside=Path(home)/'outside.exe';outside.write_bytes(struct.pack('<III',0,0,0x20001234))
            (folder/'outside.exe').symlink_to(outside)
            (folder/'wrong.exe').write_bytes(struct.pack('<III',0,0,99))
            (root/'apps.tsv').write_text('20001234\tC:\\sys\\bin\\outside.exe\tOutside\n20001234\tC:\\sys\\bin\\wrong.exe\tWrong\n20001234\tC:\\sys\\bin\\..\\wrong.exe\tTraverse\n')
            self.assertEqual(applications(home),[])
    def test_duplicate_ids_and_titles_remain_bounded(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home)/'.local/share/symbian-private/runtime';folder=root/'data/drives/c/sys/bin';folder.mkdir(parents=True)
            (folder/'a.exe').write_bytes(struct.pack('<III',0,0,1))
            line='00000001\tC:\\sys\\bin\\a.exe\t'+'A'*200+'\n';(root/'apps.tsv').write_text(line*2)
            rows=applications(home);self.assertEqual(len(rows),1);self.assertEqual(len(rows[0]['title']),80)

if __name__=='__main__':unittest.main()
