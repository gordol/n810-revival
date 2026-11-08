import importlib.util,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('history',Path(__file__).with_name('n810-walk-history.py'));h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)

class Tests(unittest.TestCase):
 def test_restore_groups_restart_but_not_transmission_state(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);position={'lat':5.56555,'lon':5.58555,'time':1234,'accuracy':10}
   for tag,start in (('a','08:00:00'),('b','08:10:00')):
    stamp='2026-10-15T'+start+'-07:00'
    rows=[dict(type='session',time=stamp,callsign='N0CALL',tag=tag),dict(type='position',time=stamp,position=position),dict(type='armed',time=stamp),dict(type='submission',time=stamp,probe={'number':1,'position':position,'payload':'hello '+tag,'status':'Submitted'})]
    (root/(tag+'.jsonl')).write_text('\n'.join(json.dumps(r) for r in rows)+'\n{broken tail')
   report={'packet':'N0CALL>APN810,WIDE1-1,qAR,VCAPK:hello a','provenance':'user_provided'}
   (root/'internet-reports.jsonl').write_text(json.dumps(report)+'\n')
   walks=h.load(root,'N0CALL');self.assertEqual(len(walks),1)
   self.assertEqual(len(walks[0]['track']),2);self.assertEqual(len(walks[0]['probes']),2)
   self.assertEqual(walks[0]['probes'][0]['internet_reports'][0]['gate'],'VCAPK')
   self.assertEqual(walks[0]['probes'][0]['internet_reports'][0]['provenance'],'user_provided')
   self.assertNotIn('armed',walks[0]);self.assertNotIn('pending',walks[0])
   self.assertEqual(h.load(root,'OTHER'),[])
 def test_live_plan_not_restored_from_archive(self):
  spec=importlib.util.spec_from_file_location('walk',Path(__file__).with_name('n810-aprs-walk.py'));w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
  import argparse
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);pos={'lat':5.56555,'lon':5.58555,'time':1234,'accuracy':10}
   rows=[dict(type='session',callsign='N0CALL',time='2026-10-15T08:00:00-07:00'),dict(type='position',position=pos,time='2026-10-15T08:01:00-07:00'),dict(type='submission',probe={'number':1,'position':pos,'payload':'test'})]
   (root/'old.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
   app=w.Walk(argparse.Namespace(callsign='N0CALL',budget=20,logs=d))
   self.assertTrue(app.view_history);self.assertFalse(app.plan.armed);self.assertEqual(app.plan.count,0);self.assertIsNone(app.plan.pending)
   app.key(ord('h'));self.assertFalse(app.view_history);self.assertFalse(app.plan.armed);app.log.close()
if __name__=='__main__':unittest.main()
