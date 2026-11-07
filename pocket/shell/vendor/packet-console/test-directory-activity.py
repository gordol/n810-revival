"""Collector activity is quiet on duplicates and published only after commit."""
import importlib.util,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('directory',HERE/'n810-aprs-directory.py')
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)

def addr(call,last=False):return bytes(ord(c)<<1 for c in call.ljust(6))+bytes([0x60|last])
ROW=dict(time='2020-01-02T03:04:05+00:00',direction='radio_to_host',frame=(b'\0'+addr('APRS')+addr('TEST',True)+b'\x03\xf0>BBS 146.820MHz').hex())
class ActivityTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.db=d.database(Path(self.temp.name)/'db');self.addCleanup(self.db.close)
  self.monitor=d.load_monitor()
 def test_zero_and_duplicate_batches_are_silent(self):
  emit=Mock();self.assertEqual(d.collect_once(self.db,[],self.monitor,'N0DEM',emit),0);emit.assert_not_called()
  self.assertEqual(d.collect_once(self.db,[ROW],self.monitor,'N0DEM',emit),1)
  event=json.loads(emit.call_args.args[0]);self.assertEqual(event['call'],'TEST');self.assertEqual(event['captured_at'],ROW['time'])
  self.assertEqual(event['packet_type'],'aprs_ui');self.assertEqual(event['source']['kind'],'raw_snapshot')
  self.assertIn('service:BBS',[f['kind'] for f in event['facts']]);emit.reset_mock()
  self.assertEqual(d.collect_once(self.db,[ROW],self.monitor,'N0DEM',emit),0);emit.assert_not_called()
 def test_rollback_does_not_publish_activity(self):
  activity=[];bad=dict(ROW,frame='nothex')
  with self.assertRaises(ValueError):d.ingest(self.db,[ROW,bad],self.monitor,'N0DEM',activity)
  self.assertEqual(activity,[]);self.assertEqual(self.db.execute('SELECT count(*) FROM stations').fetchone()[0],0)
 def test_collection_errors_remain_visible(self):
  handlers={};args=type('Args',(),dict(db=str(Path(self.temp.name)/'other'),socket='unused',call='N0DEM'))()
  def signal_handler(sig,handler):handlers[sig]=handler
  def stop_sleep(_):handlers[d.signal.SIGTERM]()
  with patch.object(d.signal,'signal',side_effect=signal_handler),patch.object(d,'snapshot',side_effect=OSError('feed unavailable')),patch.object(d.time,'sleep',side_effect=stop_sleep),patch('builtins.print') as output:
   d.collect(args)
  self.assertTrue(any(call.args[:2]==('Waiting:','feed unavailable') for call in output.call_args_list))

if __name__=='__main__':unittest.main()
