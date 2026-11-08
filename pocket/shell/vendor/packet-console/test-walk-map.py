import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tests'))
from reference_fixtures import maps
"""Walk-only layer coverage, road profiles, row runs and color backgrounds."""
import importlib.util,random,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parent
s=importlib.util.spec_from_file_location('walk_map_test',ROOT/'n810-walk-map.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class Tests(unittest.TestCase):
 def test_coverage_fallback_cache_and_sizes(self):
  a=m.Atlas(str(maps()))
  for w,h in ((130,33),(77,18),(65,33)):
   for span in (40,20,10,5,2.5,1.25):
    runs,names=a.background((47.2,-122.54),span,w,h,True)
    self.assertEqual(sum(right-left for y,left,right,char,kind in runs),w*h)
    self.assertTrue(all(0<=y<h and 0<=left<right<=w for y,left,right,char,kind in runs))
    if span<=5:self.assertEqual(a.stats['local'],w*h*2)
    else:self.assertGreater(a.stats['fallback'],0)
    self.assertEqual(a.stats['unknown'],0)
    same,_=a.background((47.2,-122.54),span,w,h,True)
    self.assertIs(same,runs);self.assertEqual(a.stats['cache'],'ram')
  a.background((48.5,-123.5),40,77,18,False);self.assertEqual(a.stats['local'],0);self.assertGreater(a.stats['fallback'],0)
  a.background((0,0),40,77,18,False);self.assertEqual(a.stats['unknown'],77*18*2)
  with self.assertRaises(ValueError):a.background((47,-122),48001,77,18,True)
 def test_roads_off_and_wide_only_major(self):
  a=m.Atlas(str(maps()))
  runs,_=a.background((47.2,-122.54),2,130,33,True)
  self.assertTrue(any(k.startswith('street') for *_,k in runs));self.assertGreater(a.stats['road_cells'],0)
  runs,_=a.background((47.2,-122.54),20,130,33,True)
  self.assertFalse(any(k.startswith('street') for *_,k in runs));self.assertTrue(any(k.startswith('route') for *_,k in runs))
  runs,_=a.background((47.2,-122.54),2,130,33,False)
  self.assertFalse(any(k.startswith(('street','route')) for *_,k in runs));self.assertEqual(a.stats['road_cells'],0)
 def test_road_background_uses_terrain_and_toggle_flattens(self):
  pairs={}
  with patch.object(m.curses,'has_colors',return_value=True),patch.object(m.curses,'COLORS',16,create=True),patch.object(m.curses,'COLOR_PAIRS',256,create=True),patch.object(m.curses,'init_pair',side_effect=lambda n,f,b:pairs.update({n:(f,b)})),patch.object(m.curses,'color_pair',side_effect=lambda n:n):
   m.init_colors();self.assertEqual(pairs[208+5][1],m.PALETTE[5]);self.assertNotEqual(pairs[208+5][1],0)
   self.assertNotEqual(m.attr('band45'),m.attr('band45',False))
   self.assertEqual(m.attr('street5',False)&~m.curses.A_DIM,208+7)
 def test_fine_intervals_and_creek_independent_of_roads(self):
  a=m.Atlas(str(maps()))
  for span,interval in ((1,5),(2.5,5),(5,10),(10,25)):
   runs,_=a.background((47.2,-122.54),span,130,33,False)
   self.assertEqual(a.stats['interval'],interval)
   if span<=5:
    self.assertFalse(any(k.startswith('contour') for *_,k in runs))
    self.assertGreater(a.stats['stream_cells'],0)
    self.assertTrue(any(k.startswith('stream') for *_,k in runs))
  runs,_=a.background((48.5,-123.5),2,130,33,False)
  self.assertFalse(any(k.startswith('contour') for *_,k in runs))
 def test_contour_toggle_hides_lines_but_keeps_streams(self):
  with patch.object(m,'COLORED',True),patch.object(m.curses,'color_pair',side_effect=lambda n:n):
   self.assertEqual(m.attr('contour1',False),207)
   self.assertEqual(m.attr('stream1',False)&~m.curses.A_BOLD,239)
   self.assertEqual(m.attr('stream1',True)&~m.curses.A_BOLD,233)
 def test_integer_line_clipping_bounds_and_no_divzero(self):
  rng=random.Random(99)
  for _ in range(5000):
   line=[rng.randrange(-150,250) for i in range(4)];v=m.clip(*line,130,33)
   if v is not None:
    x,y,xx,yy=v;self.assertTrue(0<=x<130 and 0<=xx<130 and 0<=y<33 and 0<=yy<33)
  self.assertEqual(m.clip(-5,4,140,4,130,33),(0,4,129,4))

if __name__=='__main__':unittest.main()
