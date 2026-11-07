# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fresh offline installs, failed updates and explicit data-package boundaries."""
import importlib.util
import json
from pathlib import Path
import sys,tempfile,threading,tarfile,unittest,zipfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from fcc_download import update,download,sha256
from fcc_database import lookup


def fixture(path):
    hd=['']*59
    for key,value in {0:'HD',1:'1',4:'N0CALL',5:'A',6:'HA',7:'01/01/2020',8:'01/01/2030',43:'11/01/2026'}.items():hd[key]=value
    en=['']*30
    for key,value in {0:'EN',1:'1',5:'L',7:'Example radio club',15:'123 Example St',16:'Example City',17:'WA',18:'98000',19:'42'}.items():en[key]=value
    with zipfile.ZipFile(path,'w') as archive:
        for name,row in (('HD.dat',hd),('EN.dat',en),('AM.dat',['AM','1','','','N0CALL','E'])):
            archive.writestr(name,'|'.join(row)+'\n')


class FCCInstallTests(unittest.TestCase):
    def test_unchanged_strong_etag_200_response_does_not_redownload_body(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'l_amat.zip';archive.write_bytes(b'verified cache')
            previous=dict(etag='"same"',archive_sha256=sha256(archive))
            response=SimpleNamespace(headers={'Content-Length':str(archive.stat().st_size),'ETag':'"same"'},close=lambda:None,
                                     read=lambda *args:(_ for _ in ()).throw(AssertionError('Read unchanged download body')))
            result,metadata,changed=download(root,previous,opener=SimpleNamespace(open=lambda *args,**kw:response))
            self.assertEqual(result,archive);self.assertFalse(changed)
            self.assertEqual(metadata,previous)

    def test_local_archive_installs_without_network_and_failed_update_keeps_database(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'official-fixture.zip';fixture(archive)
            database=root/'data/uls.sqlite';messages=[]
            result=update(database,root/'cache',messages.append,minimum_stations=1,archive=archive)
            self.assertTrue(result['updated']);self.assertEqual(lookup(database,'N0CALL')['street_address'],'123 Example St')
            self.assertIn('Offline FCC database ready',messages)
            before=database.read_bytes();archive.write_bytes(b'broken ZIP')
            with self.assertRaises(zipfile.BadZipFile):update(database,root/'cache',minimum_stations=1,archive=archive)
            self.assertEqual(database.read_bytes(),before)

    def test_cancel_before_download_does_not_create_database(self):
        from concurrent.futures import CancelledError
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cancelled=threading.Event();cancelled.set()
            with patch('fcc_download.download',side_effect=AssertionError('Unexpected network')):
                with self.assertRaises(CancelledError):update(root/'uls.sqlite',root/'cache',cancelled=cancelled)
            self.assertFalse((root/'uls.sqlite').exists())

    def test_default_reference_package_excludes_even_an_existing_fcc_database(self):
        path=Path(__file__).resolve().parents[1]/'tools/package_reference_data.py'
        spec=importlib.util.spec_from_file_location('reference_data_under_test',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'VERSION').write_text('0.1.0')
            for name in ('geography/index.json','hydrography/index.json','repeaters/repeaters.json','uls.sqlite'):
                file=root/'data'/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text('synthetic fixture')
            with patch.object(module,'ROOT',root):
                output=root/'references.tar.gz';module.package(output)
                with tarfile.open(output) as archive:self.assertNotIn('data/uls.sqlite',archive.getnames())
                output=root/'local-transfer.tar.gz';module.package(output,include_fcc=True)
                with tarfile.open(output) as archive:self.assertIn('data/uls.sqlite',archive.getnames())


if __name__=='__main__':unittest.main()
