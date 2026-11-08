"""The GUI dispatcher scopes pointer capture to a clicked game viewport."""
import ast,ctypes as C,sys,time,unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'graphics'),str(ROOT/'shell')]
node=next(n for n in ast.parse((ROOT/'graphics/run.py').read_text()).body if isinstance(n,ast.ClassDef) and n.name=='DesktopWindow')
class Base:
 captured=False
 def capture(self,value):self.captured=value
class Events:
 def __init__(self):self.queue=[]
 def pocket_window_event(self,raw):
  if not self.queue:return 0
  for i,value in enumerate(self.queue.pop(0)):raw[i]=value
  return 1
scope={'Window':Base,'C':C,'time':time};exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'run.py','exec'),scope)
class GameMouse(unittest.TestCase):
 def setUp(self):
  self.active=True;self.motion=[];self.buttons=[];self.releases=[]
  self.app=SimpleNamespace(input_role='game',name='Doom',_active=lambda:self.active,pointer_motion=lambda *v:self.motion.append(v),pointer_button=lambda *v:self.buttons.append(v),release_pointer=lambda:self.releases.append(True))
  self.window=scope['DesktopWindow']();self.window.lib=Events()
  host=SimpleNamespace(origin=(0,0),window=lambda name:name,bounds=lambda w:(0,0,100,30))
  self.window.platform=SimpleNamespace(pixel_apps=[self.app],host=host)
 def event(self,*raw):
  self.window.lib.queue.append(raw);return list(self.window.events())
 def test_capture_motion_fire_and_escape_stays_in_app(self):
  self.assertFalse(self.window.captured)
  self.assertEqual(self.event(2,400,240,0,0,0),[]);self.assertTrue(self.window.captured)
  self.event(5,17,-9,0,0,0);self.assertEqual(self.motion,[(17,-9)])
  self.event(2,400,240,0,0,0);self.event(2,400,240,0,1,0)
  self.assertEqual(self.buttons,[(0,False),(0,True)])
  self.assertEqual(self.event(3,27,0,0,0,0),[]);self.assertFalse(self.window.captured);self.assertTrue(self.releases)
  self.assertEqual(self.event(3,27,0,0,0,0),[dict(action='key',key='\x1b',released=False)])
 def test_switch_and_native_focus_loss_release_even_without_motion(self):
  self.event(2,400,240,0,0,0);self.active=False
  list(self.window.events());self.assertFalse(self.window.captured)
  self.active=True;self.event(2,400,240,0,0,0)
  self.assertEqual(self.event(6,0,0,0,0,0),[dict(action='cancel-input')]);self.assertFalse(self.window.captured)
 def test_desktop_and_window_chrome_do_not_capture(self):
  self.event(2,0,0,0,0,0);self.assertFalse(self.window.captured)
  self.active=False;events=self.event(2,400,240,0,0,0)
  self.assertEqual(events[0]['action'],'pointer');self.assertFalse(self.window.captured)
if __name__=='__main__':unittest.main()
