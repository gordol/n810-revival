"""Offline geography, rendering and replay-state checks; no radio or network."""
import importlib.util, pathlib, tempfile, gzip, json, unittest, re
ROOT=pathlib.Path(__file__).resolve().parent

def load(name,file):
 s=importlib.util.spec_from_file_location(name,ROOT/file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
v=load('view','n810-aprs-view.py');b=load('builder','build-map-pack.py');m=v._map

class MapTests(unittest.TestCase):
 def test_clip(self):
  a,b=m.clipped_segment((-100,5),(100,5),10,10)
  self.assertAlmostEqual(a[0],0);self.assertAlmostEqual(b[0],9)
  self.assertEqual((a[1],b[1]),(5,5))
  self.assertIsNone(m.clipped_segment((-2,-2),(-1,-1),10,10))
 def test_pack(self):
  a=m.Atlas(str(ROOT/'maps'));self.assertTrue(a.packs);self.assertFalse(a.errors)
  water,_=a.background([47.38,-122.52],160,55,18,False)
  roads,_=a.background([47.38,-122.52],160,55,18,True)
  self.assertTrue(water);self.assertFalse(any(kind=='road' for _,kind in roads.values()))
  self.assertEqual(water,roads)
  self.assertTrue(all(0<=x<55 and 0<=y<18 for x,y in roads))
  _,names=a.background([0,0],160,55,18,True);self.assertEqual(names,[])
 def test_land_water_and_disk_cache(self):
  import base64,zlib
  atlas=m.Atlas(str(ROOT/'maps'));pack=next(p for p in atlas.packs if p['name']=='Puget Sound & surroundings');r=pack['raster']
  pixels=zlib.decompress(base64.b64decode(r['data']));west,south,east,north=pack['bbox']
  def wet(lon,lat):
   x=round((lon-west)/(east-west)*(r['width']-1));y=round((north-lat)/(north-south)*(r['height']-1))
   return pixels[y*r['width']+x]&3
  self.assertEqual(wet(-122.52,47.17),0) # Lakewood
  self.assertEqual(wet(-122.45,47.70),1) # Puget Sound
  self.assertEqual(wet(-122.26,47.60),2) # Lake Washington
  with tempfile.TemporaryDirectory() as d:
   a=m.Atlas(str(ROOT/'maps'),d);first=a.background([47.38,-122.52],160,55,18,False)
   self.assertTrue(any(kind=='tone00' for _,kind in first[0].values()))
   b=m.Atlas(str(ROOT/'maps'),d)
   b.raster_base=lambda *args: self.fail('Cached base was recalculated')
   self.assertEqual(b.background([47.38,-122.52],160,55,18,False),first)
 def test_terrain_and_lake_reduction(self):
  a=m.Atlas(str(ROOT/'maps'));p=next(p for p in a.packs if p['name']=='Puget Sound & surroundings')
  self.assertIn('terrain',p)
  self.assertTrue(any(label['name']=='Mt Rainier' for label in p['labels']))
  cells,_=a.background([47.60,-122.26],240,41,15,False)
  self.assertNotEqual(cells[20,7][1],'tone00') # Inland lake suppressed at wide zoom
  cells,_=a.background([47.25,-122.45],40,55,20,False)
  self.assertFalse(any(kind=='road' for _,kind in cells.values()))
  cells,_=a.background([47.25,-122.45],40,55,20,True)
  self.assertTrue(any(kind=='road' for _,kind in cells.values()))
 def test_reference_cannot_cover_own_station(self):
  v.curses.has_colors=lambda:False
  class Atlas:
   packs=[];errors=[]
   def background(self,*args):return {},['test']
   def project(self,*args):return 12,5
  class Win:
   def __init__(self):self.grid={}
   def getmaxyx(self):return 20,60
   def addnstr(self,y,x,text,n,attr):
    for i,c in enumerate(text[:n]):self.grid[x+i,y]=c
  state=v.State();state.atlas=Atlas();state.center=[47.17,-122.52];state.roads=False
  state.stations={'N0ANT':dict(call='N0ANT',lon=-122.52,lat=47.17)}
  w=Win();v.map_panel(w,state,120,0,0,55,15)
  self.assertEqual(w.grid[12,5],'*')
  self.assertNotIn('+',w.grid.values())
  row=''.join(w.grid.get((x,5),' ') for x in range(55))
  self.assertIn('N0ANT',row)
  self.assertNotIn('(you)',row)
 def test_auto_fit(self):
  s=v.State();s.auto_fit=True;s.center=[0,0]
  s.stations={'BALDI':{'lat':47.22,'lon':-121.84}}
  span=v.fitted_span(s,55,15,160)
  for lat,lon in [(47.17,-122.52),(47.22,-121.84)]:
   x,y=m.Atlas.project(lon,lat,s.center,span,55,15)
   self.assertTrue(0<x<54 and 0<y<14)
 def test_selection_unknown_and_fit(self):
  state=v.State();state.auto_fit=False;state.center=[47.17,-122.52];state.selected=0
  state.add('17:35:23 UNKNOWN>APRS,RELAY* ctl=03 pid=f0 :TARGET   :hello')
  self.assertEqual(v.include_selection(state,40,70,25),40)
  self.assertIn('location unknown',v.selection_caption(state))
  state.stations['RELAY']={'lat':48,'lon':-122}
  self.assertIn('relays: RELAY',v.selection_caption(state))
  state.add('17:36:23 FAR>APRS ctl=03 pid=f0 !4800.00N/12100.00W_test')
  old_center=list(state.center);span=v.include_selection(state,40,70,25)
  self.assertGreater(span,40)
  for lat,lon in [(48,-121),(old_center[0],old_center[1])]:
   x,y=m.Atlas.project(lon,lat,state.center,span,70,25)
   self.assertTrue(0<=x<70 and 0<=y<25)
 def test_regional_coverage_and_priority(self):
  atlas=m.Atlas(str(ROOT/'maps'))
  rasters=[p for p in atlas.packs if 'raster' in p]
  self.assertEqual(rasters[0]['name'],'Pacific Northwest overview')
  self.assertEqual(next(p for p in reversed(rasters) if not p.get('fast_samples'))['name'],'Puget Sound & surroundings')
  for center in ([49.2,-123.1],[45.5,-122.7],[50.5,-125]):
   cells,names=atlas.background(center,80,55,18,False)
   self.assertGreater(len(cells),900)
   self.assertIn('Pacific Northwest overview',names)
 def test_bad_pack(self):
  with tempfile.TemporaryDirectory() as d:
   with gzip.open(pathlib.Path(d)/'bad.json.gz','wt') as f:json.dump({'version':9},f)
   a=m.Atlas(d);self.assertFalse(a.packs);self.assertTrue(a.errors)
 def test_simplify(self):
  self.assertEqual(b.simplify([[0,0],[.5,0],[1,0]],.1),[[0,0],[1,0]])
  self.assertEqual(len(b.simplify([[0,0],[.5,.5],[1,0]],.1)),3)
 def test_draw_sizes(self):
  v.curses.has_colors=lambda:False
  class W:
   def __init__(self,h,w):self.size=(h,w);self.text=[];self.cells={}
   def getmaxyx(self):return self.size
   def erase(self):pass
   def addnstr(self,y,x,text,n,attr):
    assert 0<=y<self.size[0] and 0<=x<self.size[1]
    assert n<=self.size[1]-x-1
    self.text.append(text[:n])
    for offset,char in enumerate(text[:n]):self.cells[x+offset,y]=char
  state=v.State();state.atlas=m.Atlas(str(ROOT/'maps'));state.center=[47.38,-122.52]
  state.roads=True;state.help=False;state.auto_fit=True;state.selected=0;state.map_dir='maps'
  state.add('17:35:23 BALDI>APOT21 ctl=03 pid=f0 !4713.13N/12150.61W_test')
  for h,w in ((30,100),(24,80),(16,64),(10,40)):
   win=W(h,w);v.draw(win,state,160);self.assertTrue(win.text)
  state.add('17:36:23 RELAY>APRS ctl=03 pid=f0 !4720.00N/12220.00W_test')
  state.add('17:37:23 BALDI>APOT21,RELAY* ctl=03 pid=f0 !4713.13N/12150.61W_test')
  win=W(30,100);v.draw(win,state,160)
  self.assertIn('@',win.text);self.assertIn('·',win.text)
  state.packets[0]['route']='APOT21,UNKNOWN*,RELAY*'
  win=W(30,100);v.draw(win,state,160)
  self.assertNotIn('·',win.text)
  state.debug=True;state.debug_key=state.packets[0]['raw'];state.debug_record=None;state.debug_scroll=0
  win=W(30,100);v.draw(win,state,160)
  self.assertIn('PAYLOAD',win.text)
  self.assertFalse(any('AUTO MAP' in t for t in win.text))
  state.debug=False
  state.packets[0]['route']='APOT21'
  state.stations={}
  for i in range(32):
   call='S%02d'%i
   state.stations[call]=dict(call=call,lat=46.8+(i//8)*.5,lon=-124+(i%8)*.45)
  state.stations['BALDI']=dict(call='BALDI',lat=47.22,lon=-121.84)
  win=W(30,100);v.map_panel(win,state,540,0,0,78,25)
  rendered='\n'.join(''.join(win.cells.get((x,y),' ') for x in range(100)) for y in range(30))
  self.assertLessEqual(len(re.findall(r'S[0-9]{2}',rendered)),6)
  self.assertIn('BALDI',rendered)
  state.help=True;v.draw(W(30,100),state,160)
  v.draw_map(W(30,40),state,160)

if __name__=='__main__':unittest.main()
