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
     self.assertEqual(app.z,0)
     self.assertTrue(app.pointer(20,4,40,released=True))
     self.assertGreater(app.z,0)
    finally:app.close()
 def test_drag_steers_continuously_and_releases_outside(self):
  from types import SimpleNamespace
  path=ROOT/'shell/apps/surface-renderer/registration.py'
  spec=importlib.util.spec_from_file_location('rainier_drag_test',path)
  registration=importlib.util.module_from_spec(spec);spec.loader.exec_module(registration)
  host=Host(50,20,[Window('Rainier walk',0,0,44,18),Window('Scenery',0,0,44,18)])
  host.activate('Rainier walk')
  now=[1.]
  view=SimpleNamespace(poll=lambda owner:None,close=lambda:None,trail=SimpleNamespace(guiding=True))
  app=registration.create_outdoors(host,clock=lambda:now[0],pixel_scene=view)
  app.needs_grid=False
  try:
   view.world=True;view.album=[];view.notebook=None
   taps=[]
   view.scene_tap=lambda x,y,w,h:taps.append((x,y))
   sys.path.insert(0,str(ROOT/"graphics"))
   from rainier_hike import HangGlider
   view.glider=HangGlider(SimpleNamespace(x=0,z=0,heading=0),lambda x,z:4500,True)
   for use_mouse in (False,True):
    def event(x,y,button,released=False):
     if use_mouse:return app.pointer(x,y,42,button,released)
     return app.world_touch(1,x,y,42,15,button,released)
    self.assertTrue(event(12,8,0))
    self.assertTrue(event(14,7,32))
    self.assertTrue(all(0<value<1 for value in view.glider.drag))
    self.assertTrue(app.pointer_captured)
    app.advance_drag()
    self.assertIsNone(app.drag_start)
    self.assertTrue(event(14,7,0,True))
    self.assertFalse(app.pointer_captured)
    self.assertEqual(view.glider.drag,(0.,0.))
    self.assertEqual(taps,[])
   app.key_event('right','press',now[0])
   self.assertIn('right',view.glider.keys)
   app.key_event('right','release',now[0])
   self.assertFalse(view.glider.keys)
   view.glider=None
   view.ski=SimpleNamespace(steer=0.)
   app.world_touch(1,9,8,42,15,0,False)
   app.world_touch(1,17,8,42,15,32,False)
   self.assertGreater(view.ski.steer,.5)
   app.world_touch(2,36,12,42,15,0,False)
   app.world_touch(2,36,12,42,15,0,True)
   self.assertEqual(taps,[(36,12)])
   app.world_touch(1,17,8,42,15,0,True)
   self.assertEqual(view.ski.steer,0.)
   view.ski=None
   taps.clear()
   view.destination=(0.,20.)
   app.world_touch(1,9,8,42,15,0,False)
   app.world_touch(1,9.2,8.1,42,15,0,True)
   self.assertEqual(taps,[(9,8)])
   view.lens=True;view.zoom=2.
   yaw,pitch=app.yaw,app.pitch
   app.world_touch(1,10,5,42,15,0,False)
   app.world_touch(2,20,5,42,15,0,False)
   app.world_touch(2,30,5,42,15,32,False)
   self.assertEqual(view.zoom,4.)
   app.world_touch(1,10,5,42,15,0,True)
   app.world_touch(2,30,5,42,15,0,True)
   self.assertEqual((app.yaw,app.pitch),(yaw,pitch))
   self.assertEqual(taps,[(9,8)])
   view.lens=False
   pages=[]
   view.notebook=SimpleNamespace(turn_page=pages.append)
   app.pointer(32,7,42);app.pointer(9,7,42,32);app.pointer(9,7,42,released=True)
   self.assertEqual(pages,[1])
   view.notebook=None
   view.cruise=True;view.cruise_heading=None
   heading=app.yaw
   for start in (5,30):
    view.frame_camera=((app.x,1.25,app.z,app.yaw,app.pitch),1.4)
    app.world_touch(1,start,5,42,15,0,False)
    yaw,pitch=app.yaw,app.pitch
    app.world_touch(1,start+3,7,42,15,32,False)
    angles=app.yaw,app.pitch
    app.x+=3.;app.z+=7.
    app.world_touch(1,start+3,7,42,15,0,True)
    self.assertEqual((app.yaw,app.pitch),angles)
    self.assertEqual(view.cruise_heading,heading)
    self.assertLess(app.yaw,yaw);self.assertLess(app.pitch,pitch)
   view.frame_camera=None
   self.assertTrue(view.trail.free_look)
   self.assertEqual(view.destination,(0.,20.))
   self.assertEqual(taps,[(9,8)])
   app.x=app.z=app.yaw=0.
   app.pointer(3,4,42);app.pointer(8,8,42,32);app.pointer(8,8,42,released=True)
   self.assertLess(app.yaw,0);self.assertEqual(app.z,0)
   app.preferences_changed({'touch-controls':'Two thumbs'})
   app.yaw=0.
   app.world_touch(2,32,7,42,15,0,False)
   app.world_touch(1,10,8,42,15,0,False)
   app.world_touch(1,10,3,42,15,32,False)
   app.world_touch(2,36,7,42,15,32,False)
   now[0]+=.1;app.poll()
   self.assertGreater(app.z,0);self.assertGreater(app.yaw,0)
   app.world_touch(2,36,7,42,15,0,True)
   moving=app.z;now[0]+=.1;app.poll();self.assertGreater(app.z,moving)
   app.world_touch(1,10,3,42,15,0,True)
   app.x=app.z=app.yaw=0.
   app.pointer(18,9,42)
   app.pointer(27,3,42,32)
   now[0]+=.1;app.poll()
   self.assertGreater(app.z,0);self.assertGreater(app.yaw,0)
   self.assertFalse(view.trail.guiding)
   app.pointer(18,9,42,32);stopped=(app.x,app.z,app.yaw)
   now[0]+=.1;app.poll()
   self.assertEqual((app.x,app.z,app.yaw),stopped)
   app.pointer(-8,22,42,32);now[0]+=.1;app.poll()
   self.assertLess(app.z,stopped[1])
   app.pointer(-8,22,42,released=True)
   self.assertFalse(app.pointer_captured)
   stopped=(app.x,app.z,app.yaw);now[0]+=1;app.poll()
   self.assertEqual((app.x,app.z,app.yaw),stopped)
   app.pointer(20,9,42);app.pointer(20,3,42,32)
   host.activate('Scenery');app.on_focus()
   self.assertFalse(app.pointer_captured)
  finally:app.close()

 def test_walk_height_matches_drawn_triangle(self):
  sys.path.insert(0,str(ROOT/'graphics'))
  from rainier_pixels import surface
  from geometry import HeightField,Vec
  field=HeightField(2,2,Vec(0,0,0),1,1,(0,10,20,60))
  self.assertEqual(surface(field,.25,.25),7.5)
  self.assertEqual(surface(field,.75,.75),37.5)
  self.assertEqual(surface(field,.5,.5),15)

 def test_overview_exposes_the_original_saved_cameras(self):
  from scenery import PRESETS,presets
  self.assertEqual(PRESETS,('original','wide','elevated','valley'))
  for name in PRESETS[1:]:self.assertIn('camera',presets()[name])

if __name__=='__main__':unittest.main()
