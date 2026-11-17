"""Admission tests for temporary SD bootstrap; no USB or disk operations."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from ab_install import sd_bootstrap

class SDBootstrap(unittest.TestCase):
    def seed(self, root):
        (root/'AB.json').write_text(json.dumps({'sd_disk_id':'12345678'}))
        kit_hash=hashlib.sha256((root/'AB.json').read_bytes()).hexdigest()
        kernel=b'fixture temporary kernel'
        (root/'sd-bootstrap-kernel.bin').write_bytes(kernel)
        report=dict(kind='n810-sd-bootstrap',kit_sha256=kit_hash,sd_disk_id='12345678',kernel_sha256=hashlib.sha256(kernel).hexdigest())
        (root/'SD-BOOTSTRAP.json').write_text(json.dumps(report))
        (root/'SD-INSTALL.json').write_text(json.dumps(dict(kit_sha256=kit_hash,readback_verified=True)))
        return report

    def test_accepts_only_matching_verified_media_and_kernel(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.seed(root)
            self.assertEqual(sd_bootstrap(root),root/'sd-bootstrap-kernel.bin')
            (root/'sd-bootstrap-kernel.bin').write_bytes(b'wrong kernel')
            with self.assertRaises(ValueError):sd_bootstrap(root)

    def test_rejects_wrong_card_or_unverified_write(self):
        for case in ('card','receipt','kit'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);report=self.seed(root)
                if case=='card':
                    report['sd_disk_id']='87654321';(root/'SD-BOOTSTRAP.json').write_text(json.dumps(report))
                elif case=='receipt':
                    p=root/'SD-INSTALL.json';r=json.loads(p.read_text());r['readback_verified']=False;p.write_text(json.dumps(r))
                else:(root/'AB.json').write_text('{"sd_disk_id":"87654321"}')
                with self.assertRaises(ValueError):sd_bootstrap(root)

if __name__=='__main__':unittest.main()
