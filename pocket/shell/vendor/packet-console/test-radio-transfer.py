import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
spec=importlib.util.spec_from_file_location('transfer',Path(__file__).with_name('n810-radio-transfer.py'))
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)


def snapshot(**changes):
    fields=dict(channel_id=0,name_str='APRS',rx_freq=144390000,tx_freq=144390000,rx_sub_audio=0,
                tx_sub_audio=10000,rx_mod=0,tx_mod=0,bandwidth=0,tx_at_max_power=True,
                tx_at_med_power=False,tx_disable=False,scan=False,mute=False,talk_around=False,
                pre_de_emph_bypass=True,vendor_unknown=77)
    fields.update(changes)
    return dict(complete=True,finished='2026-10-17T12:00:00Z',banks=[dict(index=0,name='Ham',channels=[dict(index=0,response={'status':0},decoded=fields),dict(index=1,response={'status':0},decoded=dict(fields,channel_id=1,rx_freq=0))])])


class Tests(unittest.TestCase):
    def test_pull_is_new_local_copy_no_implicit_save_or_overwrite(self):
        snap=snapshot();before=copy.deepcopy(snap);local={'version':1,'banks':[t.library.core_bank()]}
        original=copy.deepcopy(local);plan=t.plan_pull(snap,0)
        self.assertTrue(plan['can_apply_locally']);self.assertTrue(plan['review_required']);self.assertFalse(plan['saved'])
        self.assertEqual(plan['slots'][1]['state'],'empty')
        copied=t.apply_pull(local,plan)
        self.assertEqual(local,original);self.assertEqual(snap,before)
        bank=copied['banks'][-1];self.assertNotEqual(bank['id'],'core')
        self.assertNotIn('hardware_slot',bank['channels'][0])
        self.assertEqual(bank['channels'][0]['radio_origin']['raw']['decoded']['vendor_unknown'],77)
        self.assertEqual(bank['channels'][0]['tx_ctcss'],100)
        with self.assertRaises(ValueError):t.apply_pull(copied,plan)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'banks.json';self.assertFalse(path.exists())
            t.library.save(path,copied);loaded=t.library.read_saved(path)
            self.assertEqual(loaded,copied)
            self.assertEqual(loaded['banks'][-1]['channels'][0]['id'],bank['channels'][0]['id'])

    def test_unknown_and_unrepresented_never_silently_become_off(self):
        for fields in ({'rx_sub_audio':23},{'rx_mod':1},{'rx_mod':None},{'tx_freq':0},{'tx_at_max_power':None},{'rx_freq':123450000}):
            plan=t.plan_pull(snapshot(**fields),0)
            self.assertFalse(plan['can_apply_locally']);self.assertTrue(plan['blocks'])
            with self.assertRaises(ValueError):t.apply_pull({'version':1,'banks':[]},plan)
        snap=snapshot();snap['banks'][0]['channels'][0]['response']['status']=1
        self.assertFalse(t.plan_pull(snap,0)['can_apply_locally'])

    def test_push_is_explicit_diff_only_and_preserves_untouched_slots(self):
        local={'version':1,'banks':[]};bank=t.library.import_csv(local,'name,rx_mhz\nDraft,146.52\n','Local')
        before=copy.deepcopy(local);snap=snapshot();old=copy.deepcopy(snap)
        plan=t.plan_push(snap,0,local,bank['id'],[dict(channel_id=bank['channels'][0]['id'],memory_index=0)])
        self.assertFalse(plan['can_execute']);self.assertFalse(plan['capabilities']['push'])
        self.assertFalse(plan['capabilities']['pull_live']);self.assertFalse(plan['capabilities']['verify_radio_write'])
        fields={f['field']:f['state'] for f in plan['changes'][0]['comparison']['fields']}
        self.assertEqual(fields['rx_hz'],'different');self.assertEqual(fields['rx_mode'],'not_represented')
        self.assertEqual(plan['untouched_radio_slots'],[1])
        self.assertEqual(local,before);self.assertEqual(snap,old)
        self.assertTrue(any('Read back' in step for step in plan['required_before_execution']))

    def test_core_mapping_and_ambiguous_or_missing_ids_fail(self):
        local={'version':1,'banks':[t.library.core_bank()]};core=local['banks'][0]['channels'][0]['id']
        with self.assertRaises(ValueError):t.plan_push(snapshot(),0,local,'core',[dict(channel_id=core,memory_index=1)])
        for index in (True,'0',5):
            with self.assertRaises(ValueError):t.plan_pull(snapshot(),index)
        for assignments in ([dict(channel_id='missing',memory_index=0)],[dict(channel_id=core,memory_index=0)]*2):
            with self.assertRaises(ValueError):t.plan_push(snapshot(),0,local,'core',assignments)
        snap=snapshot();snap['complete']=False
        with self.assertRaises(ValueError):t.plan_pull(snap,0)


if __name__=='__main__':unittest.main()
