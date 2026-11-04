import importlib.util
from pathlib import Path
import tempfile
import time
import unittest
spec=importlib.util.spec_from_file_location('fixtures',Path(__file__).with_name('test-radio-bandwidth.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
b=f.b


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.sent=[];self.tx=b.Transaction(lambda *args:self.sent.append(args),root/'request',root/'result')
        self.status=f.packed('StatusExt',is_power_on=True,is_in_tx=True)
        self.settings=f.packed('Settings',auto_share_loc_ch=1,kiss_en=True)
        self.beacon=f.packed('BSSSettings',aprs_callsign='N0ANT',should_share_location=True,location_share_interval=0,smart_beacon_en=False,_unk_bss_1=1)
        self.channel=f.channel(bandwidth=1,pre_de_emph_bypass=False)
    def tearDown(self):self.temp.cleanup()
    def start(self):
        b.atomic(self.tx.request_path,dict(id='stop-one',action=b.STOP_ACTION,created_at=time.time()))
        self.tx.tick(0);self.tx.tick(2)
    def drive(self,wrong=False):
        for _ in range(18):
            if not self.tx.active:return
            name,cmd=self.tx.waiting
            if cmd==20:raw=self.status
            elif cmd==10:raw=self.settings
            elif cmd==13:raw=self.channel
            elif cmd==33:
                raw=self.beacon if name!='beacon_after' else self.tx.desired_beacon
                if wrong and name=='beacon_after':raw=raw[:-1]+bytes([raw[-1]^1])
            elif cmd==34:raw=b''
            else:self.fail('Unexpected command '+str(cmd))
            self.tx.consume(cmd|0x8000,b'\0'+raw)
        self.fail('Did not complete')
    def test_only_share_flag_cleared_full_readback_and_channel_unchanged(self):
        self.start();self.drive()
        self.assertEqual(self.tx.result['state'],'beacon_disabled');self.assertTrue(self.tx.result['readback_verified'])
        writes=[s for s in self.sent if s[0]==34];self.assertEqual(len(writes),1)
        self.assertEqual(writes[0][2],self.beacon)
        self.assertEqual(bytes(a^c for a,c in zip(self.beacon,writes[0][1])),b'\0\x10'+bytes(48))
        self.assertEqual(self.tx.result['reads']['channel_before'],self.tx.result['reads']['channel_after'])
        self.assertTrue(all(s[0] in (20,10,33,13,34) for s in self.sent))
        self.assertEqual(writes[0][1][3],0) # intervalraw0 unchanged
    def test_already_disabled_never_writes(self):
        self.beacon=self.beacon[:1]+bytes([self.beacon[1]&~16])+self.beacon[2:]
        self.start();self.drive()
        self.assertEqual(self.tx.result['state'],'beacon_disabled');self.assertFalse(self.tx.result['changed'])
        self.assertFalse(any(s[0] in (14,34) for s in self.sent))
    def test_all_other_bits_and_enable_rejected(self):
        desired=self.beacon[:1]+bytes([self.beacon[1]&~16])+self.beacon[2:]
        for index in range(400):
            if index==11:continue
            wrong=bytearray(desired);wrong[index//8]^=1<<(7-index%8)
            with self.assertRaises(ValueError):b.disable_beacon_only(self.beacon,bytes(wrong))
        with self.assertRaises(ValueError):b.disable_beacon_only(desired,self.beacon)
    def test_full_mismatch_fails_without_auto_retry_or_enable(self):
        self.start();self.drive(wrong=True)
        self.assertEqual(self.tx.result['state'],'failed')
        self.assertTrue(self.tx.result['write_may_have_occurred'])
        self.assertEqual(len([s for s in self.sent if s[0]==34]),1)
        self.assertEqual(self.tx.result['original_beacon_raw'],self.beacon.hex())
    def test_52byte_suffix_preserved(self):
        self.beacon+=b'\xff\xa5';self.start();self.drive()
        self.assertEqual(self.tx.result['state'],'beacon_disabled')
        self.assertEqual([s for s in self.sent if s[0]==34][0][1][-2:],b'\xff\xa5')
    def test_stop_action_cannot_reach_channel_write(self):
        self.start();self.tx.waiting=None;self.tx.queue=[('write',14,self.channel)]
        self.tx.advance(time.monotonic())
        self.assertEqual(self.tx.result['state'],'failed');self.assertFalse(any(s[0]==14 for s in self.sent))


if __name__=='__main__':unittest.main()
