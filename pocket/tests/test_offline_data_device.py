# SPDX-License-Identifier: GPL-2.0-or-later
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import native_data_setup as m
class DeviceDataTests(unittest.TestCase):
 def test_installed_app_offers_verification_instead_of_unavailable_build_tools(self):
  with tempfile.TemporaryDirectory() as d,patch.object(m,'REPOSITORY',Path(d)),patch.dict('os.environ',{'POCKET_DATA_ROOT':d}):
   form=m.OfflineData()
   self.assertEqual([t.key for t in form.navigation_targets()],['output','verify'])
   self.assertEqual(form.output.text,d)
   self.assertIn('installed maps',' '.join(form.lines()))
 def test_source_checkout_keeps_build_actions(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'pocket/tools').mkdir(parents=True);(root/'pocket/tools/maps.py').touch()
   with patch.object(m,'REPOSITORY',root):
    form=m.OfflineData();keys=[t.key for t in form.navigation_targets()]
    self.assertIn('plan',keys);self.assertIn('build',keys);self.assertNotIn('verify',keys)
if __name__=='__main__':unittest.main()
