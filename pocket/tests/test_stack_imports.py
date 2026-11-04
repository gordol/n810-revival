"""Unused upstream transports defer execution while normal imports still work."""
from pathlib import Path
import os,subprocess,sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum'

class StackImports(unittest.TestCase):
 def test_management_owner_does_not_construct_radio_data_plane(self):
  script="""import sys,tempfile
sys.path.insert(0,sys.argv[1])
from session_owner import SessionOwner
with tempfile.TemporaryDirectory() as state:
 owner=SessionOwner(state,'fixture','radio','usb','/dev/null',2,2)
 try:
  assert owner.snapshot()['radio_state']=='idle'
  assert owner.data_bridge is None
  assert not {'RNS','LXMF','data_bridge','service_bridge'} & set(sys.modules)
 finally:owner.close()
"""
  result=subprocess.run([sys.executable,'-c',script,str(ROOT)],capture_output=True,text=True,timeout=15)
  self.assertEqual(result.returncode,0,result.stderr)
 def test_local_transport_import_keeps_native_socket_path(self):
  script="""import sys
sys.path.insert(0,sys.argv[1])
from provider import Provider
from local_owner import ManagedOwner
from pathlib import Path
sys.path.insert(0,str(Path(sys.argv[1]).parents[3]))
import core,touch_process,radio_read_client,desktop_control,feed_control_client,scene_acceleration
scene_acceleration.configure()
assert 'zipfile' not in sys.modules
assert 'socket' not in sys.modules
"""
  result=subprocess.run([sys.executable,'-c',script,str(ROOT)],capture_output=True,text=True,timeout=15)
  self.assertEqual(result.returncode,0,result.stderr)
 def test_protocol_client_import_does_not_load_server_machinery(self):
  script="""import sys
sys.path.insert(0,sys.argv[1])
from owner import ServiceOwner,exchange,private_lock
owner=ServiceOwner(None,'fixture');owner.post({'ready':True});owner.drain()
assert owner.revision==1
assert not {'threading','concurrent.futures','contacts','local_owner','argparse'} & set(sys.modules)
"""
  result=subprocess.run([sys.executable,'-c',script,str(ROOT)],capture_output=True,text=True,timeout=15)
  self.assertEqual(result.returncode,0,result.stderr)
 def run_case(self,fail=False):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);interfaces=root/'RNS/Interfaces';interfaces.mkdir(parents=True)
   (root/'LXMF').mkdir();(root/'LXMF/__init__.py').write_text('')
   (root/'RNS/__init__.py').write_text('from .Interfaces import *\n'+("raise RuntimeError('fixture failure')\n" if fail else ''))
   (interfaces/'__init__.py').write_text("__all__=['Interface','UDPInterface']\n")
   (interfaces/'Interface.py').write_text('class Interface: pass\n')
   marker=root/'executed'
   (interfaces/'UDPInterface.py').write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("loaded")\nclass UDPInterface: pass\n')
   script='''import sys
from pathlib import Path
sys.path[:0]=[sys.argv[1],sys.argv[2]]
from lxmf_owner import load_stack
before=list(sys.meta_path)
if sys.argv[3]=='fail':
 try:load_stack()
 except RuntimeError:pass
 else:raise AssertionError('failure disappeared')
else:
 RNS,LXMF=load_stack()
 assert not (Path(sys.argv[1])/'executed').exists()
 from RNS.Interfaces.UDPInterface import UDPInterface
 assert UDPInterface.__name__=='UDPInterface'
 assert (Path(sys.argv[1])/'executed').exists()
assert sys.meta_path==before
'''
   result=subprocess.run([sys.executable,'-c',script,str(root),str(ROOT),'fail' if fail else 'ok'],capture_output=True,text=True,timeout=15)
   self.assertEqual(result.returncode,0,result.stderr)
 def test_unused_interface_executes_only_when_selected(self):self.run_case()
 def test_import_failure_restores_import_hooks(self):self.run_case(True)

if __name__=='__main__':unittest.main()
