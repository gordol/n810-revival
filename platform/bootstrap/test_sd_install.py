"""Exercise SD media guards and readback with ordinary fixture files, no devices."""
import gzip,hashlib,json,os,plistlib,struct,io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import write_sd_card as card
from storage_target import validate_size,require_target

class SDInstallTests(unittest.TestCase):
    def media(self):
        return dict(DeviceNode='/dev/disk99',WholeDisk=True,VirtualOrPhysical='Physical',
            Writable=True,DeviceBlockSize=512,RemovableMedia=True,TotalSize=4*1024*1024,
            DeviceTreePath='reader/slot',MediaName='Fixture SD')
    def kit(self,root):
        data=b'fixture root'+bytes(1024*1024-len(b'fixture root'));image=root/'root.ext4.gz'
        with gzip.open(image,'wb') as f:f.write(data)
        return dict(storage_target='sd',root_bytes=len(data),root_sha256=hashlib.sha256(data).hexdigest(),disk_id='12345678',kernel_sha256='a'*64),{'root-filesystem':image}
    def test_removable_capacity_and_whole_disk_guards(self):
        info=self.media();card.validate_card(info,'/dev/disk99',1024*1024)
        for key,value in [('RemovableMedia',False),('WholeDisk',False),('Writable',False),('VirtualOrPhysical','Virtual'),('TotalSize',512),('DeviceTreePath','')]:
            with self.subTest(key=key),self.assertRaises(ValueError):card.validate_card(dict(info,**{key:value}),'/dev/disk99',1024*1024)
        with self.assertRaises(ValueError):card.validate_card(info,'/dev/disk99s1',1024)
    def test_card_geometry_and_kernel_partition_identity_agree(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest,files=self.kit(Path(folder));raw=b''.join(card.blocks(manifest,files['root-filesystem'],8*1024*1024))
            self.assertEqual(len(raw),card.OFFSET+manifest['root_bytes'])
            self.assertEqual(struct.unpack_from('<I',raw,440)[0],int(manifest['disk_id'],16))
            self.assertEqual(struct.unpack_from('<II',raw,454),(2048,8*1024*1024//512-2048))
            self.assertEqual(hashlib.sha256(raw[card.OFFSET:]).hexdigest(),manifest['root_sha256'])
    def test_write_readback_and_target_pinned_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,files=self.kit(root);device=root/'device';device.write_bytes(bytes(self.media()['TotalSize']))
            real_open=open
            def fixture_open(path,*args,**kw):return real_open(device if str(path)=='/dev/rdisk99' else path,*args,**kw)
            with patch.object(card.sys,'platform','darwin'),patch.object(card,'verify_local_kit',return_value=({},manifest,files)),patch.object(card.subprocess,'check_output',return_value=plistlib.dumps(self.media())),patch.object(card.subprocess,'run'),patch.object(card.os,'geteuid',return_value=0),patch('builtins.open',side_effect=fixture_open):
                result=card.install(root,'/dev/disk99',0x2100000,True,lambda _:None)
            receipt=json.loads((root/'INSTALL-STATE.json').read_text())
            self.assertTrue(receipt['rootfs_readback_verified']);self.assertEqual(receipt['usb_location'],0x2100000)
            self.assertEqual(receipt['storage_target'],'sd');self.assertEqual(receipt['written_bytes'],card.OFFSET+manifest['root_bytes'])
            self.assertEqual(result['state'],'rootfs_written')
    def test_failed_readback_never_produces_a_flash_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,files=self.kit(root);device=root/'device';device.write_bytes(bytes(self.media()['TotalSize']))
            real_open=open
            def fixture_open(path,*args,**kw):
                if str(path)=='/dev/rdisk99':
                    return io.BytesIO(bytes(card.OFFSET+manifest['root_bytes'])) if args[0]=='rb' else real_open(device,*args,**kw)
                return real_open(path,*args,**kw)
            with patch.object(card.sys,'platform','darwin'),patch.object(card,'verify_local_kit',return_value=({},manifest,files)),patch.object(card.subprocess,'check_output',return_value=plistlib.dumps(self.media())),patch.object(card.subprocess,'run'),patch.object(card.os,'geteuid',return_value=0),patch('builtins.open',side_effect=fixture_open):
                with self.assertRaisesRegex(ValueError,'readback mismatch'):card.install(root,'/dev/disk99',1,True,lambda _:None)
            self.assertFalse((root/'INSTALL-STATE.json').exists())

    def test_internal_kit_is_rejected_before_media_inspection(self):
        with patch.object(card.sys,'platform','darwin'),patch.object(card,'verify_local_kit',return_value=({},dict(storage_target='internal'),{})),patch.object(card.subprocess,'check_output') as inspect:
            with self.assertRaises(ValueError):card.install('/fixture','/dev/disk99',1)
            inspect.assert_not_called()
    def test_changed_card_is_rejected_before_opening_disk(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);manifest,files=self.kit(root);info=self.media()
            with patch.object(card.sys,'platform','darwin'),patch.object(card,'verify_local_kit',return_value=({},manifest,files)),patch.object(card.subprocess,'check_output',side_effect=[plistlib.dumps(info),plistlib.dumps(dict(info,DeviceTreePath='other-reader'))]),patch.object(card.subprocess,'run'),patch.object(card.os,'geteuid',return_value=0),patch('builtins.open') as opened:
                with self.assertRaisesRegex(ValueError,'identity changed'):card.install(root,'/dev/disk99',1,True,lambda _:None)
                opened.assert_not_called()
    def test_storage_limits_and_cross_target_receipt(self):
        validate_size('sd',4096)
        with self.assertRaises(ValueError):validate_size('internal',4096)
        with self.assertRaises(ValueError):require_target({'storage_target':'sd'},'internal')
