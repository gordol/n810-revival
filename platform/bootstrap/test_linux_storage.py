"""Linux storage safety and transfer tests; no user storage is accessed."""
import gzip
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from linux_storage import validate, transfer, INTERNAL_BYTES
from internal_installer import identify_device, flash_kernel


class LinuxStorageTests(unittest.TestCase):
    def info(self):
        return dict(partition=False,readonly=False,sector_size=512,busy=False,
                    bytes=INTERNAL_BYTES,usb_port='1-2.3',usb_vendor='0421',model='N810',
                    removable=True,mmc_type='')

    def test_internal_requires_exact_nokia_identity_and_port(self):
        validate(self.info(),'internal',1024,'1-2.3')
        for key,value in [('partition',True),('readonly',True),('sector_size',4096),
                          ('busy',True),('bytes',4*1024**3),('usb_port','1-2.4'),
                          ('usb_vendor','1234'),('model','Other')]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate(dict(self.info(),**{key:value}),'internal',1024,'1-2.3')

    def test_sd_refuses_nokia_export_and_fixed_or_active_disks(self):
        with self.assertRaises(ValueError): validate(self.info(),'sd',1024,'1-2.3')
        info=dict(self.info(),usb_vendor='1234',model='Card Reader',usb_port='2-1')
        validate(info,'sd',1024,'1-2.3')
        validate(dict(info,usb_port='',mmc_type='SD'),'sd',1024,'1-2.3')
        for key,value in [('removable',False),('busy',True),('readonly',True),('partition',True)]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate(dict(info,**{key:value}),'sd',1024,'1-2.3')

    def test_complete_write_and_readback(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);data=b'root-fixture'+bytes(4096-len(b'root-fixture'))
            image=folder/'root.gz'
            with gzip.open(image,'wb') as stream:stream.write(data)
            disk=folder/'disk';disk.write_bytes(bytes(2*1024*1024))
            manifest=dict(disk_id='1234abcd',root_bytes=len(data),root_sha256=hashlib.sha256(data).hexdigest())
            fd=os.open(disk,os.O_RDWR)
            try:
                with patch('linux_storage.fcntl.ioctl'):
                    count,digest=transfer(fd,manifest,image,disk.stat().st_size,lambda _:None)
                raw=disk.read_bytes()[:count]
                self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
                self.assertEqual(raw[1024*1024:],data)
                with patch('linux_storage.fcntl.ioctl'),patch('linux_storage.os.read',return_value=b''):
                    os.lseek(fd,0,os.SEEK_SET)
                    with self.assertRaisesRegex(OSError,'readback'):transfer(fd,manifest,image,disk.stat().st_size,lambda _:None)
            finally:os.close(fd)

    def test_multiple_nokia_devices_refused_before_flasher(self):
        with patch('internal_installer.platform.system',return_value='Linux'), \
             patch('linux_storage.nokia_ports',return_value=['1-2','1-3']), \
             patch('internal_installer._run_flasher') as run:
            with self.assertRaisesRegex(ValueError,'exactly one'):identify_device('/fixture')
            run.assert_not_called()

    def test_linux_identity_includes_stable_port(self):
        with patch('internal_installer.platform.system',return_value='Linux'), \
             patch('linux_storage.nokia_ports',return_value=['1-2']), \
             patch('internal_installer._run_flasher',return_value='Device: RX-44'):
            self.assertEqual(identify_device('/fixture')['usb_port'],'1-2')

    def test_wrong_port_cannot_flash(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('internal_installer.platform.system',return_value='Linux'), \
                 patch('internal_installer.verify_local_kit',return_value=({}, {}, {})), \
                 patch('internal_installer.checked_write_receipt',return_value={'usb_port':'1-2'}), \
                 patch('internal_installer.identify_device',return_value={'usb_port':'1-3'}), \
                 patch('internal_installer._run_flasher') as run:
                with self.assertRaisesRegex(ValueError,'different Linux'):flash_kernel(folder)
                run.assert_not_called()
