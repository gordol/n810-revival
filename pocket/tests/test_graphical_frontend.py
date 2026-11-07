"""The graphical executable owns pixels; it never starts the terminal UI."""
from pathlib import Path
import json,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]
class GraphicalFrontend(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if not (ROOT/'build/graphics/frontend.json').exists():raise unittest.SkipTest('run make graphics-native first')
 def run_frontend(self,*args):
  return subprocess.run([sys.executable,str(ROOT/'graphics/launch.py'),*map(str,args)],capture_output=True,timeout=45)
 def test_independent_pixel_frame_and_no_terminal_output(self):
  with tempfile.TemporaryDirectory() as d:
   output=Path(d)/'frame';r=self.run_frontend('--once','--output',output)
   self.assertEqual(r.returncode,0,r.stderr.decode());self.assertEqual(r.stdout,b'')
   meta=json.loads(r.stderr);self.assertEqual(meta['frontend'],'pixels');self.assertFalse(meta['gpu'])
   raw=output.read_bytes();self.assertEqual(len(raw),800*480*2);self.assertGreater(len(set(raw)),8)
 def test_shared_window_actions_and_surface_room(self):
  with tempfile.TemporaryDirectory() as d:
   d=Path(d);actions=d/'actions';output=d/'frames'
   events=[dict(action='pointer',button=0,x=64,y=48),dict(action='pointer',button=32,x=96,y=80),dict(action='pointer',button=0,x=96,y=80,released=True),dict(action='open',app='surface-room'),dict(action='quit')]
   actions.write_text(''.join(json.dumps(e)+'\n' for e in events))
   r=self.run_frontend('--actions',actions,'--output',output)
   self.assertEqual(r.returncode,0,r.stderr.decode());self.assertEqual(r.stdout,b'')
   raw=output.read_bytes();self.assertEqual(len(raw)%768000,0);self.assertGreaterEqual(len(raw),3*768000)
   self.assertNotEqual(raw[:768000],raw[-768000:])
 def test_stylus_launch_uses_existing_window_action(self):
  with tempfile.TemporaryDirectory() as d:
   actions=Path(d)/'actions';output=Path(d)/'frames'
   actions.write_text('{"action":"pointer","button":0,"x":48,"y":112}\n{"action":"quit"}\n')
   r=self.run_frontend('--actions',actions,'--output',output)
   self.assertEqual(r.returncode,0,r.stderr.decode());self.assertEqual(r.stdout,b'')
   raw=output.read_bytes();self.assertEqual(len(raw),2*768000);self.assertNotEqual(raw[:768000],raw[768000:])
 def test_attach_preserves_existing_desktop_model(self):
  sys.path.insert(0,str(ROOT/'graphics'))
  import importlib.util
  spec=importlib.util.spec_from_file_location("test_pixel_desktop",ROOT/"graphics/desktop.py")
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  Desktop=module.Desktop
  from core import Host,Window
  config=json.loads((ROOT/'build/graphics/frontend.json').read_text())
  host=Host(100,30,[Window('Existing app',2,2,30,8,lines=('existing model',))],animate=False)
  host.background_enabled=False;host.show_clock=False;host.show_connectivity=False
  self.assertTrue(host.enable_native(config['native_library']))
  registry=object();host.app_registry=registry
  app=Desktop.from_host(host,config['font'],config['renderer_library'],backend='native')
  try:
   self.assertIs(app.host,host);self.assertIs(host.app_registry,registry)
   self.assertEqual([w.name for w in host.windows],['Existing app'])
   frame=app.render();self.assertIsInstance(frame,bytearray);self.assertEqual(len(frame),768000)
  finally:app.close()
 def test_native_presenter_borrows_mutable_frame_storage(self):
  import ctypes as C,types
  sys.path.insert(0,str(ROOT/'graphics'))
  from window import Window
  frame=bytearray(768000);view=(C.c_ubyte*len(frame)).from_buffer(frame);seen=[]
  callback=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p)(lambda handle,address:seen.append(address) or 0)
  window=Window.__new__(Window);window.handle=1;window.lib=types.SimpleNamespace(pocket_window_present=callback)
  window.present(frame);window.present(memoryview(frame))
  self.assertEqual(seen,[C.addressof(view)]*2)
 def test_invalid_input_fails_without_terminal_side_effects(self):
  with tempfile.TemporaryDirectory() as d:
   actions=Path(d)/'actions';actions.write_text('{"action":"pointer","button":0,"x":-1,"y":0}\n')
   r=self.run_frontend('--actions',actions,'--output',Path(d)/'frame')
   self.assertNotEqual(r.returncode,0);self.assertEqual(r.stdout,b'');self.assertIn(b'Pointer outside',r.stderr)
if __name__=='__main__':unittest.main()
