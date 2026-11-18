from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import uvpro_settings


class Edit(unittest.TestCase):
    def setUp(self):
        self.patch=patch.object(uvpro_settings,'__file__',str(HERE.parent/'vendor/packet-console/helper.py'))
        self.patch.start();self.addCleanup(self.patch.stop)
        self.edit=dict(group='settings',field='squelch_level',expected=3,value=5)
        self.raw=bytes([0x98,0xb3])+bytes(range(20))
    def test_changes_only_requested_bits_then_verifies(self):
        job=uvpro_settings.transaction(self.edit)
        self.assertEqual(next(job),(10,b'',None))
        command,desired,original=job.send(self.raw)
        self.assertEqual((command,original),(11,self.raw))
        self.assertEqual(desired,self.raw[:1]+b'\xb5'+self.raw[2:])
        self.assertEqual(job.send(b''),(10,b'',None))
        with self.assertRaisesRegex(ValueError,'readback'):job.send(self.raw)
    def test_noop_read_only(self):
        job=uvpro_settings.transaction(dict(self.edit,value=3))
        next(job);self.assertEqual(job.send(self.raw),(10,b'',None))
        with self.assertRaises(StopIteration) as done:job.send(self.raw)
        self.assertFalse(done.exception.value['changed'])
    def test_stale_or_invalid_rejected(self):
        for edit in (dict(self.edit,expected=2),dict(self.edit,value=10),dict(self.edit,field='_unknown')):
            with self.assertRaises(ValueError):uvpro_settings.changed(self.raw,edit)
