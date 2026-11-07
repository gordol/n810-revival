import sys,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from station_workspace import StationMap,Context
from map_fixtures import install
class PreviewStationsTests(unittest.TestCase):
 def test_enter_acknowledgement_survives_los_controls_and_cancel(self):
  from terrain_point_map import PointMap
  from unittest.mock import patch
  f=StationMap(Context(),Path(__file__).resolve().parents[1]/'shell/vendor/packet-console',lambda:None)
  f.width=120;f.height=42
  tool=PointMap(lambda *a,**k:None,lambda:None,base=f)
  try:
   f.target_box.choose((47.19,-122.54),8.8);f.key('\r')
   with patch.object(f.renderer,'frame',return_value=None):
    lines=tool.lines()
    self.assertIn('Zoom accepted',lines[0]);self.assertIn('Loading 8.8 km',lines[0])
    self.assertIn('Zoom accepted',lines[-1]);self.assertIn('Esc cancel',lines[-1])
    self.assertIn('[Point path T]',lines[1])
    f.key('\x1b');lines=tool.lines()
    self.assertNotIn('Zoom accepted','\n'.join(lines));self.assertIsNone(f._detail_request)
  finally:f.close();f.renderer.close()
 def test_stations_stay_projected_in_preview_overview_and_after_cancel(self):
  c=Context();c.catalog(dict(revision=1,has_more=False,rows=[dict(call='NEAR',position=dict(lat=47.19,lon=-122.54),categories=[],symbol=None),dict(call='FAR',position=dict(lat=47.25,lon=-122.59),categories=[],symbol=None)]))
  f=StationMap(c,Path(__file__).resolve().parents[1]/'shell/vendor/packet-console',lambda:None)
  install(self,f.renderer)
  f.width=160;f.height=55;f.center=(47.19,-122.54);f.span=8.8
  def ready():
   until=time.monotonic()+12
   while time.monotonic()<until:
    f.lines()
    if f._shown_image:return
    time.sleep(.01)
   self.fail(f.renderer.error)
  try:
   ready();camera=f.center,f.span
   f.key('-');f.lines()
   self.assertTrue(any(hit[3]=='NEAR' for hit in f._station_hits))
   backdrop=f._zoom_context_image;context=f._zoom_context_view
   f.key('+');self.assertIs(f._zoom_context_image,backdrop)
   f.lines();self.assertEqual(f._zoom_context_view,context)
   self.assertEqual((f.center,f.span),camera)
   f.key('o');f.lines()
   self.assertTrue(any(hit[3]=='NEAR' for hit in f._station_hits))
   f.key('\x1b');f.lines();self.assertEqual((f.center,f.span),camera)
   self.assertTrue(any(hit[3]=='NEAR' for hit in f._station_hits))
  finally:f.close();f.renderer.close()

 def test_station_label_toggle_preserves_markers_and_selected_label(self):
  from offline_map import Image
  from unittest.mock import patch
  class View:
   center=(0,0);span=10
   def project(self,lon,lat):return lon,lat
  c=Context();c.catalog(dict(revision=1,has_more=False,rows=[dict(call='NEAR',position=dict(lat=2,lon=2),categories=[],symbol=None),dict(call='OTHER',position=dict(lat=7,lon=2),categories=[],symbol=None)]))
  c.select(None,dict(call='NEAR',position=(2,2)))
  f=StationMap(c,Path(__file__).resolve().parents[1]/'shell/vendor/packet-console',lambda:None)
  install(self,f.renderer)
  image=Image(50,12,tuple((' ',0) for _ in range(600)),'',(),0,View())
  try:
   with patch('repeater_catalog.load',return_value=()):
    f.station_labels=False;f.station_layer(image)
    self.assertTrue(any(hit[3]=='OTHER' and hit[2]==1 for hit in f._station_hits))
    self.assertFalse(any(hit[3]=='OTHER' and hit[2]>1 for hit in f._station_hits))
    self.assertTrue(any(hit[3]=='NEAR' and hit[2]>1 for hit in f._station_hits))
    f.station_labels=True;f.station_layer(image)
    self.assertTrue(any(hit[3]=='OTHER' and hit[2]>1 for hit in f._station_hits))
  finally:f.close();f.renderer.close()
