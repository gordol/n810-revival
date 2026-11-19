"""Opt-in Linux kernel integration test using only a newly allocated loop fixture."""
import errno
import gzip
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from linux_storage import transfer


@unittest.skipUnless(sys.platform.startswith('linux') and os.environ.get('N810_LOOP_TEST') == '1',
                     'Set N810_LOOP_TEST=1 in a disposable privileged Linux container')
class LinuxBlockDeviceTest(unittest.TestCase):
    def test_exclusive_mount_guard_flush_and_readback(self):
        self.assertEqual(os.geteuid(), 0)
        with tempfile.TemporaryDirectory(prefix='n810-loop-test-') as folder:
            root=Path(folder);backing=root/'disk.img'
            with backing.open('wb') as stream:stream.truncate(16*1024*1024)
            loop=subprocess.check_output(['losetup','--find','--show',str(backing)],text=True).strip()
            try:
                subprocess.run(['mkfs.ext4','-q','-F',loop],check=True)
                mounted=root/'mounted';mounted.mkdir()
                subprocess.run(['mount',loop,str(mounted)],check=True)
                try:
                    with self.assertRaises(OSError) as error:
                        fd=os.open(loop,os.O_RDWR|os.O_EXCL)
                        os.close(fd)
                    self.assertEqual(error.exception.errno,errno.EBUSY)
                finally:subprocess.run(['umount',str(mounted)],check=True)
                data=b'fixture'+bytes(4*1024*1024-7)
                image=root/'root.gz'
                with gzip.open(image,'wb') as stream:stream.write(data)
                manifest=dict(disk_id='1357abcd',root_bytes=len(data),root_sha256=hashlib.sha256(data).hexdigest())
                fd=os.open(loop,os.O_RDWR|os.O_EXCL|os.O_NOFOLLOW)
                try:
                    count,digest=transfer(fd,manifest,image,16*1024*1024,lambda _:None)
                    self.assertEqual(count,5*1024*1024)
                    os.lseek(fd,0,os.SEEK_SET)
                    self.assertEqual(os.read(fd,512)[510:],b'\x55\xaa')
                finally:os.close(fd)
            finally:subprocess.run(['losetup','--detach',loop],check=True)
