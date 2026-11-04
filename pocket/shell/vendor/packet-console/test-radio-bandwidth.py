import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest

spec=importlib.util.spec_from_file_location('bandwidth',Path(__file__).with_name('n810-radio-bandwidth.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
LAYOUT=json.loads(Path(__file__).with_name('radio-read-layouts.json').read_text())


def packed(name,**values):
    total=0;bits=0
    for key,width,kind in LAYOUT[name]:
        value=values.get(key,0)
        if kind=='str':value=int.from_bytes(str(value).encode().ljust(width//8,b'\0'),'big') if value else 0
        bits=(bits<<width)|int(value);total+=width
    return bits.to_bytes(total//8,'big')


def channel(**changes):
    values=dict(channel_id=0,rx_freq=144390000,tx_freq=144390000,name_str='APRS 144',
                tx_at_max_power=True,pre_de_emph_bypass=True,sign=True,_pad=9)
    values.update(changes);return packed('RfCh',**values)


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.sent=[]
        self.tx=b.Transaction(lambda *args:self.sent.append(args),self.root/'request',self.root/'result')
        self.status=packed('StatusExt',is_power_on=True,is_in_rx=True)
        self.settings=packed('Settings',auto_share_loc_ch=1,kiss_en=True,channel_b_lower=2)
        self.beacon=packed('BSSSettings',aprs_callsign='N0ANT')
    def tearDown(self):self.temp.cleanup()
    def start(self,action=b.ACTION):
        b.atomic(self.root/'request',dict(id='one',action=action,created_at=time.time()))
        self.tx.tick(0);self.tx.tick(2)
    def drive(self,raw=None,readback=None,pre_settings=None):
        raw=channel() if raw is None else raw;written=False
        for _ in range(20):
            if not self.tx.active:return
            name,cmd=self.tx.waiting
            if cmd==20:body=self.status
            elif cmd==10:body=pre_settings if name=='settings_prewrite' and pre_settings is not None else self.settings
            elif cmd==33:body=self.beacon
            elif cmd==13:body=(readback if readback is not None else self.tx.desired) if name=='channel_after' else raw
            elif cmd==14:written=True;body=b'\0'
            self.tx.consume(cmd|0x8000,b'\0'+body)
        self.fail('Transaction did not terminate')
    def writes(self):return [s for s in self.sent if s[0]==14]

    def test_read_only_reports_both_bandwidth_and_emphasis_without_write(self):
        for wide,bypass in ((0,0),(1,1)):
            self.tx.seen=None;self.sent.clear()
            raw=channel(bandwidth=wide,pre_de_emph_bypass=bypass,fixed_bandwidth=True)
            self.start(b.READ_ACTION);self.drive(raw)
            self.assertEqual(self.tx.result['state'],'read');self.assertTrue(self.tx.result['completed'])
            self.assertTrue(self.tx.result['read_only']);self.assertFalse(self.tx.result['write_attempted'])
            self.assertEqual(self.tx.result['reported']['bandwidth_khz'],25 if wide else 12.5)
            self.assertEqual(self.tx.result['reported']['pre_de_emph_bypass'],bool(bypass))
            self.assertEqual(self.tx.result['channel_raw'],raw.hex())
            self.assertTrue(all(command in (20,10,33,13) for command,_,_ in self.sent));self.assertFalse(self.writes())
    def test_read_only_does_not_require_transmitter_idle(self):
        self.status=packed('StatusExt',is_power_on=True,is_in_tx=True)
        self.start(b.READ_ACTION);self.drive()
        self.assertEqual(self.tx.result['state'],'read');self.assertFalse(self.writes())
    def test_read_only_wrong_mapping_fails_without_write(self):
        self.status=packed('StatusExt',is_power_on=True,curr_region=1)
        self.start(b.READ_ACTION);self.drive()
        self.assertEqual(self.tx.result['state'],'failed');self.assertFalse(self.writes())
    def test_read_only_internal_write_stage_is_rejected(self):
        self.start(b.READ_ACTION)
        self.tx.queue=[('write',14,channel(bandwidth=1))];self.tx.waiting=None
        self.tx.advance(time.monotonic())
        self.assertEqual(self.tx.result['state'],'failed');self.assertFalse(self.writes())
        self.assertFalse(self.tx.result['write_attempted'])
    def test_only_bandwidth_bit_changes_and_full_readback_verified(self):
        raw=channel();self.start();self.drive(raw)
        self.assertEqual(self.tx.result['state'],'verified');self.assertTrue(self.tx.result['readback_verified'])
        write=self.writes();self.assertEqual(len(write),1)
        self.assertEqual(write[0][2],raw)
        self.assertEqual(bytes(a^c for a,c in zip(raw,write[0][1])),bytes(13)+b'\x10'+bytes(11))
        self.assertEqual(self.tx.result['original_raw'],raw.hex())
        self.assertEqual(self.tx.result_path.stat().st_mode&0o777,0o600)
    def test_already_wide_never_writes(self):
        self.start();self.drive(channel(bandwidth=1))
        self.assertEqual(self.writes(),[]);self.assertEqual(self.tx.result['state'],'verified')
        self.assertFalse(self.tx.result['changed'])
    def test_enabled_beacon_is_read_and_preserved_without_setting_write(self):
        self.beacon=packed('BSSSettings',aprs_callsign='N0ANT',should_share_location=True)
        self.start();self.drive()
        self.assertEqual(self.tx.result['state'],'verified')
        self.assertEqual(self.tx.result['reads']['beacon_before'],self.tx.result['reads']['beacon_after'])
        self.assertTrue(all(command in (20,10,33,13,14) for command,_,_ in self.sent))
    def test_extended_channel_suffix_preserved(self):
        raw=channel()+b'\xff\xaa';self.start();self.drive(raw)
        self.assertEqual(self.tx.result['state'],'verified')
        self.assertEqual(self.writes()[0][1][-2:],b'\xff\xaa')
    def test_walking_ssid_refused_before_write(self):
        self.beacon=packed('BSSSettings',aprs_callsign='N0ANT',aprs_ssid=7)
        self.start();self.drive();self.assertEqual(self.tx.result['state'],'failed');self.assertFalse(self.writes())
    def test_every_other_changed_bit_rejected(self):
        raw=channel();desired=raw[:13]+bytes([raw[13]|0x10])+raw[14:]
        for index in range(200):
            if index==107:continue
            wrong=bytearray(desired);wrong[index//8]^=1<<(7-index%8)
            with self.assertRaises(ValueError):b.wide_only(raw,bytes(wrong))
    def test_mapping_frequency_beacon_and_concurrent_settings_guard(self):
        cases=[('status',packed('StatusExt',is_power_on=True,curr_region=1)),('status',packed('StatusExt',is_power_on=True,is_in_tx=True))]
        for field,value in cases:
            self.sent.clear();setattr(self,field,value);self.start();self.drive()
            self.assertEqual(self.writes(),[]);self.assertEqual(self.tx.result['state'],'failed')
            self.tx.seen=None
            self.status=packed('StatusExt',is_power_on=True,is_in_rx=True);self.beacon=packed('BSSSettings',aprs_callsign='N0ANT')
        self.start();self.drive(raw=channel(rx_freq=146520000));self.assertFalse(self.writes())
    def test_changed_settings_abort_before_write(self):
        changed=bytearray(self.settings);changed[-1]^=1
        self.start();self.drive(pre_settings=bytes(changed))
        self.assertFalse(self.writes());self.assertEqual(self.tx.result['state'],'failed')
    def test_readback_mismatch_has_no_retry_or_automatic_rollback(self):
        raw=bytearray(channel(bandwidth=1));raw[-1]^=1
        self.start();self.drive(readback=bytes(raw))
        self.assertEqual(len(self.writes()),1);self.assertEqual(self.tx.result['state'],'failed')
        self.assertTrue(self.tx.result['write_may_have_occurred']);self.assertIn('original_raw',self.tx.result)
    def test_timeout_and_no_replay_after_owner_restart(self):
        self.start();self.tx.tick(self.tx.deadline+1)
        self.assertEqual(self.tx.result['state'],'failed');self.assertFalse(self.writes())
        other=b.Transaction(lambda *args:self.fail('Replayed stale mailbox'),self.root/'request',self.root/'other')
        other.tick();self.assertFalse(other.active)
    def test_stale_request_refused_without_any_radio_request(self):
        b.atomic(self.root/'request',dict(id='old',action=b.ACTION,created_at=time.time()-60))
        self.tx.tick();self.assertFalse(self.sent);self.assertEqual(self.tx.result['state'],'failed')


if __name__=='__main__':unittest.main()
