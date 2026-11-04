"""The acquisition thread must keep reading even while Python cannot run."""
import os,sys,select,struct,time,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from native_cells import load
from native_runtime import select as select_native
from touch_evdev import EventReader,EventCodec,EV_SYN,SYN_REPORT,SYN_DROPPED,EV_KEY,BTN_TOUCH,EV_ABS,ABS_X,CANCEL

class NativeInputTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  path=os.environ.get('POCKET_TEST_NATIVE') or select_native(build=False)['library']
  if not path:raise unittest.SkipTest('native build unavailable')
  cls.lib=load(path)
  if not hasattr(cls.lib,'input_start'):raise unittest.SkipTest('native input unavailable')
 def setUp(self):
  self.r,self.w=os.pipe();os.set_blocking(self.r,False);self.p=self.lib.input_start(self.r,16)
 def tearDown(self):
  self.lib.input_close(self.p);os.close(self.r);os.close(self.w)
 def ready(self):
  self.assertTrue(select.select([self.lib.input_fileno(self.p)],[],[],3)[0])
 def test_gil_stall_preserves_events_and_native_abi(self):
  # A separate writer sends more than an ordinary pipe can retain. The Python
  # consumer holds the GIL during the interval; only the C pump can drain it.
  import subprocess
  raw=b''.join(struct.pack('=iiHHi',1,i,3,0,i) for i in range(2048))
  with tempfile.TemporaryFile() as source:
   source.write(raw);source.seek(0)
   process=subprocess.Popen([sys.executable,'-c','import os,sys; d=sys.stdin.buffer.read();\nwhile d:\n n=os.write(int(sys.argv[1]),d[:4096]);d=d[n:]',str(self.w)],stdin=source,pass_fds=(self.w,))
   previous=sys.getswitchinterval();sys.setswitchinterval(2)
   try:
    deadline=time.monotonic()+.5
    while time.monotonic()<deadline:pass
   finally:sys.setswitchinterval(previous)
   process.wait(timeout=3)
  result=b''
  while len(result)<len(raw):
   self.ready();chunk,losses,reads=self.lib.input_read(self.p);self.assertEqual(losses,0);result+=chunk
  self.assertEqual(result,raw)
 def test_overflow_is_explicit_and_buffer_bounded(self):
  block=EventCodec(4).pack(EV_SYN,SYN_REPORT,0)*256
  for _ in range(24):os.write(self.w,block);time.sleep(.005)
  self.ready();raw,losses,reads=self.lib.input_read(self.p)
  self.assertGreater(losses,0);self.assertLessEqual(len(raw),4096);self.assertGreaterEqual(reads,17)
 def test_disconnect_is_reported_after_buffered_data(self):
  raw=EventCodec(4).pack(EV_SYN,SYN_REPORT,0);os.write(self.w,raw);os.close(self.w);self.w=os.open(os.devnull,os.O_WRONLY)
  self.ready();self.assertEqual(self.lib.input_read(self.p)[0],raw)
  self.ready()
  with self.assertRaises(OSError):self.lib.input_read(self.p)
 def test_close_is_idempotent_and_wakes_idle_thread(self):
  self.lib.input_close(self.p);self.lib.input_close(self.p)
  with self.assertRaises(ValueError):self.lib.input_read(self.p)
 def test_cancel_discards_old_contacts_before_rearming(self):
  self.lib.input_close(self.p)
  reader=EventReader(fd=self.r,query=lambda fd:({'name':'fixture'},(10,20,False)),codec=EventCodec(4),native=self.lib)
  c=reader.codec
  try:
   os.write(self.w,c.pack(EV_KEY,BTN_TOUCH,1)+c.pack(EV_SYN,SYN_REPORT,0)+c.pack(EV_KEY,BTN_TOUCH,0)+c.pack(EV_SYN,SYN_REPORT,0))
   self.assertTrue(select.select([reader],[],[],3)[0])
   reader.suppress_until_release();self.assertEqual(reader.drain(),[])
   os.write(self.w,c.pack(EV_KEY,BTN_TOUCH,1)+c.pack(EV_SYN,SYN_REPORT,0))
   self.assertTrue(select.select([reader],[],[],3)[0]);self.assertTrue(reader.drain()[0][2])
  finally:reader.close()
 def test_reader_resync_cancels_and_requires_fresh_contact(self):
  self.lib.input_close(self.p)
  device={'name':'fixture'};state=[10,20,False]
  reader=EventReader(fd=self.r,query=lambda fd:(device,tuple(state)),codec=EventCodec(4),native=self.lib)
  c=reader.codec
  try:
   os.write(self.w,c.pack(EV_KEY,BTN_TOUCH,1)+c.pack(EV_SYN,SYN_REPORT,0))
   self.assertTrue(select.select([reader],[],[],3)[0]);self.assertTrue(reader.drain()[0][2])
   os.write(self.w,c.pack(EV_SYN,SYN_DROPPED,0)+c.pack(EV_SYN,SYN_REPORT,0)+c.pack(EV_KEY,BTN_TOUCH,1)+c.pack(EV_SYN,SYN_REPORT,0))
   self.assertTrue(select.select([reader],[],[],3)[0]);self.assertEqual(reader.drain(),[CANCEL])
   os.write(self.w,c.pack(EV_KEY,BTN_TOUCH,0)+c.pack(EV_SYN,SYN_REPORT,0)+c.pack(EV_KEY,BTN_TOUCH,1)+c.pack(EV_SYN,SYN_REPORT,0))
   self.assertTrue(select.select([reader],[],[],3)[0]);rows=reader.drain();self.assertEqual(len(rows),1);self.assertTrue(rows[0][2])
  finally:reader.close()
if __name__=='__main__':unittest.main()
