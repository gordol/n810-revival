import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('reads',Path(__file__).with_name('n810-radio-read-request.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def make(self):return m.ReadRequest('test',started_at=100,now=0,owner_idle=True)
 def test_serial_reads_and_actual_observations(self):
  r=self.make()
  for n,(cmd,payload) in enumerate(m.READS):
   self.assertEqual(r.next(n),(cmd,payload));self.assertIsNone(r.next(n))
   self.assertFalse(r.reply(999,{},observed_at=101+n))
   self.assertTrue(r.reply(cmd,{'value':n},observed_at=101+n))
  self.assertEqual(r.snapshot()['state'],'complete');self.assertIsNone(r.next(10))
  self.assertEqual(r.snapshot()['results']['20']['observed_at'],101)
 def test_busy_timeout_cancel_and_no_late_completion(self):
  with self.assertRaises(ValueError):m.ReadRequest('x',started_at=0,now=0,owner_idle=False)
  r=self.make();r.next(0);self.assertIsNone(r.next(5));self.assertEqual(r.state,'failed')
  self.assertFalse(r.reply(20,{},observed_at=200))
  r=self.make();r.next(0);r.cancel();self.assertIsNone(r.next(1));self.assertFalse(r.reply(20,{},observed_at=201))
 def test_snapshots_do_not_mutate_owner_results(self):
  r=self.make();r.next(0);data={'v':[]};r.reply(20,data,observed_at=100);data['v'].append(1)
  s=r.snapshot();s['results']['20']['decoded']['v'].append(2)
  self.assertEqual(r.snapshot()['results']['20']['decoded']['v'],[])
if __name__=='__main__':unittest.main()
