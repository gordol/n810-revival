"""Saved owners must not form a mandatory batch before the usable shell."""
import fcntl,json,os,pty,select,socket,struct,subprocess,sys,tempfile,termios,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'shell'))
from runtime_codec import frame as control_frame,unpack,HEADER

def completed_records(path):
 try:raw=path.read_bytes()
 except FileNotFoundError:return []
 # The child may be midway through one write. A newline commits a record;
 # malformed complete records still fail rather than hiding broken fixtures.
 return [json.loads(line) for line in raw.split(b'\n')[:-1] if line]

class StartupRestoreTests(unittest.TestCase):
 def test_live_reader_waits_for_complete_record(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as d:
   path=Path(d)/'events';path.write_bytes(b'{"kind":"frame"}\n{"kind":"id')
   self.assertEqual(completed_records(path),[{'kind':'frame'}])
   with path.open('ab') as stream:stream.write(b'le"}\n')
   self.assertEqual(completed_records(path),[{'kind':'frame'},{'kind':'idle'}])
   path.write_bytes(b'broken\n')
   with self.assertRaises(json.JSONDecodeError):completed_records(path)
 def test_pending_owner_keeps_saved_state_and_explicit_open_bypasses_queue(self):
  from types import SimpleNamespace
  sys.path.insert(0,str(ROOT/'shell'))
  from app_registry import LazyApplication
  made=[]
  class Owner:
   def restore_session(self,state):self.state=state
   def session_state(self):return self.state
   def bind_session(self,callback):pass
  def factory(host,**options):made.append(Owner());return made[-1]
  window=SimpleNamespace(opened=True,rolled=False)
  host=SimpleNamespace(desktop=2,focus='Other',windows=[window],window_cleanup={},window=lambda name:window,shown=lambda window:True)
  entry=SimpleNamespace(preferred_size=(40,12),title='Saved',factory=factory)
  form=LazyApplication(SimpleNamespace(options=lambda entry:{}),entry,host)
  form.restore_session({'selection':17});form.restore_pending=True
  form.set_active(True)
  self.assertEqual(made,[])
  self.assertEqual(form.session_state(),{'selection':17})
  self.assertIn('Restoring',form.lines()[0])
  form.open(activate=False)
  self.assertEqual(len(made),1)
  self.assertFalse(form.restore_pending)
  self.assertEqual(form.session_state(),{'selection':17})
  self.assertEqual((host.desktop,host.focus),(2,'Other'))

 def test_saved_layout_first_frame_input_and_eventual_restoration(self):
  self.check_saved_layout()

 def test_saved_empty_desktop_does_not_reopen_connections(self):
  self.check_saved_layout(empty=True)

 def check_saved_layout(self,empty=False):
  with tempfile.TemporaryDirectory(prefix='pocket-restore-',dir='/tmp') as temporary:
   folder=Path(temporary);master,slave=pty.openpty()
   fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',30,100,0,0))
   began=time.monotonic()
   child=subprocess.Popen([sys.executable,str(ROOT/'tests/fixtures/startup_restore_fixture.py'),str(ROOT/'shell/desktop.py'),str(folder)]+(['empty'] if empty else []),stdin=slave,stdout=slave,stderr=slave,env={**os.environ,'TERM':'xterm-256color'})
   os.close(slave);raw=bytearray()
   def records():
    return completed_records(folder/'events')
   def pump():
    if select.select([master],[],[],.01)[0]:
     try:raw.extend(os.read(master,65536))
     except OSError:pass
    if child.poll() is not None:raise AssertionError(bytes(raw[-4000:]).decode(errors='replace'))
    if time.monotonic()-began>15:raise AssertionError('startup timed out')
   try:
    while b'\x1b[?2026l' not in raw:pump()
    requested=time.monotonic()
    with socket.socket(socket.AF_UNIX) as client:
     client.connect(str(folder/'ui.sock'));client.sendall(control_frame({'activate':'System'}));client.setblocking(False)
     while not select.select([client],[],[],0)[0]:pump()
     self.assertTrue(unpack(client.recv(8192)[HEADER:])['ok'])
    response=time.monotonic()-requested
    while not any(r['kind']=='idle' for r in records()):pump()
    os.write(master,b'\x1dq')
    while child.poll() is None:
     if select.select([master],[],[],.01)[0]:
      try:raw.extend(os.read(master,65536))
      except OSError:pass
     self.assertLess(time.monotonic()-began,15)
    self.assertEqual(child.returncode,0,bytes(raw[-3000:]))
    rows=records();frame=next(r for r in rows if r['kind']=='frame');starts=[r for r in rows if r['kind']=='factory-start']
    for module in ('moon','geometry','textwrap'):
     self.assertNotIn(module,frame['modules'])
    # Python 3.14's argparse color formatter uses dataclasses itself.
    # The Nokia's 3.11 runtime must not load that machinery for saved settings.
    if '_colorize' not in frame['modules']:
     for module in ('dataclasses','inspect'):self.assertNotIn(module,frame['modules'])
    self.assertFalse(frame['state']['windows']['Connections']['opened'])
    self.assertEqual(frame['state']['focus'],None if empty else 'Workbench')
    if empty:self.assertEqual(starts,[])
    else:self.assertLess(frame['at'],starts[0]['at'])
    # A ready request waits at most one non-preemptible constructor, not all three.
    self.assertLess(response,.65)
    self.assertTrue(any(r['kind']=='idle' and r['timeout'] is None for r in rows),rows)
    for index,name in enumerate(('Workbench','Reader','Library')):
     saved=frame['state'];final=rows[-1]['state']
     self.assertEqual(saved['app_views'][name],{'marker':name})
     self.assertEqual(final['app_views'][name],{'marker':name})
     self.assertEqual(saved['windows'][name],final['windows'][name])
     self.assertEqual(saved['windows'][name]['desktop'],index)
    print('saved startup: first frame %.3fs, first input %.3fs, owners %.3fs' % (frame['at']-began,response,rows[-2]['at']-began))
   finally:
    if child.poll() is None:child.terminate();child.wait(timeout=5)
    os.close(master)
if __name__=='__main__':unittest.main()
