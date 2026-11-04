"""Navigation order, safe command barriers, and independent map/header painting."""
import argparse
import collections
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
s=importlib.util.spec_from_file_location('walk_ui',Path(__file__).with_name('n810-aprs-walk.py'))
w=importlib.util.module_from_spec(s);s.loader.exec_module(w)

class Screen:
 def __init__(self,size=(39,133)):self.size=size;self.rows={};self.map_writes=0;self.erases=0
 def getmaxyx(self):return self.size
 def erase(self):self.rows={};self.erases+=1
 def move(self,y,x):self.cursor=y
 def clrtoeol(self):self.rows[self.cursor]=''
 def addnstr(self,y,x,text,n,attr):
  assert all(c.isprintable() for c in text)
  assert 0<=y<self.size[0] and 0<=x<self.size[1]-1 and n<=self.size[1]-x-1
  self.rows[y]=self.rows.get(y,'').ljust(x)[:x]+text[:n]
 def refresh(self):pass

class Pad:
 def __init__(self):self.runs=[]
 def bkgd(self,*args):pass
 def erase(self):pass
 def addstr(self,*args):self.runs.append(args)
 def overwrite(self,win,*args):win.map_writes+=1

class Atlas:
 def __init__(self):self.calls=[]
 def background(self,*args):self.calls.append(args);return ({(0,0):(' ','tone11'),(1,0):(' ','tone11'),(2,0):('─','road')},['fixture'])
 def project(self,*args):return (1,1)

class Tests(unittest.TestCase):
 def app(self,root):
  a=w.Walk(argparse.Namespace(callsign='N0CALL',budget=20,logs=root));a.atlas=Atlas();a.center=(5.5655,5.5855);a.span=40;a.fit_requested=False
  return a
 def test_burst_clamps_order_and_does_not_change_terrain(self):
  with tempfile.TemporaryDirectory() as root:
   app=self.app(root);app.terrain=False
   class Keys:
    def __init__(self,keys):self.keys=collections.deque(keys)
    def timeout(self,n):pass
    def getch(self):return self.keys.popleft() if self.keys else -1
   keys=Keys([ord('+')]*4+[ord('t'),ord('-')])
   barrier=w.navigation_batch(keys,app,ord('+'))
   self.assertEqual(app.span,1.25);self.assertFalse(app.terrain);self.assertEqual(barrier,ord('t'))
   self.assertEqual(keys.getch(),ord('-'));self.assertFalse(app.plan.armed)
   app.span=.5
   w.navigation_batch(Keys([ord('-')]),app,ord('+'))
   self.assertEqual(app.span,1);app.log.close()
 def test_pan_uses_zoom_at_its_fifo_position(self):
  with tempfile.TemporaryDirectory() as root:
   app=self.app(root);lat,lon=app.center
   class Keys:
    keys=collections.deque([w.curses.KEY_RIGHT,ord('+'),ord('p')])
    def timeout(self,n):pass
    def getch(self):return self.keys.popleft()
   barrier=w.navigation_batch(Keys(),app,ord('+'))
   expected=round(lon+4/(111.32*w.math.cos(w.math.radians(lat))),6)
   self.assertEqual(app.center,(round(lat,6),expected));self.assertEqual(app.span,10)
   self.assertEqual(barrier,ord('p'));app.log.close()
 def test_fifo_pause_and_arm_confirmation_are_barriers(self):
  with tempfile.TemporaryDirectory() as root:
   app=self.app(root)
   class Keys:
    def timeout(self,n):pass
    def getch(self):return ord('a')
   barrier=w.navigation_batch(Keys(),app,w.curses.KEY_RIGHT)
   self.assertEqual(barrier,ord('a'));self.assertFalse(app.plan.armed)
   app.key(barrier);self.assertEqual(app.prompt,'');app.key(ord('+'))
   self.assertEqual(app.prompt,'+');self.assertFalse(app.plan.armed);app.log.close()
 def test_navigation_wait_is_bounded_and_burst_count_capped(self):
  class Clock:
   now=0
   def __call__(self):return self.now
  clock=Clock()
  class Keys:
   wait=0
   def timeout(self,n):self.wait=n
   def getch(self):clock.now+=max(0,self.wait)/1000;return -1
  class App:
   def key(self,key):pass
  self.assertIsNone(w.navigation_batch(Keys(),App(),ord('+'),clock))
  self.assertLessEqual(clock.now,.101)
  class Flood(Keys):
   calls=0
   def getch(self):self.calls+=1;return ord('+')
  keys=Flood();w.navigation_batch(keys,App(),ord('+'),clock);self.assertEqual(keys.calls,63)
 def test_headers_do_not_repaint_or_rebuild_map(self):
  with tempfile.TemporaryDirectory() as root,patch.object(w.curses,'newpad',side_effect=lambda *args:Pad()) as pads:
   app=self.app(root);screen=Screen();app.draw(screen)
   calls=len(app.atlas.calls);writes=screen.map_writes;layers=pads.call_count
   app.received+=1;app.notice='New packet';app.position={'lat':5.5655,'lon':5.5855,'accuracy':12}
   app.view_history=True;app.archives=[{'start':'2026-10-15T15:25','track':[],'probes':[]}]
   app.draw(screen);writes=screen.map_writes
   app.position['accuracy']=20;app.received+=1;app.draw(screen)
   self.assertEqual(len(app.atlas.calls),calls);self.assertEqual(pads.call_count,layers)
   self.assertEqual(screen.map_writes,writes)
   self.assertIn('TX DISARMED',screen.rows[0]);self.assertIn('t terrain ON | r roads ON',screen.rows[1])
   self.assertEqual(screen.erases,1);app.log.close()
 def test_controls_layout_preview_and_resize(self):
  with tempfile.TemporaryDirectory() as root,patch.object(w.curses,'newpad',side_effect=lambda *args:Pad()):
   app=self.app(root);screen=Screen();app.draw(screen);self.assertEqual(app.map_size,(130,33))
   calls=len(app.atlas.calls);app.key(ord('+'));app.draw(screen,preview=True)
   self.assertEqual(len(app.atlas.calls),calls);self.assertIn('target',screen.rows[1])
   app.draw(screen);self.assertEqual(len(app.atlas.calls),calls+1)
   app.key(ord('t'));app.draw(screen);self.assertIn('t terrain OFF',screen.rows[1]);self.assertEqual(len(app.atlas.calls),calls+1)
   app.key(ord('r'));app.draw(screen);self.assertIn('r roads OFF',screen.rows[1]);self.assertFalse(app.atlas.calls[-1][-1])
   screen.size=(24,80);app.draw(screen);self.assertIn('TX DISARMED',screen.rows[0]);app.log.close()
 def test_map_styles_are_calculated_per_kind_and_runs_batched(self):
  cells={(x,0):(' ','tone11') for x in range(40)};pad=Pad()
  with patch.object(w.curses,'newpad',return_value=pad),patch.object(w,'map_attr',return_value=0) as attr:
   self.assertIs(w.map_layer(cells,40,1,True),pad)
   self.assertEqual(attr.call_count,1);self.assertEqual(len(pad.runs),1)
 def test_run_coalesces_before_drawing_and_preserves_prompt_input(self):
  with tempfile.TemporaryDirectory() as root,patch.object(w,'init_map_colors'),patch.object(w.curses,'curs_set'),patch.object(w.visibility,'visible',return_value=True):
   app=self.app(root);events=[]
   app.tick=lambda:None
   app.draw=lambda win,preview=False:events.append((app.span,preview,app.prompt))
   class Keys:
    def __init__(self):self.keys=collections.deque([ord('+')]*5+[ord('p'),ord('a'),ord('+'),27,ord('q')])
    def timeout(self,n):pass
    def getmaxyx(self):return (39,133)
    def getch(self):return self.keys.popleft() if self.keys else -1
   w.run(Keys(),app)
   rendered=[span for span,preview,prompt in events if not preview]
   self.assertEqual(rendered,[1.25]*4)
   self.assertIn((1.25,False,'+'),events);self.assertFalse(app.plan.armed);app.log.close()

if __name__=='__main__':unittest.main()
