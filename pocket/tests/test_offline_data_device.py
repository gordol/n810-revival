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
 def test_native_picker_fills_plan_bounds_and_cancel_preserves_them(self):
  from native_navigation import native_key,native_pointer
  form=m.OfflineData();form.width,form.height=40,20
  def tap(x,y):
   self.assertTrue(native_pointer(form,x,y,40,0,False))
   native_pointer(form,x,y,40,0,True)
  tap(4,next(i for i,line in enumerate(form.lines()) if 'Choose area on world map' in line))
  form.lines()
  self.assertIsNotNone(form.layer())
  tap(2,0)
  for ch in 'Seattle':native_key(form,ch)
  self.assertIn('Seattle',form.lines()[2])
  tap(2,2)
  form.lines()
  tap(21,0)
  tap(15,9);tap(23,12)
  self.assertTrue(form.picker.bounds)
  tap(29,0)
  self.assertIsNone(form.layer())
  bounds=form.bbox.text
  w,s,e,n=map(float,bounds.split())
  self.assertTrue(-123<w<e<-122 and 47<s<n<48)
  with tempfile.TemporaryDirectory() as directory:
   self.assertIn('estimated_raw_bytes',m.prepare('plan',bounds,'',directory,'30'))
  form.key('pick');form.lines();tap(37,0)
  self.assertEqual(form.bbox.text,bounds)
 def test_plan_tap_shows_estimate_or_actionable_error_in_short_window(self):
  from native_navigation import native_pointer
  form=m.OfflineData();self.addCleanup(form.close)
  form.width,form.height=40,12
  with tempfile.TemporaryDirectory() as directory:
   form.output.text=directory
   for bounds,expected in (('', 'Enter west south east north bounds'),('1 1 2 2','matching OSM PBF'),('1 1 1.01 1.01','Download and build')):
    form.bbox.text=bounds
    row=next(i for i,line in enumerate(form.lines()) if 'Plan / reuse' in line)
    self.assertTrue(native_pointer(form,3,row,40))
    from concurrent.futures import wait
    wait([form.pending],timeout=5)
    self.assertTrue(form.poll())
    lines=form.lines()
    self.assertIn(expected,' '.join(lines))
    if bounds:self.assertIn('New raw elevation',' '.join(lines))
    native_pointer(form,3,1,40)
    self.assertFalse(form.plan_page)
   self.assertEqual(list(Path(directory).iterdir()),[])
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
