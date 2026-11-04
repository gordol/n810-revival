import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('decoder',Path(__file__).with_name('n810-aprs-decode.py'))
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)

class Tests(unittest.TestCase):
 def test_published_longitude_motion_example(self):
  # APRS101 chapter 10 p53: (_fn"Oj, western +100 longitude.
  r=d.decode('`(_fn"Oj/','T7SPPY')
  self.assertNotIn('error',r)
  self.assertAlmostEqual(r['position'][1],-(112+7.74/60),6)
  self.assertEqual((r['speed_knots'],r['course']),(20,251))
 def test_captured_k7mm(self):
  r=d.decode('`27}m57>/]"4n}=\\x0d','T7QPXV')
  self.assertNotIn('error',r)
  self.assertAlmostEqual(r['position'][0],47+10.86/60,6)
  self.assertAlmostEqual(r['position'][1],-(122+27.97/60),6)
  self.assertEqual((r['speed_knots'],r['course'],r['status']),(12,127,'In service'))
 def test_escaped_and_ambiguity(self):
  r=d.decode('`2[Rl \\x1c-\\`441.700MHz','TWRQTW')
  self.assertNotIn('error',r)
  self.assertEqual(r['symbol'],'-')
  r=d.decode('`27}m57>/','T7QPZZ')
  self.assertEqual(r['ambiguity'],2)
 def test_bad_and_no_false_position(self):
  for body,dest in [('`short','T7QPXV'),('`27}m57>/','BAD'),('`27}m57>/','ZZZZZZ')]:
   r=d.decode(body,dest);self.assertIn('error',r);self.assertNotIn('position',r)
  self.assertNotIn('position',d.decode(':TARGET   :meet 0533.44N/00533.38E'))
 def test_shared_phg_and_cache(self):
  payload='!4713.13N/12150.61W_PHG7830/W2,WAn,Baldi N7FSP'
  r=d.decode(payload,'APOT21');self.assertTrue(any('49 W' in x for x in d.facts(r)))
  self.assertIs(r,d.decode(payload,'APOT21'))

if __name__=='__main__':unittest.main()
