"""The fixed helper fast path never opens a radio or alters an existing mapping."""
import importlib.util,io,os,stat,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('fast_spp',Path(__file__).resolve().parents[1]/'platform/n810/rnode_spp_prepare.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
BOND='[General]\nServices=00001101-0000-1000-8000-00805f9b34fb;\n[LinkKey]\nKey='+'A'*32+'\n'

class FastPrepareTests(unittest.TestCase):
 def test_bond_requires_unambiguous_classic_key_and_serial_service(self):
  self.assertTrue(helper._bonded_spp(BOND))
  for value in (BOND.replace('A'*32,'invalid'),BOND.replace('00001101','00001102'),BOND+'Key='+'B'*32+'\n'):
   self.assertFalse(helper._bonded_spp(value))
 def check(self,busy=False,wrong_mapping=False,changed=False):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root);(root/'bond').write_text(BOND);(root/'lock').touch()
   open_fd=os.open;opened=[]
   def redirect(path,flags,*args):
    opened.append(path)
    return open_fd(root/('bond' if str(path).endswith('/info') else 'lock'),flags,*args)
   node=SimpleNamespace(st_mode=stat.S_IFCHR|0o660,st_uid=1000,st_gid=20,st_rdev=os.makedev(216,0),st_dev=1,st_ino=2)
   after=SimpleNamespace(**vars(node));after.st_ino+=int(changed)
   root_file=SimpleNamespace(st_mode=stat.S_IFREG|0o600,st_uid=0,st_nlink=1,st_size=len(BOND))
   def capture(args):
    if 'hciconfig' in args[0]:return 0,'BD Address: '+helper.CONTROLLER+'\nUP RUNNING\n'
    if 'rfcomm' in args[0]:return 0,'rfcomm0: '+helper.CONTROLLER+' -> '+('00:00:00:00:00:00' if wrong_mapping else helper.ADDRESS)+' channel 1 closed\n'
    return (0,'occupied') if busy else (1,'')
   with patch.object(helper.os,'geteuid',return_value=0),patch.object(helper.sys,'argv',['helper']),patch.object(helper.pwd,'getpwnam',return_value=SimpleNamespace(pw_uid=1000)),patch.object(helper.grp,'getgrnam',return_value=SimpleNamespace(gr_gid=20)),patch.object(helper.os,'stat',side_effect=[node,after]),patch.object(helper.os,'fstat',return_value=root_file),patch.object(helper.os,'open',side_effect=redirect),patch.object(helper.os,'listdir',return_value=[]),patch('builtins.open',return_value=io.StringIO('CapEff: 00080000\n')),patch.object(helper,'_capture',side_effect=capture),patch.object(helper.os,'chown') as chown:
    result=helper._existing_mapping_ready()
    chown.assert_not_called()
   self.assertNotIn(helper.DEVICE,opened)
   return result
 def test_unchanged_unused_mapping_is_ready_without_opening_device(self):self.assertTrue(self.check())
 def test_occupied_mapping_is_not_accepted(self):self.assertFalse(self.check(busy=True))
 def test_other_device_mapping_is_not_accepted(self):self.assertFalse(self.check(wrong_mapping=True))
 def test_replaced_device_node_is_not_accepted(self):self.assertFalse(self.check(changed=True))

if __name__=='__main__':unittest.main()
