import importlib.util,io,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parent
s=importlib.util.spec_from_file_location('rgb_map_test',ROOT/'n810-map-rgb.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Tests(unittest.TestCase):
 def test_endpoints_and_monotonic_brightness(self):
  self.assertEqual(m.band_color(35,35,80),m.LOW);self.assertEqual(m.band_color(80,35,80),m.HIGH)
  colors=[m.band_color(v,35,80) for v in range(35,81,5)]
  self.assertEqual(sorted(sum(c) for c in colors),[sum(c) for c in colors]);self.assertNotIn((255,255,255),colors)
 def test_real_filled_bands_coverage_cache_and_toggles(self):
  atlas=m.atlas(str(ROOT/'maps'));center=(47.17,-122.52)
  frames=[]
  for span,interval in ((1,5),(5,10),(20,25)):
   frame,text=m.background(atlas,center,span,80,24,True);self.assertEqual(len(frame),80*24);self.assertIn('%d m bands'%interval,text) if span<20 else self.assertIn('Regional elevation',text)
   self.assertFalse(any(c in ('┊','┄') for c,_,_ in frame));self.assertIs(m.background(atlas,center,span,80,24,True)[0],frame)
  frame,text=m.background(atlas,center,1,80,24,False)
  self.assertTrue(any(fg==m.CREEK for _,fg,_ in frame));self.assertGreater(len({bg for _,_,bg in frame}),5)
  flat,text=m.background(atlas,center,1,80,24,False,False)
  self.assertTrue({bg for _,_,bg in flat}<={m.LAND,m.WATER});self.assertTrue(any(fg==m.CREEK for _,fg,_ in flat))
  _,text=m.background(atlas,(48.5,-123.5),2,80,24,False);self.assertIn('Regional heights',text)
 def test_surface_partial_updates_and_marker_background(self):
  s=m.Surface();frame=((' ',m.LOW,m.LOW),(' ',m.HIGH,m.HIGH));buf=io.StringIO()
  with patch.object(m.sys,'stdout',buf):
   s.draw(frame,{},0,0,2,1);self.assertGreater(s.last_bytes,0)
   s.draw(frame,{},0,0,2,1);self.assertEqual(s.last_bytes,0)
   s.draw(frame,{(1,0):('O',m.TRACK)},0,0,2,1);self.assertIn('48;2;153;157;101',buf.getvalue());self.assertEqual(s.previous[1],('O',m.TRACK,m.HIGH))
 def test_walk_rgb_skips_ansi_map_layer(self):
  import argparse,tempfile
  spec=importlib.util.spec_from_file_location('walk_rgb_render_test',ROOT/'n810-aprs-walk.py');walk=importlib.util.module_from_spec(spec);spec.loader.exec_module(walk)
  class Screen:
   def getmaxyx(self):return 30,100
   def clear(self):pass
   def move(self,*args):pass
   def clrtoeol(self):pass
   def addnstr(self,*args):pass
   def refresh(self):pass
  with tempfile.TemporaryDirectory() as folder:
   app=walk.Walk(argparse.Namespace(callsign='N0ANT',budget=20,logs=folder));app.center=(47.17,-122.52);app.span=1;app.fit_requested=False
   with patch.object(walk.rgb_map,'enabled',return_value=True),patch.object(walk,'map_layer',side_effect=AssertionError('ANSI map must not be drawn')),patch.object(walk.rgb_map.Surface,'draw') as output:
    app.draw(Screen());self.assertEqual(output.call_count,1)
    app.draw(Screen());self.assertEqual(output.call_count,1)
   app.log.close()
 def test_trail_clips_and_does_not_join_long_gap(self):
  atlas=m.atlas(str(ROOT/'maps'))
  spec=importlib.util.spec_from_file_location('clip_test',ROOT/'n810-walk-map.py');wm=importlib.util.module_from_spec(spec);spec.loader.exec_module(wm)
  points=[dict(lon=0,lat=0,time=1),dict(lon=1,lat=0,time=30)]
  cells=m.trail(points,lambda p:(p['lon']*20-5,4),10,10,wm.clip)
  self.assertEqual(set(cells),{(x,4) for x in range(10)})
  points[1]['time']=300;self.assertEqual(m.trail(points,lambda p:(1,1),10,10,wm.clip),{})
 def test_regional_heights_and_large_view_cost_is_bounded(self):
  atlas=m.atlas(str(ROOT/'maps'))
  frame,text=m.background(atlas,(47.5,-122.5),500,100,30,True)
  self.assertGreater(len({bg for _,_,bg in frame}),4);self.assertIn('Regional elevation',text)
  frame,text=m.background(atlas,(47.5,-122.5),48000,100,30,True);self.assertEqual(len(frame),3000)
 def test_fallback_switch(self):
  with patch.dict(m.os.environ,{'N810_MAP_RGB':'0'}):self.assertFalse(m.enabled())
if __name__=='__main__':unittest.main()
