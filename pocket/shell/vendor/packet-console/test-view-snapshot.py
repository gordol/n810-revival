"""Inspector explicit read-only snapshot selection using local synthetic sockets."""
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('snapshot_view',ROOT/'n810-aprs-view.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
spec=importlib.util.spec_from_file_location('snapshot_model',ROOT/'n810-messages-model.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
spec=importlib.util.spec_from_file_location('snapshot_monitor',ROOT/'n810-packet-monitor.py');monitor=importlib.util.module_from_spec(spec);spec.loader.exec_module(monitor)
FRAME=m.kiss_frame('N0CALL',[],'W7DK','hello','A12')[1:-1].replace(b'\xdb\xdc',b'\xc0').replace(b'\xdb\xdd',b'\xdb')
RECORD=dict(time='2026-10-17T12:00:00+00:00',frame=FRAME.hex(),direction='radio_to_host')
PACKET=dict(raw='12:00:00 '+monitor.describe(FRAME))
class Tests(unittest.TestCase):
 def setUp(self):v._raw_cache.clear()
 def exchange(self,path,call):
  # Real socketpair exercises JSONL reads; proxy verifies endpoint routing without
  # a filesystem socket bind, which the local sandbox does not allow.
  client,server=socket.socketpair()
  server.sendall((json.dumps(dict(type='snapshot',version=1,records=1))+'\n'+json.dumps(RECORD)+'\n').encode());server.close()
  connects=[]
  class SnapshotClient:
   def __enter__(self):return self
   def __exit__(self,*args):client.close()
   def connect(self,target):connects.append(target)
   def settimeout(self,value):client.settimeout(value)
   def makefile(self,*args):return client.makefile(*args)
  with patch.object(v.socket,'socket',return_value=SnapshotClient()):result=call()
  self.assertEqual(connects,[str(path)]);return result
 def test_explicit_local_replay_name_returns_original_rx(self):
  with tempfile.TemporaryDirectory() as directory:
   endpoint=Path(directory)/'replay.sock'
   row=self.exchange(endpoint,lambda:v.raw_record(PACKET,str(Path(directory)/'aprs.sock'),str(endpoint)))
   self.assertEqual(row,RECORD);self.assertIn(str(endpoint),v._raw_cache)
 def test_default_linux_sibling_is_preserved(self):
  with tempfile.TemporaryDirectory() as directory:
   endpoint=Path(directory)/'n810-aprs-replay.sock'
   row=self.exchange(endpoint,lambda:v.raw_record(PACKET,str(Path(directory)/'aprs.sock')))
   self.assertEqual(row,RECORD)
 def test_explicit_unavailable_does_not_substitute_local_saved_capture(self):
  with patch('builtins.open',side_effect=AssertionError('No unrelated disk fallback')):
   self.assertIsNone(v.raw_record(PACKET,'/missing/aprs.sock','/missing/explicit-replay.sock'))
 def test_cache_is_scoped_to_snapshot_endpoint(self):
  with tempfile.TemporaryDirectory() as directory:
   endpoint=Path(directory)/'replay.sock';decoded=str(Path(directory)/'aprs.sock')
   self.exchange(endpoint,lambda:v.raw_record(PACKET,decoded,str(endpoint)))
   self.assertIsNone(v.raw_record(PACKET,decoded,str(Path(directory)/'other.sock')))
if __name__=='__main__':unittest.main()
