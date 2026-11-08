"""Nokia pixels reuse selector input and do not poll idle or own the display stack."""
from pathlib import Path
import ast,importlib.util,sys,unittest
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'graphics'));sys.path.insert(0,str(ROOT/'shell'))
spec=importlib.util.spec_from_file_location('test_nokia_pixels',ROOT/'graphics/nokia.py')
nokia=importlib.util.module_from_spec(spec);spec.loader.exec_module(nokia)
class NokiaGraphics(unittest.TestCase):
 def platform(self,**kwargs):return nokia.NokiaPlatform('font','renderer',None,**kwargs)
 def test_idle_uses_model_deadline_without_polling(self):
  p=self.platform();self.assertIsNone(p.wait_timeout(None));self.assertEqual(p.wait_timeout(12),12)
 def test_bounded_check_deadline_starts_after_initialization(self):
  p=self.platform(seconds=5)
  with patch.object(nokia.time,'monotonic',return_value=100):p.events()
  self.assertEqual(p.deadline,105)
  with patch.object(nokia.time,'monotonic',return_value=102):
   self.assertEqual(p.wait_timeout(None),3);self.assertEqual(p.wait_timeout(1),1)
  with patch.object(nokia.time,'monotonic',return_value=105):p.events()
  self.assertTrue(p.closed)
 def test_pending_scripted_actions_do_not_block(self):
  p=self.platform(actions=[{'key':'\x1b'}]);self.assertEqual(p.wait_timeout(None),0)
 def test_signal_stop_wakes_the_desktop_selector(self):
  tree=ast.parse((ROOT/'graphics/nokia.py').read_text())
  main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
  stop=next(n for n in main.body if isinstance(n,ast.FunctionDef) and n.name=='stop')
  platform=SimpleNamespace(closed=False);wakes=[]
  signals=SimpleNamespace(SIGTERM=15,getsignal=lambda sig:lambda *event:wakes.append(event))
  scope=dict(platform=platform,signal=signals)
  exec(compile(ast.fix_missing_locations(ast.Module(body=[stop],type_ignores=[])),'nokia.py','exec'),scope)
  scope['stop'](2,None);self.assertTrue(platform.closed);self.assertEqual(wakes,[(2,None)])
  signals.getsignal=lambda sig:scope['stop']
  scope['stop'](15,None);self.assertEqual(len(wakes),1)
 def test_vt_input_is_explicit_and_uses_existing_dispatch(self):
  self.assertTrue(nokia.NokiaPlatform.terminal_input)
  text=(ROOT/'shell/desktop.py').read_text()
  self.assertIn("platform is None or getattr(platform,'terminal_input',False):selector.register(sys.stdin",text)
if __name__=='__main__':unittest.main()
