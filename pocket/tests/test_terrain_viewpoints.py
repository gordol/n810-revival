# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Saved terrain cameras stay discoverable from the ground-level demo."""
import importlib.util
from pathlib import Path
import sys,unittest,tempfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'shell'))
from core import Host,Window

class ViewpointTests(unittest.TestCase):
 def test_walk_opens_existing_overview_without_losing_position(self):
  path=ROOT/'shell/apps/surface-renderer/registration.py'
  spec=importlib.util.spec_from_file_location('terrain_view_registration',path)
  registration=importlib.util.module_from_spec(spec);spec.loader.exec_module(registration)
  host=Host(100,36,[Window('Rainier walk',0,0,90,32),Window('Scenery',0,0,90,32,opened=False,visible=False)])
  host.activate('Rainier walk');app=registration.create_outdoors(host)
  try:
   app.x,app.z,app.yaw=3.,4.,.5
   app.held_motion.event('w','press',app.clock())
   self.assertTrue(app.key('o'))
   self.assertEqual(host.focus,'Scenery')
   self.assertTrue(host.window('Scenery').opened)
   self.assertFalse(app.held_motion.held)
   host.activate('Rainier walk')
   self.assertEqual((app.x,app.z,app.yaw),(3.,4.,.5))
   self.assertIn('wide',str(app.help))
  finally:app.close()
 def test_missing_grid_offers_download_then_runs_walk(self):
  import os
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   with patch.dict(os.environ,POCKET_DATA_ROOT=str(root/'data'),XDG_DATA_HOME=str(root/'user')):
    path=ROOT/'shell/apps/surface-renderer/registration.py'
    spec=importlib.util.spec_from_file_location('walk_data_test',path)
    registration=importlib.util.module_from_spec(spec);spec.loader.exec_module(registration)
    host=Host(50,20,[Window('Rainier walk',0,0,44,18)])
    host.activate('Rainier walk')
    app=registration.create_outdoors(host)
    try:
     self.assertTrue(app.needs_grid)
     self.assertIn('Download Rainier',str(app.lines()))
     with patch('rainier_data.download') as fetch:
      self.assertTrue(app.pointer(4,2,40))
      app.download_job.result(timeout=20)
      app.poll()
     fetch.assert_called_once_with()
     self.assertFalse(app.needs_grid)
     self.assertTrue(app.pointer(20,4,40))
     self.assertGreater(app.z,0)
    finally:app.close()
 def test_overview_exposes_the_original_saved_cameras(self):
  from scenery import PRESETS,presets
  self.assertEqual(PRESETS,('original','wide','elevated','valley'))
  for name in PRESETS[1:]:self.assertIn('camera',presets()[name])

if __name__=='__main__':unittest.main()
