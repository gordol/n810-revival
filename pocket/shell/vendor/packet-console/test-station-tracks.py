"""Bounded reported positions and callsign camera following; synthetic no-I/O."""
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('tracks_test',ROOT/'n810-station-tracks.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_exact_callsign_camera_pause_collect_resume_and_stop(self):
  t=m.Tracks();t.follow('N0CALL-7')
  self.assertIsNone(t.camera_position());self.assertEqual(t.freshness(100),'position unknown')
  t.add('N0CALL',47,-122,observed_at=100);self.assertIsNone(t.camera_position())
  t.add('N0CALL-7',47.1,-122.1,stamp='12:00:00',observed_at=100)
  self.assertEqual(t.camera_position(),(47.1,-122.1))
  t.pause();t.add('N0CALL-7',47.2,-122.2,observed_at=110)
  self.assertIsNone(t.camera_position());self.assertEqual(len(t.points()),2)
  t.resume();self.assertEqual(t.camera_position(),(47.2,-122.2))
  t.stop();self.assertIsNone(t.camera_position())
 def test_stationary_reports_do_not_invent_motion_and_legacy_age_unknown(self):
  t=m.Tracks();t.follow('N0CALL');t.add('N0CALL',47,-122,stamp='12:00:00')
  t.add('N0CALL',47,-122,stamp='12:01:00')
  self.assertEqual(len(t.points()),1);self.assertEqual(t.freshness(100000),'age unknown')
  t.add('N0CALL',47,-122,observed_at=100)
  self.assertEqual(t.freshness(101),'fresh');self.assertEqual(t.freshness(401),'stale')
  self.assertEqual(t.freshness(99),'age unknown')
 def test_limits_preserve_followed_station_and_detach_snapshots(self):
  t=m.Tracks(max_stations=2,max_points=3);t.follow('N0CALL')
  for n in range(10):t.add('N0CALL',47+n/100,-122)
  t.add('OTHER',48,-122);t.add('THIRD',48,-123)
  self.assertEqual(len(t.points()),3);self.assertEqual(len(t.history),2)
  self.assertIn('N0CALL',t.history)
  t.points()[0]['lat']=0;self.assertNotEqual(t.points()[0]['lat'],0)
 def test_invalid_and_out_of_order_full_capture_time(self):
  t=m.Tracks();t.follow('N0CALL')
  for lat,lon in ((float('nan'),0),(91,0),(0,181)):
   self.assertFalse(t.add('N0CALL',lat,lon))
  self.assertFalse(t.add('N0CALL-16',47,-122))
  t.add('N0CALL',47,-122,stamp='2026-10-17T20:00:00+00:00')
  self.assertFalse(t.add('N0CALL',48,-123,stamp='2026-10-17T19:00:00+00:00'))
  self.assertEqual(t.camera_position(),(47,-122))
if __name__=='__main__':unittest.main()
