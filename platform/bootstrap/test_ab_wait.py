"""Boot discovery tolerates delayed partitions and remains bounded without a card."""
import unittest
from unittest.mock import Mock,patch
import ab_runtime as runtime

class WaitForCard(unittest.TestCase):
    def run_wait(self,ready_at,held_at=None,timeout=5):
        clock=[0];checked=[]
        def device(config,part):
            checked.append((clock[0],part))
            return Mock(is_block_device=lambda:clock[0]>=ready_at.get(part,999))
        with patch.object(runtime,'device',side_effect=device), patch.object(runtime.time,'monotonic',side_effect=lambda:clock[0]), patch.object(runtime.time,'sleep',side_effect=lambda seconds:clock.__setitem__(0,clock[0]+seconds)), patch.object(runtime.Path,'exists',side_effect=lambda:held_at is not None and clock[0]>=held_at):
            result=runtime.wait_for_card({},timeout)
        return result,clock[0],checked
    def test_delayed_data_partition_waits_even_when_control_exists(self):
        result,elapsed,checked=self.run_wait({1:0,2:1,3:2,4:4})
        self.assertEqual((result,elapsed),('ready',4))
        self.assertIn((4,4),checked)
    def test_absent_or_incomplete_card_times_out(self):
        for parts in ({},{1:0,2:0,3:0}):
            result,elapsed,_=self.run_wait(parts)
            self.assertEqual((result,elapsed),('timeout',5))
    def test_local_recovery_request_interrupts_wait(self):
        result,elapsed,_=self.run_wait({},held_at=2)
        self.assertEqual((result,elapsed),('held',2))
    def test_ready_card_has_no_fixed_delay(self):
        result,elapsed,_=self.run_wait(dict.fromkeys((1,2,3,4),0))
        self.assertEqual((result,elapsed),('ready',0))
