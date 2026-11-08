import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tests'))
from reference_fixtures import maps
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import importlib.util
from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('walk',Path(__file__).with_name('n810-aprs-walk.py'))
w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)

class Tests(unittest.TestCase):
 def setUp(self):
  original=w.walk_map.Atlas
  p=patch.object(w.walk_map,'Atlas',side_effect=lambda directory:original(str(maps())))
  p.start();self.addCleanup(p.stop)
 def test_schedule_manual_and_no_catchup(self):
  p=w.Plan(3);p.arm(0,True)
  self.assertFalse(p.tick(59,True));self.assertTrue(p.tick(60,True))
  p.submitted(60,{'lat':47,'lon':-122},b'test')
  self.assertFalse(p.tick(89,True));self.assertFalse(p.tick(90,True));self.assertIsNone(p.pending)
  self.assertFalse(p.tick(119,True));self.assertTrue(p.tick(120,True))
  p.submitted(130,{},b'manual');self.assertEqual(p.due,190)
  self.assertTrue(p.tick(999,True));p.submitted(999,{},b'last')
  self.assertFalse(p.armed);self.assertFalse(p.tick(9999,True))
  with self.assertRaises(ValueError):p.arm(9999,True)
 def test_disconnect_never_auto_rearms(self):
  p=w.Plan();p.arm(0,True);self.assertFalse(p.tick(10,False));self.assertFalse(p.armed)
  self.assertFalse(p.tick(1000,True));p.arm(1000,True)
  self.assertFalse(p.tick(1059,True));self.assertTrue(p.tick(1060,True))
 def test_fresh_fix_requires_timestamp_accuracy_and_connection(self):
  state={'heartbeat':100,'connected':True,'fields':{'position':100},'position':{'time':100,'accuracy':10,'lat':47,'lon':-122}}
  self.assertIsNotNone(w.fresh_position(state,105))
  self.assertIsNone(w.fresh_position(state,140))
  state['connected']=False;self.assertIsNone(w.fresh_position(state,105));state['connected']=True
  for accuracy in (0,101,65535,float('nan')):
   state['position']['accuracy']=accuracy;self.assertIsNone(w.fresh_position(state,105))
 def test_beacon_roundtrip_and_local_echo_not_return(self):
  pos={'lat':5.5655,'lon':5.5855};payload=w.beacon_payload(pos,'123456',1)
  self.assertEqual(payload,b'!0533.93N/00535.13E[Walk 123456 001')
  self.assertEqual(w.coordinate(47.999999,True),'4800.00N')
  frame=w.beacon_frame('N0CALL',pos,'123456',1)
  addresses,decoded=w.unpack(frame);self.assertEqual(decoded,payload)
  self.assertFalse(any(used for call,used in addresses[2:]))
  self.assertTrue(addresses[0][1]);self.assertFalse(addresses[1][1])
  self.assertEqual(w.bridge.Frames().feed(w.bridge.encode(frame)),[frame])
  # Exercise actual receive classifier: local echo has no used hop.
  app=w.Walk.__new__(w.Walk);app.plan=w.Plan();app.call='N0CALL';app.position=pos;app.received=0
  import collections
  app.recent=collections.deque();app.notice='';app.log=type('Log',(),{'add':lambda *args,**kwargs:None})()
  app.plan.submitted(0,pos,payload);app.receive(frame);self.assertNotIn('return_path',app.plan.probes[0])
  repeated=bytearray(frame);repeated[1+2*7+6]|=128
  app.receive(bytes(repeated));self.assertIn('WIDE1-1*',app.plan.probes[0]['return_path'])
 def test_journal_full_session(self):
  with tempfile.TemporaryDirectory() as root:
   log=w.Journal(Path(root));log.add('rx',frame='00');log.close()
   rows=[json.loads(s) for s in log.path.read_text().splitlines()]
   self.assertEqual(rows[0]['frame'],'00');self.assertEqual(log.path.stat().st_mode&0o777,0o600)
 def test_no_gps_queries_without_lease_and_reply_parsing(self):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root);sent=[];owner=w.live.Telemetry(sent.append,root/'state',root/'control',root/'gps')
   owner.tick(0);self.assertEqual(sent,[])
   import time,struct
   w.live.atomic(root/'gps',{'until':time.time()+45})
   owner.refresh_controls({root/'gps'},now=1);owner.tick(1)
   self.assertEqual(sent,[w.live.request(20),w.live.request(76)])
   raw=int(47*30000).to_bytes(3,'big',signed=True)+int(-122*30000).to_bytes(3,'big',signed=True)+bytes(6)+int(time.time()).to_bytes(4,'big')+b'\0\12'
   body=b'\0'+raw;frame=b'\xff\1\0'+bytes([len(body)])+struct.pack('>HH',2,0x804c)+body
   owner.feed(frame[:10]);owner.feed(frame[10:]);self.assertEqual(owner.state['position']['lat'],47)
   owner.close()
 def test_render_small_and_large(self):
  class Win:
   def getmaxyx(self):return (24,80)
   def erase(self):pass
   def move(self,*args):pass
   def clrtoeol(self):pass
   def refresh(self):pass
   def addnstr(self,y,x,text,n,attr):
    assert all(c.isprintable() for c in text),repr(text)
    self.assertions(y,x,n)
   def assertions(self,y,x,n):assert 0<=y<24 and 0<=x<79 and n<=79-x
  with tempfile.TemporaryDirectory() as root:
   import argparse
   app=w.Walk(argparse.Namespace(callsign='N0CALL',budget=20,logs=root))
   app.recent.append('bad\0station\x1b[31m');app.notice='bad\0status'
   app.center=(5.5573,5.5565);app.position={'lat':5.5573,'lon':5.5565,'accuracy':10}
   app.track.append(app.position)
   with patch.object(w.curses,'newpad'):
    app.draw(Win());app.key(ord('m'));app.draw(Win())
    app.key(ord('t'));app.key(ord('r'));app.draw(Win())
   app.log.close()
 def test_position_wire_decoding(self):
  raw=int(5.5655*30000).to_bytes(3,'big',signed=True)+int(5.5855*30000).to_bytes(3,'big',signed=True)+bytes(6)+(1234567890).to_bytes(4,'big')+(12).to_bytes(2,'big')
  p=w.live.parse_position(raw);self.assertAlmostEqual(p['lon'],-122.5);self.assertEqual(p['accuracy'],12)
  self.assertIsNone(w.live.parse_position(bytes(18)))

if __name__=='__main__':unittest.main()
