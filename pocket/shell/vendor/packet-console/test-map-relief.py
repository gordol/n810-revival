# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fine offline terrain selection and visibility checks; no network or radio."""
import importlib.util,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parent

def module(name,file):
 spec=importlib.util.spec_from_file_location(name,ROOT/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class Tests(unittest.TestCase):
 def test_fine_pack_skips_coarse_work_and_falls_back_when_zoomed_out(self):
  m=module('maps','n810-map.py');a=m.Atlas(str(ROOT/'maps'))
  cells,names=a.background((47.1908,-122.5337),1.2,130,27,False)
  self.assertEqual(names,['Lakewood fine relief']);self.assertGreater(len({kind for char,kind in cells.values()}),5)
  for p in a.packs:
   if p.get('raster') and p['name']!='Lakewood fine relief':self.assertNotIn('_pixels',p)
  _,names=a.background((47.1908,-122.5337),80,55,18,False)
  self.assertNotIn('Lakewood fine relief',names);self.assertIn('Puget Sound & surroundings',names)
 def test_compact_cache_roundtrip_and_bad_cache_rebuild(self):
  m=module('compact','n810-map.py')
  with tempfile.TemporaryDirectory() as root:
   a=m.Atlas(str(ROOT/'maps'),root);result=a.background((47.1908,-122.5337),1.2,130,27,True)
   files=list(Path(root).glob('*.bin'));self.assertEqual(len(files),1);self.assertLess(files[0].stat().st_size,15000)
   b=m.Atlas(str(ROOT/'maps'),root)
   b.raster_base=lambda *args: self.fail('Prepared cache was recomputed')
   self.assertEqual(b.background((47.1908,-122.5337),1.2,130,27,True),result)
   files[0].write_bytes(b'incomplete')
   c=m.Atlas(str(ROOT/'maps'),root);self.assertEqual(c.background((47.1908,-122.5337),1.2,130,27,True),result)
 def test_visibility_fails_open_and_tracks_current_panes(self):
  v=module('visible','n810-ui-visible.py')
  with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'TMUX':'/tmp/example,42,0','TMUX_PANE':'%7'}):
   v.STATE=Path(root)/'state';v._due=0;self.assertTrue(v.visible())
   v.STATE.write_text('42\n%8\n');v._due=0;self.assertFalse(v.visible())
   v.STATE.write_text('42\n%7\n%8\n');v._due=0;self.assertTrue(v.visible())
   v.STATE.write_text('99\n%8\n');v._due=0;self.assertTrue(v.visible())
 def test_shared_palette_supports_relief_and_bright_markers(self):
  m=module('palette','n810-map-style.py');pairs={}
  class Win:
   def bkgd(self,*args):pass
  with patch.object(m.curses,'has_colors',return_value=True),patch.object(m.curses,'start_color'),patch.object(m.curses,'COLORS',16,create=True),patch.object(m.curses,'COLOR_PAIRS',256,create=True),patch.object(m.curses,'init_pair',side_effect=lambda n,f,b:pairs.update({n:(f,b)})),patch.object(m.curses,'color_pair',side_effect=lambda n:n):
   m.init_screen(Win());self.assertEqual(pairs[7],(0,11));self.assertEqual(pairs[72],(15,0))
   self.assertNotEqual(m.cell_attr('relief12'),m.cell_attr('relief12',False))

if __name__=='__main__':unittest.main()
