"""The native map samples real terrain beyond the terminal cell grid."""
import sys
import unittest
from array import array
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'graphics'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from map_pixels import terrain_detail


class TerrainDetail(unittest.TestCase):
 def test_desktop_resamples_at_pixel_resolution(self):
  requests=[]
  def viewport(center,span,width,height,aspect):
   requests.append((width,height))
   return NS(center=center,span=span,width=width,height=height,cell_aspect=aspect)
  def render(view,terrain):
   self.assertTrue(terrain)
   return [(None,(x%256,y%256,0),(x%256,(y+1)%256,0))
           for y in range(view.height) for x in range(view.width)],''
  view=NS(center=(47.,-122.),span=10.,width=40,height=12,cell_aspect=2)
  original=array('I',[0]*(view.width*view.height*2))
  features=NS(terrain=original,sample_width=view.width,sample_height=view.height*2)
  surface=NS(terrain=True,image=NS(source='semantic'),renderer=NS(
      module=NS(Viewport=viewport),engine=NS(_rgb_terrain=render)))
  with patch('desktop_elevation.enabled',return_value=True):
   samples,width,height=terrain_detail(surface,view,features)
  self.assertEqual(requests,[(320,96)])
  self.assertEqual((width,height,len(samples)),(320,192,320*192))
  self.assertNotEqual(samples[0],samples[5])
  self.assertIsNot(samples,original)

 def test_preview_reuses_terrain_when_only_target_box_changes(self):
  from collections import namedtuple
  from map_pixels import View
  viewport=namedtuple('Viewport','center span width height cell_aspect')((47.,-122.),5.,3,2,2.)
  features=NS(terrain=array('I',[0]*12),sample_width=3,sample_height=4,
              vectors=(),labels={})
  image=NS(source='semantic')
  surface=NS(image=image,terrain=True,unavailable_reason='',overlay_vectors=(),
             viewport=lambda:viewport,features=lambda view,plane:features)
  layer=(0,2,3,2,tuple((' ',0) for _ in range(6)))
  native=View(None,None)
  with patch('map_pixels.terrain_detail',return_value=(features.terrain,3,4)) as detail:
   native.build(layer,surface)
   native.build(layer,surface)
  self.assertEqual(detail.call_count,1)

 def test_dense_pixel_fast_path_matches_desktop_relief_colors(self):
  import numpy as np
  from desktop_elevation import pixel_samples,render
  from offline_map import map_rgb
  view=NS(center=(47.,-122.),span=10.,width=4,height=2,cell_aspect=2.,ground_m_per_halfcell=20.)
  water=np.array([[1,1,0,1],[1,0,0,1],[1,1,1,1],[0,1,1,0]],dtype=np.int8)
  heights=np.array([[np.nan,80,np.nan,100],[150,np.nan,np.nan,240],[300,500,700,900],[np.nan,1200,1500,np.nan]],dtype=float)
  spacing=np.full((4,4),30.,dtype=float)
  rows=np.where(water==0,0,1).tolist()
  engine=NS(_desktop_dem_signature=('test',),palette=NS(WATER=(23,68,60),LAND=(35,88,51)),
            atlas=NS(raster=lambda *a:(rows,None,None)),
            _original_rgb_terrain=lambda *a:([(' ',(35,88,51),(35,88,51)) for _ in range(8)],''))
  with patch('desktop_shoreline.mask',return_value=water),patch('desktop_elevation.sample',return_value=(heights,spacing)):
   cells,_=render(engine,view,True)
   fast=pixel_samples(engine,view)
  expected=array('I')
  for row in range(view.height):
   line=cells[row*view.width:(row+1)*view.width]
   expected.extend(map_rgb(upper) for _,upper,_ in line)
   expected.extend(map_rgb(lower) for _,_,lower in line)
  self.assertEqual(fast,(expected,4,4))

 def test_other_sources_keep_original_samples(self):
  original=array('I',[1,2]);features=NS(terrain=original,sample_width=1,sample_height=2)
  view=NS(width=1,height=1)
  for source,terrain in [('provider',True),('semantic',False)]:
   surface=NS(terrain=terrain,image=NS(source=source))
   with patch('desktop_elevation.enabled',return_value=True):
    self.assertEqual(terrain_detail(surface,view,features),(original,1,2))
  with patch('desktop_elevation.enabled',return_value=False):
   self.assertEqual(terrain_detail(NS(terrain=True,image=NS(source='semantic')),view,features),(original,1,2))

 def test_sample_budget_bounds_large_windows(self):
  view=NS(width=600,height=200)
  original=array('I',[1,2]);features=NS(terrain=original,sample_width=1,sample_height=2)
  seen=[]
  def viewport(center,span,width,height,aspect):
   seen.append(width*height)
   return NS(width=width,height=height)
  surface=NS(terrain=True,image=NS(source='semantic'),renderer=NS(
      module=NS(Viewport=viewport),engine=NS(_rgb_terrain=lambda *a: self.fail('too many samples'))))
  with patch('desktop_elevation.enabled',return_value=True):
   self.assertEqual(terrain_detail(surface,view,features),(original,1,2))
  self.assertFalse(seen)


if __name__=='__main__':unittest.main()
