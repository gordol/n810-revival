"""Stable pixel palettes avoid repacking; every visual input invalidates."""
from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/p) for p in ('graphics','shell')]
from core import Host
import mbx
class PaletteCache(unittest.TestCase):
 def test_unchanged_and_changed_inputs(self):
  h=Host(100,30,[]);r=mbx.Renderer.__new__(mbx.Renderer);r.host=h
  with patch.object(mbx,'style',wraps=mbx.style) as convert:
   a=r.prepare_palette();calls=convert.call_count
   self.assertGreater(calls,0);self.assertIs(r.prepare_palette()[0],a[0]);self.assertEqual(convert.call_count,calls)
   for name,value in (('tinted',not h.tinted),('overview_opacity',.5),('palette','amber')):
    setattr(h,name,value);r.prepare_palette();self.assertGreater(convert.call_count,calls);calls=convert.call_count
    self.assertIs(r.prepare_palette()[0],r.layer_palette);self.assertEqual(convert.call_count,calls)
 def test_cached_and_fresh_values_match(self):
  h=Host(100,30,[]);r=mbx.Renderer.__new__(mbx.Renderer);r.host=h
  for tinted in (False,True):
   for opacity in (0,.5,1):
    h.tinted=tinted;h.overview_opacity=opacity
    a,f=r.prepare_palette();expected=(tuple(a),f);r.palette_inputs=None
    b,g=r.prepare_palette();self.assertEqual(expected,(tuple(b),g))
