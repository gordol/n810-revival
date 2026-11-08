# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate reuse of tslib and historical collector transforms with Pocket."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import tempfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'pocket/shell'))
spec=importlib.util.spec_from_file_location('setup_touch',Path(__file__).with_name('setup_touch.py'))
setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)
DEVICE=dict(name='TSC2005 touchscreen',id=[24,0,0,0],physical='fixture',x_range=[100,4100],y_range=[200,4200])

class TouchSetupTests(unittest.TestCase):
 def test_available_mapping_is_confirmed_saved_and_reused(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'dev/input').mkdir(parents=True);(root/'dev/input/event0').touch()
   (root/'etc').mkdir();(root/'etc/pointercal').write_text('2 0 -200 0 1 -200 10')
   def local_path(value):return root/str(value).lstrip('/') if str(value).startswith(('/etc/','/dev/','/mnt/','/media/')) else Path(value)
   class Reader:
    device=DEVICE
    def __init__(self,path):pass
    def close(self):pass
   with patch.object(setup,'Path',side_effect=local_path),patch.object(setup,'EventReader',Reader),patch.object(sys,'argv',['n810-setup-touch']),patch('builtins.input',return_value='y'),patch.object(setup.subprocess,'Popen') as run:
    run.return_value.poll.return_value=None
    setup.main()
    run.assert_called_once()
   profile=root/'etc/n810/touch-calibration.json'
   self.assertTrue(profile.is_file())
   setup.Calibration.load(profile,DEVICE,setup.display(800,480))
   with patch.object(setup,'Path',side_effect=local_path),patch.object(setup,'EventReader',Reader),patch.object(sys,'argv',['n810-setup-touch']),patch('builtins.input',side_effect=AssertionError('existing mapping prompted again')):
    setup.main()

 def test_missing_mapping_collects_targets_and_runs_real_fitter(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'dev/input').mkdir(parents=True);(root/'dev/input/event0').touch()
   def local_path(value):return root/str(value).lstrip('/') if str(value).startswith(('/etc/','/dev/','/mnt/','/media/')) else Path(value)
   class Reader:
    device=DEVICE
    def __init__(self,path):pass
    def close(self):pass
   real_run=setup.subprocess.run
   def collect(command,**kwargs):
    if command[0]==sys.executable:return real_run(command,**kwargs)
    Path(command[1]).write_text('screen_x,screen_y,raw_x,raw_y,samples\n'+''.join(f'{x},{y},{100+x*5},{200+y*4000/480},5\n' for x,y in [(80,48),(720,48),(720,432),(80,432),(400,240)]))
   real_output=setup.subprocess.check_output
   fitter=ROOT/'platform/scripts/n810-touch-fit.py'
   if not fitter.exists():fitter=Path('/opt/n810-touch/n810-touch-fit.py')
   def fit(command,**kwargs):return real_output([sys.executable,str(fitter),command[-1]],**kwargs)
   with patch.object(setup,'Path',side_effect=local_path),patch.object(setup,'EventReader',Reader),patch.object(sys,'argv',['n810-setup-touch']),patch('builtins.input',return_value=''),patch.object(setup.subprocess,'run',side_effect=collect),patch.object(setup.subprocess,'check_output',side_effect=fit):
    setup.main()
   cal=setup.Calibration.load(root/'etc/n810/touch-calibration.json',DEVICE,setup.display(800,480))
   u,v=cal.normalized(2100,2200)
   self.assertAlmostEqual(u,.5)
   self.assertAlmostEqual(v,.5)

 def test_tslib_pixels_convert_to_pocket_normalized_coordinates(self):
  profile=setup.from_pointercal('2 0 -200 0 1 -200 10',DEVICE)
  cal=setup.Calibration(profile,DEVICE,setup.display(800,480))
  self.assertEqual(cal.cell(100,200,800,480),(0,0))
  self.assertEqual(cal.cell(2100,2600,800,480),(400,240))
 def test_swapped_and_inverted_axes_preserve_mapping(self):
  profile=setup.from_pointercal('0 -2 8400 1 0 -100 10',DEVICE)
  cal=setup.Calibration(profile,DEVICE,setup.display(800,480))
  self.assertEqual(cal.cell(2500,2200,800,480),(400,240))
 def test_invalid_saved_transform_is_rejected(self):
  for text in ['1 2','1 0 0 0 1 0 0','0 0 0 0 0 0 1','1 0 99999999 0 1 0 1']:
   with self.subTest(text=text),self.assertRaises(ValueError):setup.from_pointercal(text,DEVICE)
 def test_pixel_fit_uses_current_runtime_schema(self):
  profile=setup.from_pixels([.2,0,-20,0,.12,-24],DEVICE)
  cal=setup.Calibration(profile,DEVICE,setup.display(800,480))
  self.assertEqual(cal.cell(2100,2200,800,480),(400,240))

if __name__=='__main__':unittest.main()
