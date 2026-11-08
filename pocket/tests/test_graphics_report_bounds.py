"""Long GUI runs retain bounded recent frames and durable failure summaries."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'graphics'))
from full import Platform

class ReportBounds(unittest.TestCase):
 def test_default_does_not_collect_or_inspect_frame_history(self):
  p=Platform('unused','unused')
  p.record_frame() # No host/registry exists: disabled diagnostics must not inspect them.
  self.assertEqual(p.report,{})
 def test_long_run_preserves_early_menu_and_failure_without_unbounded_history(self):
  p=Platform('unused','unused',diagnostics=True)
  form=SimpleNamespace(error='early construction failure')
  p.registry=SimpleNamespace(forms={'Example':form});p.host=SimpleNamespace(focus='First app',launcher_lines=['menu'])
  p.frames=1;p.record_frame()
  form.error='';p.host.launcher_lines=[]
  for i in range(2,10001):
   p.frames=i;p.host.focus='window-'+str(i);p.record_frame()
  self.assertEqual(len(p.report['history']),128)
  self.assertEqual(p.report['history'][0]['frame'],9873)
  self.assertEqual(p.report['history'][-1]['frame'],10000)
  self.assertEqual(p.report['history_dropped'],9872)
  self.assertTrue(p.report['menu_opened'])
  self.assertEqual(p.report['errors'],{'Example':'early construction failure'})
  self.assertEqual(len(p.report['activity']),64)
  self.assertIn('First app',p.report['activity'])

if __name__=='__main__':unittest.main()
