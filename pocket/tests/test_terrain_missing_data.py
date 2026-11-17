# SPDX-License-Identifier: GPL-2.0-or-later
import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import terrain_elevation as t
class MissingElevationTests(unittest.TestCase):
 def test_outside_selected_data_is_unknown_without_legacy_packs(self):
  with patch('local_elevation.sample',return_value=(None,{})),patch.object(t,'tiled_index',return_value=None),patch.object(t,'elevation',side_effect=FileNotFoundError),patch.object(t,'regional_grid',side_effect=FileNotFoundError):
   self.assertEqual(t.sample_elevation(5.5555,5.5555),(None,{}))
   result=t.classify_path('5.5555,5.5555','5.5655,5.5555')
   self.assertEqual(result['los'],'unknown');self.assertEqual(result['fresnel'],'unknown')
 def test_corrupt_data_is_not_silently_treated_as_unknown(self):
  with patch('local_elevation.sample',side_effect=ValueError('checksum')):
   with self.assertRaisesRegex(ValueError,'checksum'):t.sample_elevation(5.5555,5.5555)
if __name__=='__main__':unittest.main()
