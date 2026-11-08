"""Window frames and settings icons share one-pixel, connected GUI strokes."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'graphics'))
from font_supplement import box_glyphs
from types import SimpleNamespace

class BoxGlyphs(unittest.TestCase):
 def setUp(self):
  self.font=SimpleNamespace(mapping={'A':0},glyphs=(bytes([0x55]*16),))
  box_glyphs(self.font)
 def points(self,ch):
  bits=self.font.glyphs[self.font.mapping[ch]]
  return {(x,y) for y,b in enumerate(bits) for x in range(8) if b&(128>>x)}
 def test_shared_straight_join_and_uniform_stroke(self):
  self.assertEqual(self.points('│'),{(3,y) for y in range(16)})
  self.assertEqual(self.points('─'),{(x,7) for x in range(8)})
  for ch in '┌┐└┘├┤┬┴┼':self.assertIn((3,7),self.points(ch))
 def test_rounded_corners_connect_to_both_neighbor_cells(self):
  for ch,horizontal,vertical in [('╭',(7,7),(3,15)),('╮',(0,7),(3,15)),('╰',(7,7),(3,0)),('╯',(0,7),(3,0))]:
   points=self.points(ch);self.assertIn(horizontal,points);self.assertIn(vertical,points)
   visited={horizontal}
   while True:
    more={p for p in points if any(max(abs(p[0]-q[0]),abs(p[1]-q[1]))<=1 for q in visited)}
    if more<=visited:break
    visited|=more
   self.assertEqual(visited,points)
   self.assertTrue(all(sum(px==x for px,py in points if py==y)==1 for x,y in points if y!=7))
 def test_text_unchanged_and_reapplication_is_stable(self):
  self.assertEqual(self.font.glyphs[0],bytes([0x55]*16))
  before=(dict(self.font.mapping),self.font.glyphs);box_glyphs(self.font)
  self.assertEqual(before,(self.font.mapping,self.font.glyphs))

if __name__=='__main__':unittest.main()
