"""Persistent-data startup must recover safely before resize, or stop."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).with_name('ab_prepare_data.sh')

class PrepareData(unittest.TestCase):
    def invoke(self,fsck,resize=0):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,status in (('e2fsck',fsck),('resize2fs',resize)):
                tool=root/name
                tool.write_text('#!/bin/sh\necho '+name+' >> "$CALLS"\nexit '+str(status)+'\n')
                tool.chmod(0o755)
            result=subprocess.run(['sh',str(SCRIPT),'/dev/fixture'],env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'],CALLS=str(root/'calls')),capture_output=True,text=True)
            return result.returncode,(root/'calls').read_text().splitlines()
    def test_clean_and_corrected_filesystems_continue(self):
        for status in (0,1):
            with self.subTest(status=status):self.assertEqual(self.invoke(status),(0,['e2fsck','resize2fs']))
    def test_reboot_required_or_uncorrected_errors_block_resize(self):
        for status in (2,3,4,8,16,32,128):
            with self.subTest(status=status):self.assertEqual(self.invoke(status),(status,['e2fsck']))
    def test_resize_failure_is_not_hidden(self):
        self.assertEqual(self.invoke(0,1),(1,['e2fsck','resize2fs']))
