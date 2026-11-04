"""Private test-only normal demo.main PTY fixture, deliberately slow form poll."""
import importlib.util,json,os,selectors,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]/'shell';sys.path.insert(0,str(ROOT));DEMO=Path(sys.argv[1]);FOLDER=Path(sys.argv[2]);JOBS=len(sys.argv)>3 and sys.argv[3]=='jobs';sys.argv=[str(DEMO),'--minimal','--no-native','--no-animation','--no-save','--session',str(FOLDER/'session.json')]
def record(kind,**data):
 with (FOLDER/'events.jsonl').open('a') as out:out.write(json.dumps(dict(kind=kind,ns=time.monotonic_ns(),**data))+'\n')
spec=importlib.util.spec_from_file_location('fixture_demo',DEMO);demo=importlib.util.module_from_spec(spec);spec.loader.exec_module(demo)
HOST=None;PENDING=None;READY=False
class FixtureHost(demo.Host):
 def __init__(self,*args,**kwargs):
  global HOST
  super().__init__(*args,**kwargs);HOST=self
 def flush(self,*args,**kwargs):
  global PENDING
  self.move_mode=self.resize_mode='outline';self.background_enabled=False
  output,changed,computed=super().flush(*args,**kwargs)
  if output and self.drag and self.latest is None and self.ui_painted:PENDING=dict(rect=list(self.drag[2]),native=self._native is not None)
  return output,changed,computed
 def finish(self,commit):
  had=bool(self.drag);super().finish(commit)
  if had:record('finish',commit=commit,rect=list(self.window('Slow').rect))
demo.Host=FixtureHost
class Output:
 def __init__(self,target):self.target=target;self.bytes=0
 def __getattr__(self,name):return getattr(self.target,name)
 def write(self,value):self.bytes+=len(value.encode());return self.target.write(value)
 def flush(self):
  global PENDING,READY
  self.target.flush()
  if PENDING is not None and self.bytes:
   record('outline-written',bytes=self.bytes,**PENDING);PENDING=None
  if not READY and HOST is not None and not HOST.damage and 'Slow' in HOST.app_forms:
   READY=True;record('ready',rect=list(HOST.window('Slow').rect),origin=list(HOST.origin))
  self.bytes=0
sys.stdout=Output(sys.stdout)
class Slow:
 def poll(self):
  if (FOLDER/'slow').exists():record('slow-start',drag=bool(HOST.drag),rect=list(HOST.window('Slow').rect));time.sleep(.18);record('slow-end',drag=bool(HOST.drag))
 def lines(self):return ('Private slow model fixture',)
 def poll_interval(self):return None
import app_registry
class Job:
 def poll_interval(self):return .05
 def poll(self):
  if HOST.drag and (FOLDER/'slow').exists():record('job-poll',drag=True)
original_bind=app_registry.Registry.bind
def bind(self,host):
 original_bind(self,host);host.add_window(demo.Window('Slow',10,4,50,15,visible=True,opened=True));host.app_forms['Slow']=Slow();host.activate('Slow')
 if JOBS:host.add_window(demo.Window('Job',1,1,20,8,visible=False,opened=True));host.app_forms['Job']=Job()
app_registry.Registry.bind=bind
OriginalSelector=selectors.DefaultSelector
class Selector(OriginalSelector):
 def select(self,timeout=None):
  if HOST is not None and HOST.drag and (FOLDER/'slow').exists():record('select',timeout=timeout)
  return super().select(timeout)
selectors.DefaultSelector=Selector
demo.main()
