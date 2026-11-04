"""Execute actual combined demo ingress/application statements on real readiness."""
import ast,selectors,signal,socket,subprocess,sys,tempfile,time,unittest
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Inbox
from app_readiness import AppReadiness,AppReady
from child_exit_wakeup import ChildExitWake
from map_library_open import MapOpen
from map_library_registration import RetiredJobs
ROOT=Path(__file__).resolve().parents[1]/'shell'
TREE=ast.parse((ROOT/'desktop.py').read_text())
def code(node):return compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'actual-demo.py','exec')
INGRESS=code(next(n for n in ast.walk(TREE) if isinstance(n,ast.For) and ast.unparse(n.target)=='(key, _)' and ast.unparse(n.iter)=='events'))
APPLICATIONS=code(next(n for n in ast.walk(TREE) if isinstance(n,ast.For) and ast.unparse(n.target)=='(index, application)' and ast.unparse(n.iter)=='enumerate(applications)' and 'serviced_owners.add(owner)' in ast.unparse(n)))
class Tests(unittest.TestCase):
 def setUp(self):
  self.inbox=Inbox();self.addCleanup(self.inbox.close)
  self.selector=selectors.DefaultSelector();self.addCleanup(self.selector.close)
  self.selector.register(self.inbox.readable,selectors.EVENT_READ)
 def env(self,events,map_open=None):
  return dict(events=events,bluetooth_control=None,keyboard=None,control=None,touch=None,terminals={},AppReady=AppReady,
              inbox=self.inbox,notified_owners=set(),map_open=map_open,sys=sys,Weather=object,Link=object)
 def test_actual_map_open_raw_wake_and_keyed_form_coalesce_without_losing_changed_map(self):
  for keyed_first in (True,False):
   with self.subTest(keyed_first=keyed_first):
    service=MapOpen(ROOT,ROOT,lambda:self.inbox.writable.send(b'l'),lambda ref:self.fail('Unexpected selection'))
    self.addCleanup(service.close)
    service._future=Future();service._future.add_done_callback(service._completed)
    if keyed_first:self.inbox.notify('form:CW')
    service._future.set_result((0,None,'controlled admission error'))
    if not keyed_first:self.inbox.notify('form:CW')
    events=self.selector.select(.1);self.assertTrue(events)
    env=self.env(events,service);exec(INGRESS,env)
    self.assertEqual(service.notice,'Cannot open map: controlled admission error')
    self.assertIsNone(service._future)
    self.assertEqual(env['notified_owners'],{'form:CW','all'})
    self.assertEqual(self.selector.select(0),[])
 def test_actual_retired_child_sigchld_and_keyed_form_service_application_owner(self):
  previous=signal.getsignal(signal.SIGCHLD);seen=[]
  signal.signal(signal.SIGCHLD,lambda signum,frame:seen.append(signum))
  self.addCleanup(signal.signal,signal.SIGCHLD,previous)
  wake=ChildExitWake(self.inbox);self.addCleanup(wake.close)
  child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.03)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  self.addCleanup(child.wait)
  class Model:
   def __init__(self):self.worker=SimpleNamespace(process=child);self.closed=False
   def poll(self):
    if self.worker.process.poll() is not None:self.worker=None
   def close(self):self.closed=True
  model=Model();jobs=RetiredJobs();jobs.models.append(model);self.addCleanup(jobs.close)
  self.inbox.notify('form:CW')
  end=time.monotonic()+2
  while not seen and time.monotonic()<end:time.sleep(.002)
  self.assertTrue(seen)  # Real SIGCHLD has fired; no waitpid outside owner.
  env=self.env(self.selector.select(.1));exec(INGRESS,env)
  self.assertEqual(env['notified_owners'],{'form:CW','all'})
  env.update(applications=[jobs],metrics=None,full_models='all' in env['notified_owners'],due_owners=env['notified_owners'],serviced_owners=set(),host=SimpleNamespace(app_forms={}))
  exec(APPLICATIONS,env)
  self.assertTrue(model.closed);self.assertEqual(jobs.models,[])
  self.assertEqual(child.returncode,0);self.assertEqual(env['serviced_owners'],{'application:0'})
  self.assertEqual(self.selector.select(0),[])
 def test_actual_appready_callback_publishes_model_readiness(self):
  read,write=socket.socketpair();self.addCleanup(read.close);self.addCleanup(write.close)
  attachment=AppReadiness(self.selector);self.addCleanup(attachment.close)
  class Form:
   def __init__(self):self.seen=[]
   def ready(self):self.seen.append(read.recv(1))
   def readiness_sources(self):return ((read,self.ready),)
  form=Form();attachment.sync((form,));write.send(b'x')
  env=self.env(self.selector.select(.1));exec(INGRESS,env)
  self.assertEqual(form.seen,[b'x']);self.assertEqual(env['notified_owners'],{'all'})
  self.assertEqual(self.selector.select(0),[])
 def test_no_second_child_handler_and_no_idle_completion_poll_fallback(self):
  calls=[ast.unparse(n.func) for n in ast.walk(TREE) if isinstance(n,ast.Call)]
  self.assertEqual(calls.count('ChildExitWake'),1)
  text=(ROOT/'desktop.py').read_text()
  self.assertNotIn('needs_completion_poll',text)
  self.assertNotIn("timeout=.05 if timeout is None else min(timeout,.05);owner_delay('form:'+name,.05)",text)
  self.assertIn('keyboard_router.safety_interval()',text)
  self.assertIn('app_readiness.sync(',text)

if __name__=='__main__':unittest.main()
