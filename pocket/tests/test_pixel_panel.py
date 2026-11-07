"""The same panel model can emit structured text with identical hit targets."""
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from panel import Panels
class PixelPanel(unittest.TestCase):
 def test_structured_sink_keeps_hits_without_ansi(self):
  for dock in ('top','bottom','left','right'):
   a=Panels(dock);b=Panels(dock);a.layout(100,30);b.layout(100,30)
   widgets={'windows':[('Connections','Connections')],'clock':[('key:,','menu')],'apps':[('launch:window:Settings','Settings')]}
   text=a.render(widgets);runs=[]
   output=b.render(widgets,sink=lambda *run:runs.append(run))
   self.assertTrue(text);self.assertEqual(output,'');self.assertTrue(runs)
   self.assertEqual([p.hits for p in a.panels],[p.hits for p in b.panels])
   self.assertTrue(all('\x1b' not in run[2] for run in runs))
   runs.clear();self.assertEqual(b.render(widgets,sink=lambda *run:runs.append(run)),'');self.assertEqual(runs,[])
if __name__=='__main__':unittest.main()
