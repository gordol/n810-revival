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
