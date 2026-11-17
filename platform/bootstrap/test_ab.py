"""A/B failure-path and on-disk partition contract tests; no hardware writes."""
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from ab_runtime import choose,confirm,atomic,config,validate_state
from ab_media import layout,MIB

class BootState(unittest.TestCase):
    def state(self):return dict(version=1,active='A',pending='B',tries=3)
    def test_three_failed_trials_return_to_confirmed_slot(self):
        state=self.state()
        for tries in (2,1,0):
            slot,state=choose(state);self.assertEqual(slot,'B');self.assertEqual(state['tries'],tries)
        slot,state=choose(state);self.assertEqual(slot,'A');self.assertIsNone(state['pending'])
    def test_success_is_explicit_and_cannot_confirm_other_slot(self):
        slot,state=choose(self.state())
        with self.assertRaises(ValueError):confirm(state,'A')
        state=confirm(state,'B');self.assertEqual(choose(state)[0],'B');self.assertIsNone(state['pending'])
    def test_selection_does_not_mutate_uncommitted_state(self):
        state=self.state();before=copy.deepcopy(state);choose(state);self.assertEqual(state,before)
    def test_corrupt_state_stays_in_recovery(self):
        for change in ({'active':'C'},{'tries':True},{'tries':-1},{'tries':4},{'pending':'/bin/sh'},{'version':2}):
            with self.subTest(change=change),self.assertRaises(ValueError):choose(dict(self.state(),**change))
    def test_atomic_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'state.json';atomic(p,self.state());atomic(p,choose(self.state())[1])
            self.assertEqual(json.loads(p.read_text())['tries'],2);self.assertEqual(len(list(Path(t).iterdir())),1)
    def test_distinct_recovery_identity_required(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'config';p.write_text(json.dumps(dict(sd_disk_id='12345678',recovery_disk_id='12345678',data_schema=1)))
            with self.assertRaises(ValueError):config(p)

class Media(unittest.TestCase):
    def manifest(self):return dict(slot_mib=1536,sd_disk_id='12345678',files={'data.ext4':{'bytes':256*MIB}})
    def test_slots_and_persistence_are_disjoint_and_fill_card(self):
        capacity=8*1024*MIB;table,images=layout(self.manifest(),capacity)
        self.assertEqual(table[510:512],b'\x55\xaa')
        self.assertEqual(struct.unpack_from('<I',table,440)[0],0x12345678)
        previous=2048
        for i,(offset,name) in enumerate(images):
            start,sectors=struct.unpack_from('<II',table,454+16*i)
            self.assertEqual(start,previous);self.assertEqual(offset,start*512)
            self.assertGreater(sectors,0);previous=start+sectors
        self.assertEqual(previous*512,capacity)
        self.assertEqual([n for _,n in images],['control.ext4','slot.ext4','slot.ext4','data.ext4'])
    def test_small_or_misaligned_media_rejected(self):
        for size in (2*1024*MIB,8*1024*MIB+1):
            with self.assertRaises(ValueError):layout(self.manifest(),size)

if __name__=='__main__':unittest.main()

class Stage(unittest.TestCase):
    def test_private_seed_is_separate_from_readonly_os_and_shell_is_valid(self):
        import subprocess
        from unittest.mock import patch
        from ab_stage import stage
        with tempfile.TemporaryDirectory() as t:
            base=Path(t);root=base/'root';data=base/'data';kernel=base/'kernel'
            data.mkdir();kernel.mkdir()
            for name in ('etc/ssh','etc/default','etc/init.d','var/lib/dpkg','var/lib/n810-radio',
                         'var/log','var/tmp','var/cache/apt/archives','usr/local/sbin','sbin','home/nokia','root','tmp',
                         'etc/rc2.d','etc/rc3.d','etc/rc4.d','etc/rc5.d'):
                (root/name).mkdir(parents=True,exist_ok=True)
            (root/'etc/wpa_supplicant').mkdir();(root/'etc/wpa_supplicant/wpa_supplicant-wlan0.conf').write_text('private fixture')
            (root/'etc/passwd').write_text('nokia:x:1000:1000::/home/nokia:/bin/sh\n')
            (kernel/'BUILD.json').write_text('{"ab_boot":true}');(kernel/'KERNELRELEASE').write_text('fixture')
            for name in ('zImage','omap2420-n810.dtb'):(kernel/name).write_bytes(b'fixture')
            actual=subprocess.run
            def run(args,**kw):
                if args[0]=='chroot':
                    (root/'tmp/n810-ab-hostkey').write_text('private fixture key')
                    (root/'tmp/n810-ab-hostkey.pub').write_text('public fixture key')
                    return subprocess.CompletedProcess(args,0)
                return actual(args,**kw)
            with patch('ab_stage.subprocess.run',side_effect=run):
                stage(root,data,kernel,dict(sd_disk_id='12345678',recovery_disk_id='87654321',data_schema=1))
            self.assertEqual((data/'etc/ssh/ssh_host_ed25519_key').read_text(),'private fixture key')
            self.assertEqual((data/'etc/wpa_supplicant/wpa_supplicant-wlan0.conf').read_text(),'private fixture')
            self.assertTrue((root/'etc/wpa_supplicant').is_symlink())
            self.assertTrue((root/'usr/lib/n810-ab/etc/ssh/ssh_host_ed25519_key').is_symlink())
            self.assertTrue((root/'etc/n810-ab/config.json').is_symlink())
            self.assertEqual(json.loads((data/'etc/n810-ab/config.json').read_text())['sd_disk_id'],'12345678')
            self.assertFalse((data/'var/lib/dpkg').exists())
            self.assertEqual(data.stat().st_mode&0o777,0o755)
            self.assertNotIn('resize2fs /dev/disk/by-partuuid',(root/'sbin/n810-slot-init').read_text())
            subprocess.run(['sh','-n',str(root/'sbin/n810-slot-init')],check=True)
