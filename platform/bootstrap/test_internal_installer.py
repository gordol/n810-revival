import unittest
import gzip,hashlib,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from internal_installer import internal_target,Installer

class InternalTarget(unittest.TestCase):
    def row(self,name='mmcblk0',kind='MMC',sectors=3900000,cid='a'*32):
        return f'{name} {kind} {sectors} {cid}'
    def test_internal_mmc_selected_independently_of_sd_order(self):
        result=internal_target(self.row('mmcblk0','SD')+'\n'+self.row('mmcblk1'),512*1024*1024)
        self.assertEqual(result['device'],'/dev/mmcblk1')
    def test_rejects_ambiguous_missing_oversized_and_malformed_targets(self):
        for rows,size in ((self.row(kind='SD'),1),(self.row()+'\n'+self.row('mmcblk1'),1),
                          (self.row(),4*1024**3),(self.row(sectors=100),1),
                          (self.row(name='mmcblk0;reboot'),1),(self.row(cid='bad'),1)):
            with self.subTest(rows=rows),self.assertRaises(ValueError):internal_target(rows,size)

class CompressedKit(unittest.TestCase):
    def kit(self,folder):
        root=Path(folder);raw=b'fictional root fixture'*1024
        archive=root/'root.ext4.gz';archive.write_bytes(gzip.compress(raw))
        kernel=root/'kernel.bin';kernel.write_bytes(b'fictional kernel fixture')
        manifest=dict(kind='n810-internal',root_bytes=len(raw),root_sha256=hashlib.sha256(raw).hexdigest(),
            compressed_root_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            kernel_sha256=hashlib.sha256(kernel.read_bytes()).hexdigest())
        (root/'INTERNAL.json').write_text(json.dumps(manifest))
        installer=Installer(root,'192.168.11.1')
        installer.remote=Mock(return_value=SimpleNamespace(stdout='mmcblk0 MMC 3900000 '+'a'*32+'\n'))
        return installer,manifest
    def test_compressed_only_kit_is_verified_before_target_inspection(self):
        with tempfile.TemporaryDirectory() as folder:
            installer,manifest=self.kit(folder)
            _,target=installer.inspect()
            self.assertEqual(target['device'],'/dev/mmcblk0')
            self.assertEqual(installer.remote.call_count,1)
    def test_corruption_and_expansion_size_fail_without_contacting_tablet(self):
        for mode in ('corrupt','expanded'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                installer,manifest=self.kit(folder)
                if mode=='corrupt':(Path(folder)/'root.ext4.gz').write_bytes(b'changed')
                else:
                    manifest['root_bytes']-=1
                    (Path(folder)/'INTERNAL.json').write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):installer.inspect()
                installer.remote.assert_not_called()

if __name__=='__main__':unittest.main()
