# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import sys,math,unittest,importlib.util
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from station_workspace import StationMap,Context
from offline_map import Image,ContextPlane,ScaledPlane
from map_overview import LocalOverview
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('interaction_map_engine',ROOT/'shell/vendor/packet-console/n810-map-next.py')
engine=importlib.util.module_from_spec(spec);spec.loader.exec_module(engine)

class InteractionTests(unittest.TestCase):
 def form(self):
  f=StationMap(Context(),ROOT/'shell/vendor/packet-console',lambda:None)
  self.addCleanup(f.renderer.close);self.addCleanup(f.close)
  f.width=120;f.height=43;f.center=(47.,-122.);f.span=20.
  f.renderer.module=engine
  view=engine.Viewport(f.center,f.span,120,40)
  image=Image(120,40,tuple((' ',0) for _ in range(4800)),'',(),0.,view)
  f._image=f._shown_image=image;f._image_view=(f.center,f.span);f._display_layer=f.station_layer(image)
  return f
 def test_drag_moves_map_with_hand_without_preview_box_or_overview(self):
  f=self.form();old=f.center
  f.pointer(35,15,120,0,False);f.pointer(41,21,120,32,False);f.pointer(41,21,120,0,True)
  self.assertGreater(f.center[0],old[0]);self.assertLess(f.center[1],old[1])
  self.assertIsNone(f.target_box.view);self.assertFalse(f.full_overview);self.assertEqual(f.span,20.)
  with patch.object(f.renderer,'frame',return_value=None),patch('repeater_catalog.load',return_value=()):f.lines()
  self.assertEqual(f._shown_image.source,'pan-preview')
  x,y=f._shown_image.projection.project(old[1],old[0])
  self.assertAlmostEqual(x,59.5+6,delta=.01);self.assertAlmostEqual(y,19.5+6,delta=.01)
  self.assertIsNone(f.target_box.view)
 def test_forest_toggle_rebuilds_display_image_even_if_frame_identity_repeats(self):
  f=self.form();image=f._image
  f._display_key=(id(image),f.width,f.height-3)
  f.key('z')
  self.assertIsNone(f._display_image)
  with patch.object(f.renderer,'frame',return_value=image),patch('repeater_catalog.load',return_value=()):
   f.lines()
  self.assertIsNotNone(f._display_image)

 def test_repeated_forest_key_survives_pending_and_reused_frames_in_terrain_map(self):
  from station_map_tools import StationMapTools
  f=self.form();image=f._image;owner=StationMapTools(f)
  owner.terrain_active=True;owner.ensure_tool();owner.tool.screen='map'
  calls=[0]
  def frame(*args):
   calls[0]+=1
   return image if calls[0]%3==0 else None
  with patch.object(f.renderer,'frame',side_effect=frame),patch('repeater_catalog.load',return_value=()):
   for _ in range(39):owner.key('z');owner.lines()
  self.assertEqual(calls[0],39)
  self.assertIsNotNone(f._display_image)

 def test_auto_grid_stays_clear_at_wide_zoom_but_manual_grid_remains_available(self):
  f=self.form();plain=f._display_layer
  f._shown_image=Image(120,40,plain[4].base,'',(),0.,engine.Viewport(f.center,52.,120,40))
  self.assertIs(f.layer(),plain)
  f.maidenhead_grid='on'
  self.assertIsNot(f.layer(),plain)

 def test_explicit_overview_camera_stays_fixed_during_box_zoom_and_drag(self):
  f=self.form();f.key('o');camera=f._overview_camera
  view=engine.Viewport(*camera,120,40)
  f._shown_image=Image(120,40,tuple((' ',0) for _ in range(4800)),'',(),0.,view,'cached-overview')
  for _ in range(10):f.key('-')
  self.assertEqual(f._overview_camera,camera)
  f.zoom_at_pointer(60,22,120,out=False);self.assertEqual(f._overview_camera,camera)
  f.target_box.choose(f.center,20.)
  f.overview_pointer(60,22,120,0,False);f.overview_pointer(60,27,120,32,False);f.overview_pointer(60,27,120,0,True)
  self.assertLess(f.target_box.view[0][0],f.center[0]);self.assertEqual(f._overview_camera,camera)
  self.assertIsNone(f._zoom_context_view)
 def test_native_wrapper_arrows_move_zoom_box_even_with_sidebar_open(self):
  from station_map_tools import StationMapTools
  from native_navigation import native_key,navigation
  for overview in (False,True):
   f=self.form();wrapped=StationMapTools(f)
   f.side_overview=True;wrapped.layers_visible=True
   wrapped.sidebar_scroll=3
   if overview:f.open_overview()
   with patch.object(f,'preview_zoom'):
    native_key(wrapped,'-');before=f.target_box.view
    self.assertEqual(navigation(wrapped).current().kind,'map')
    native_key(wrapped,'up');self.assertGreater(f.target_box.view[0][0],before[0][0])
    native_key(wrapped,'down');self.assertAlmostEqual(f.target_box.view[0][0],before[0][0])
    native_key(wrapped,'right');self.assertGreater(f.target_box.view[0][1],before[0][1])
    self.assertEqual(wrapped.sidebar_scroll,3)
    self.assertEqual(f.center,(47.,-122.));self.assertEqual(f.span,20.)
    f.side_overview=False;wrapped.layers_visible=False
    native_key(wrapped,'\x1b');self.assertIsNone(f.target_box.view)
    self.assertFalse(f.full_overview)
 def test_normal_desktop_overview_requests_one_full_resolution_image(self):
  image=object();calls=[]
  renderer=SimpleNamespace(context_frame=lambda *args:calls.append(args) or image)
  local=LocalOverview(renderer)
  with patch('desktop_elevation.enabled',return_value=True):
   self.assertIs(local.image(engine,243,61,(47.,-122.),160),image)
   self.assertIs(local.image(engine,243,61,(47.,-122.),160),image)
  self.assertEqual(len(calls),1);self.assertEqual(calls[0][-2:],(243,61))
 def test_leaving_zoom_context_scrolls_retained_pixels_without_scale_reset(self):
  f=self.form();view=engine.Viewport(f.center,50.,120,40)
  image=Image(120,40,tuple((' ',0) for _ in range(4800)),'retained',(),0.,view)
  f._zoom_context_image=image;f.target_box.choose((47.,-121.5),20.)
  with patch('map_overview.zoom_context',side_effect=AssertionError('Regional fallback during pan')):
   f.preview_zoom()
  self.assertEqual(f._zoom_context_view,((47.,-121.5),50.))
  self.assertEqual(f._zoom_context_image.source,'pan-preview')
  self.assertEqual(f._zoom_context_image.projection.span,50.)
 def test_scaled_planes_are_bounded_and_reuse_color_conversion(self):
  from paint import ink
  base=tuple(('▀',ink(60,70,80,background=(20,30,40))) for _ in range(4))
  for cls in (ScaledPlane,ContextPlane):
   plane=cls(base,2,2,4,4);self.assertEqual(len(tuple(plane)),16)
   with self.assertRaises(IndexError):plane[16]
  plane=ContextPlane(base,2,2,4,4)
  with patch('offline_map.ink',wraps=ink) as convert:
   self.assertEqual(plane[3],plane[3]);self.assertEqual(convert.call_count,1)
if __name__=='__main__':unittest.main()
