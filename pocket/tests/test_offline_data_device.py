# SPDX-License-Identifier: GPL-2.0-or-later
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import native_data_setup as m
class DeviceDataTests(unittest.TestCase):
 def test_installed_app_offers_verification_instead_of_unavailable_build_tools(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m,'POCKET',Path(d)),patch.dict('os.environ',{'POCKET_DATA_ROOT':d}):
   form=m.OfflineData()
   self.assertEqual([t.key for t in form.navigation_targets()],['output','verify'])
   self.assertEqual(form.output.text,d)
   self.assertIn('installed maps',' '.join(form.lines()))
 def test_registered_app_session_contract_and_input_notification(self):
  from app_registry import LazyApplication
  from native_navigation import native_key
  form=m.OfflineData();events=[]
  wrapper=LazyApplication.__new__(LazyApplication);wrapper.owner=form;wrapper.saved=form.session_state();wrapper._session_callback=lambda:events.append(form.session_state())
  wrapper._bind_owner_session()
  native_key(form,'7')
  self.assertTrue(events);self.assertTrue(events[-1][form.field].endswith('7'))
 def test_source_checkout_keeps_build_actions(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'tools').mkdir(parents=True);(root/'tools/maps.py').touch()
   with patch.object(m,'POCKET',root):
    form=m.OfflineData();keys=[t.key for t in form.navigation_targets()]
    self.assertIn('plan',keys);self.assertIn('build',keys);self.assertNotIn('verify',keys)
 def test_picker_launch_failure_keeps_link_and_offers_retry_or_back(self):
  from native_navigation import native_pointer
  form=m.OfflineData();form.width,form.height=40,12
  with patch('area_picker.Picker') as factory:
   picker=factory.return_value
   picker.url='http://127.0.0.1:12345/test/'
   picker.launch.side_effect=FileNotFoundError()
   row=next(i for i,line in enumerate(form.lines()) if 'Choose area on world map' in line)
   self.assertTrue(native_pointer(form,5,row,40))
   self.assertIn(picker.url,' '.join(form.lines()))
   self.assertTrue(native_pointer(form,5,1,40))
   factory.assert_called_once()
   self.assertEqual(picker.launch.call_count,2)
   self.assertTrue(native_pointer(form,5,2,40))
   picker.close.assert_called_once()
   self.assertIsNone(form.picker)
 def test_phone_build_uses_local_guest_for_every_stage(self):
  import os
  with tempfile.TemporaryDirectory() as d, patch.dict(os.environ,POCKET_TERMUX='1'), patch('shutil.which',return_value='proot-distro'), patch('subprocess.Popen') as spawn:
   output=Path(d)/'offline maps'
   spawn.return_value.communicate.return_value=('ok','')
   spawn.return_value.returncode=0
   m.prepare('build','1 1 1.01 1.01','',str(output),'30')
   commands=[call.args[0] for call in spawn.call_args_list]
   self.assertEqual([cmd[-1] for cmd in commands[:-1]],['configure','download','build','elevation'])
   self.assertEqual(commands[-1][-1],'--plan')
   for cmd in commands[:-1]:
    self.assertEqual(cmd[:3],['proot-distro','login','pocket-maps'])
    self.assertIn(str(output),cmd[:cmd.index('--')])
    self.assertTrue(cmd[cmd.index('--source')+1].endswith('.osm'))
    self.assertEqual(cmd[cmd.index('--url')+1],'https://api.openstreetmap.org/api/0.6/map?bbox=1.0,1.0,1.01,1.01')
 def test_phone_plan_needs_no_guest_or_network(self):
  import os
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,POCKET_TERMUX='1'),patch('shutil.which',return_value=None):
   output=Path(d)/'area'
   self.assertIn('estimated_raw_bytes',m.prepare('plan','1 1 1.01 1.01','',str(output),'30'))
   self.assertFalse(output.exists())
   with self.assertRaisesRegex(ValueError,'mobile-map-deps'):
    m.prepare('build','1 1 1.01 1.01','',str(output),'30')
if __name__=='__main__':unittest.main()
