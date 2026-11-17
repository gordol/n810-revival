"""Same-kernel handoff rejects incompatible slots before running their startup."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import ab_early as early
import ab_runtime as runtime

class Compatibility(unittest.TestCase):
    def test_exact_build_required_not_just_release(self):
        manifest=dict(boot_method='same-kernel-root-switch',kernel_release=os.uname().release,kernel_notes_sha256='expected')
        with patch.object(runtime,'digest',return_value='expected'):
            runtime.verify_kernel(manifest)
            for bad in ({'kernel_release':'other'},{'kernel_notes_sha256':'other'},{'boot_method':'kexec'}):
                with self.assertRaises(ValueError):runtime.verify_kernel(dict(manifest,**bad))
    def test_wrong_kernel_never_executes_slot_code(self):
        with patch.object(early,'mounted'), patch.object(early,'read',return_value={'data_schema':1}), patch.object(early,'verify_kernel',side_effect=ValueError('mismatch')), patch.object(early,'run') as run:
            with self.assertRaises(ValueError):early.prepare({'data_schema':1},{2:'/dev/fixture'},'A')
            run.assert_not_called()
    def test_corrupt_trial_falls_back_to_confirmed_slot(self):
        state=dict(version=1,active='A',pending='B',tries=3)
        with patch.object(early,'discover',return_value={1:'control'}), patch.object(early,'mounted'), patch.object(early,'read',return_value=state), patch.object(early,'atomic') as save, patch.object(early,'prepare',side_effect=[ValueError('wrong kernel'),None]) as prepare, patch.object(early,'unmount_slot') as cleanup, patch.object(early,'run'), patch.object(early.Path,'exists',return_value=False):
            self.assertTrue(early.select({}))
            self.assertEqual([c.args[2] for c in prepare.call_args_list],['B','A'])
            self.assertEqual(save.call_args_list[-1].args[1]['attempt'],'A')
            cleanup.assert_called_once()
    def test_no_card_reaches_recovery_without_mounting(self):
        with patch.object(early,'discover',return_value=None), patch.object(early.time,'monotonic',side_effect=[0,120]), patch.object(early.time,'sleep'), patch.object(early.Path,'exists',return_value=False), patch.object(early,'mounted') as mount:
            self.assertFalse(early.select({}))
            mount.assert_not_called()
    def test_delayed_card_is_accepted(self):
        with patch.object(early,'discover',side_effect=[None,None,{1:'control'}]), patch.object(early.time,'sleep') as sleep, patch.object(early,'mounted'), patch.object(early,'read',return_value=dict(version=1,active='A',pending=None,tries=0)), patch.object(early,'atomic'), patch.object(early,'prepare'), patch.object(early,'run'), patch.object(early.Path,'exists',return_value=False):
            self.assertTrue(early.select({}))
            self.assertEqual(sleep.call_count,2)
