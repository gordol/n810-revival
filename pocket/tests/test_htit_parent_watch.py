"""Parent lifetime pipe must neither hang nor abort helper shutdown."""
from pathlib import Path
import subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/meshcore'
SETUP='''
import sys,socket
sys.path.insert(0,PATH)
import hub_transport as hub
class FakeLink:
 def __init__(self,port):self.serial,self.writer=socket.socketpair()
 def hello(self):return bytes([1,0,15])
 def request(self,*args,**kwargs):raise OSError('controlled helper error')
 def close(self):self.serial.close();self.writer.close()
hub.Link=FakeLink
'''.replace('PATH',repr(str(ROOT)))
class Tests(unittest.TestCase):
 def child(self,body):
  p=subprocess.Popen([sys.executable,'-c',SETUP+body],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  self.addCleanup(lambda:p.kill() if p.poll() is None else None)
  self.addCleanup(lambda:[s.close() for s in (p.stdin,p.stdout,p.stderr) if not s.closed])
  return p
 def test_main_error_exits_while_parent_pipe_is_still_open(self):
  p=self.child("""
sys.argv=['hub','--port','fake','bridge','--ble','AA:BB:CC:DD:EE:FF','--parent-watch']
try:hub.main()
except OSError:sys.exit(7)
""")
  self.assertEqual(p.wait(timeout=5),7,p.stderr.read())
 def test_parent_eof_interrupts_idle_helper_cleanly(self):
  p=self.child("""
sys.argv=['hub','--port','fake','bridge','--peer','1','--parent-watch']
try:hub.main()
except KeyboardInterrupt:pass
""")
  self.assertTrue(p.stdout.readline().startswith('PEER_PORT='))
  p.stdin.close()
  self.assertEqual(p.wait(timeout=5),0,p.stderr.read())
if __name__=='__main__':unittest.main()
