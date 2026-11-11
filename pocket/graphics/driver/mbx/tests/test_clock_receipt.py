# SPDX-License-Identifier: MIT
"""Receipt policy must preserve either observed divider, never infer a reset."""
from pathlib import Path
import copy
import importlib.util
import unittest

path=Path(__file__).resolve().parents[5]/'graphics/mbx/runtime/judge_probe.py'
spec=importlib.util.spec_from_file_location('mbx_clock_judge',path)
judge=importlib.util.module_from_spec(spec);spec.loader.exec_module(judge)

def receipt(initial):
    values=judge.CLEAN|judge.READY|judge.INPUTS|{
        'readiness_samples':2,'gpu_dma_stage':0,'probe_mode':0,
        'gpu_submitted':0,'gpu_words_written':0,'gpu_completion_status':0,
        'gpu_capture_valid':0,'gpu_quiesced':0,'observed_core_id':0x01010000,
        'observed_revision':1,'observed_product_id':0,'observed_part_number':0,
        'observed_select':initial,'active_divider':initial,
        'divider_change_attempted':int(initial!=2),'divider_restore_attempts':int(initial!=2)}
    return {'kernel_release':judge.RELEASE,'module_sha256':'0'*64,'parameters':values,
            'initial_divider':initial,'log_complete':True,
            'initial_final_gates_match':True,'initial_final_selector_match':True}

class ClockReceipt(unittest.TestCase):
    def test_original_divider_and_transition_counts(self):
        for initial in (1,2):
            good=receipt(initial)
            self.assertEqual(judge.judge(good,'0'*64)['status'],'CLEAN_IDENTITY_RECEIPT')
            for key in ('active_divider','observed_select','divider_change_attempted','divider_restore_attempts'):
                bad=copy.deepcopy(good);bad['parameters'][key]^=3
                with self.assertRaises(ValueError):judge.judge(bad,'0'*64)
        old=receipt(1);old.pop('initial_divider')
        self.assertEqual(judge.judge(old,'0'*64)['status'],'CLEAN_IDENTITY_RECEIPT')
        old=receipt(2);old.pop('initial_divider')
        with self.assertRaises(ValueError):judge.judge(old,'0'*64)
    def test_invalid_or_unverified_initial_state(self):
        for value in (0,3,True,None):
            bad=receipt(2);bad['initial_divider']=value
            with self.assertRaises(ValueError):judge.judge(bad,'0'*64)
        bad=receipt(2);bad['initial_final_selector_match']=False
        with self.assertRaises(ValueError):judge.judge(bad,'0'*64)

if __name__=='__main__':unittest.main()
