"""Local captured-feed contracts; no private captures or radio hardware needed."""
import datetime,json,os,select,socket,subprocess,sys,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent

def address(call,last=False):return bytes(ord(c)<<1 for c in call.ljust(6))+bytes([0x60|last])
FRAME=(b'\0'+address('APRS')+address('TEST',True)+b'\x03\xf0>Recorded example').hex()
STAMP='2020-01-02T03:04:05.000+00:00'
class LocalFeed(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='n810-test-',dir='/tmp');self.root=Path(self.temp.name)/'env'
  live=Path(self.temp.name)/'live.json';cat=Path(self.temp.name)/'catalog.json'
  live.write_text(json.dumps({'data':{'captured':'2020-01-02T04:00:00+00:00','packets':[dict(time=STAMP,direction='radio_to_host',frame=FRAME)]}}))
  cat.write_text(json.dumps({'data':{'stations':[dict(call='TEST',first=STAMP,last=STAMP,packets=1)],'evidence':[],'via':[]}}))
  self.process=subprocess.Popen([sys.executable,str(HERE/'dev-env.py'),'serve','--root',str(self.root),'--live',str(live),'--catalog',str(cat)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  ready=select.select([self.process.stdout,self.process.stderr],[],[],8)[0]
  self.assertTrue(ready,'server startup timed out');line=self.process.stdout.readline() if self.process.stdout in ready else self.process.stderr.readline();self.assertTrue(line.startswith(b'{'),line.decode());self.meta=json.loads(line)
 def tearDown(self):
  self.process.terminate()
  try:self.process.communicate(timeout=4)
  except subprocess.TimeoutExpired:self.process.kill();self.process.communicate()
  self.temp.cleanup()
 def connect(self,name):
  s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.settimeout(2);s.connect(str(self.root/name));self.addCleanup(s.close);return s
 def test_multiple_readers_receive_original_times_and_replay_label(self):
  for _ in range(2):
   data=self.connect('aprs.sock').recv(65536)
   self.assertIn(b'03:04:05 TEST>APRS',data);self.assertIn(b'REPLAY',data);self.assertIn(b'TX disabled',data)
  self.assertEqual(self.meta['mode'],'REPLAY');self.assertFalse(self.meta['transmit']);self.assertFalse((self.root/'kiss.sock').exists())
 def test_raw_snapshot_preserves_frame_timestamp_and_closes(self):
  s=self.connect('replay.sock');data=b''
  while True:
   b=s.recv(65536)
   if not b:break
   data+=b
  lines=[json.loads(x) for x in data.splitlines()];self.assertTrue(lines[0]['replay']);self.assertEqual(lines[0]['records'],1);self.assertEqual(lines[1]['time'],STAMP);self.assertEqual(lines[1]['frame'],FRAME)
 def test_input_rejected_and_sandbox_database_matches_capture(self):
  import sqlite3
  s=self.connect('aprs.sock');s.recv(65536);s.sendall(b'TX fake\n');self.assertEqual(s.recv(4096),b'')
  db=sqlite3.connect(self.root/'home/.local/state/n810-aprs/directory.sqlite3');self.addCleanup(db.close);self.assertEqual(db.execute('select call,last,packets from stations').fetchone(),('TEST',STAMP,1))
 def test_second_owner_refused_without_interrupting_existing_readers(self):
  result=subprocess.run([sys.executable,str(HERE/'dev-env.py'),'serve','--root',str(self.root)],capture_output=True,timeout=5)
  self.assertNotEqual(result.returncode,0);self.assertIn(b'already owns',result.stderr);self.assertIn(b'REPLAY',self.connect('aprs.sock').recv(65536))
if __name__=='__main__':unittest.main()
