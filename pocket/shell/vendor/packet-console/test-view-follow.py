"""Actual APRS State ingestion, follow camera and reported trail overlays."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('follow_view',Path(__file__).with_name('n810-aprs-view.py'))
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
class Tests(unittest.TestCase):
 def state(self):
  s=v.State();s.map_engine_name='next';s.center=[47,-122];s.auto_fit=False;s.terrain=True;s.map_target=None
  return s
 def test_follow_received_call_then_new_positions_pause_and_resume(self):
  s=self.state();first=s.add('12:00:00 N0CALL-7>APRS ctl=03 pid=f0 !4710.00N/12231.00W>walking')
  v.toggle_station_follow(s);v.apply_station_follow(s)
  self.assertEqual(s.tracks.call,'N0CALL-7');self.assertEqual(s.center,list(v.packet_position(first)))
  next=s.add('12:01:00 N0CALL-7>APRS ctl=03 pid=f0 !4720.00N/12221.00W>moving')
  v.apply_station_follow(s);self.assertEqual(s.center,list(v.packet_position(next)))
  s.tracks.pause();s.center=[46,-121]
  s.add('12:02:00 N0CALL-7>APRS ctl=03 pid=f0 !4730.00N/12211.00W>moving')
  v.apply_station_follow(s);self.assertEqual(s.center,[46,-121])
  self.assertEqual(len(s.tracks.points()),3)
  v.toggle_station_follow(s);v.apply_station_follow(s)
  self.assertFalse(s.tracks.paused);self.assertNotEqual(s.center,[46,-121])
  self.assertIn('age unknown',v.follow_caption(s));self.assertTrue(s.terrain)
  v.toggle_station_follow(s);self.assertIsNone(s.tracks.call)
 def test_track_points_render_without_invented_relay_path(self):
  s=self.state();s.atlas=SimpleNamespace(places=lambda view:())
  s.tracks.follow('N0CALL-7')
  for lat,lon in ((48,-123),(47,-122),(46,-121)):s.tracks.add('N0CALL-7',lat,lon)
  viewport=SimpleNamespace(project=lambda lon,lat:((lon+124)*10,(49-lat)*10))
  with patch.object(v,'ink',side_effect=lambda n:n<<8):cells=v.map_overlays(s,320,80,40,viewport)
  for xy in ((10,10),(20,20),(30,30)):self.assertEqual(cells[xy][0],':')
  self.assertFalse(any(char=='·' for char,attr in cells.values()))
 def test_unknown_follow_and_explicit_directory_target_do_not_fight(self):
  s=self.state();s.tracks.follow('N0CALL-7');old=list(s.center)
  v.apply_station_follow(s);self.assertEqual(s.center,old)
  self.assertIn('position unknown',v.follow_caption(s))
  s.tracks.add('N0CALL-7',48,-123)
  # A Directory navigation action pauses camera following, rather than snapping back.
  v.activate_external_target(s,dict(call='OTHER',source='directory'))
  self.assertTrue(s.tracks.paused);v.apply_station_follow(s);self.assertEqual(s.center,old)
  v.toggle_station_follow(s)
  self.assertEqual(s.tracks.call,'OTHER');self.assertIsNone(s.map_target)
if __name__=='__main__':unittest.main()
