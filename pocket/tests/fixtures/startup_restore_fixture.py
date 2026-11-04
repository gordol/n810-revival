"""Exercise real desktop startup with three deliberately slow saved owners."""
import importlib.util,json,selectors,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'shell'))
source=Path(sys.argv[1]);folder=Path(sys.argv[2])
empty=len(sys.argv)>3 and sys.argv[3]=='empty'
spec=importlib.util.spec_from_file_location('fixture_desktop',source)
desktop=importlib.util.module_from_spec(spec);spec.loader.exec_module(desktop)
import session,app_registry
NAMES=('Workbench','Reader','Library')
finished=set()
def record(kind,**values):
 with (folder/'events').open('a') as stream:stream.write(json.dumps(dict(kind=kind,at=time.monotonic(),**values))+'\n')
original_load=session.Store.load
HOST=None
PANELS=None
def load(self,host,panels):
 global HOST,PANELS
 HOST=host;PANELS=panels
 if not self.path.exists():
  data=session.capture(host,panels)
  data['preferences'].update(background_enabled=False,animate=False,show_clock=False,show_connectivity=False)
  data['windows']['Connections'].update(opened=False,visible=False)
  for index,name in enumerate(NAMES):
   data['windows'][name].update(opened=True,visible=True,x=3+index,y=3+index,w=40,h=12,desktop=index)
   data['app_views'][name]={'marker':name}
  data['desktop']=0;data['focus']='Workbench'
  if empty:
   for row in data['windows'].values():row.update(opened=False,visible=False)
   data['focus']=None
  self.path.write_text(json.dumps(data))
 original_load(self,host,panels)
 assert self.loaded,self.error
session.Store.load=load
class Owner:
 def __init__(self,name):
  self.name=name;self.state={};record('factory-start',name=name)
  time.sleep(.25);record('factory-end',name=name)
 def restore_session(self,state):
  self.state=state;finished.add(self.name);record('restored',name=self.name,state=state)
 def session_state(self):return self.state
 def bind_session(self,callback):pass
 def lines(self):return ('Restored '+self.name,)
 def poll_interval(self):return None
original_bind=app_registry.Registry.bind
def bind(self,host):
 original_bind(self,host)
 for name in NAMES:
  form=self.forms[name];form.entry=form.entry._replace(factory=lambda host,name=name,**kwargs:Owner(name))
app_registry.Registry.bind=bind
OriginalSelector=selectors.DefaultSelector
class Selector(OriginalSelector):
 def select(self,timeout=None):
  if empty or len(finished)==3:record('idle',timeout=timeout)
  return super().select(timeout)
selectors.DefaultSelector=Selector
class Output:
 def __init__(self,target):self.target=target;self.frame=False
 def __getattr__(self,key):return getattr(self.target,key)
 def write(self,value):
  if '\x1b[?2026l' in value:self.frame=True
  return self.target.write(value)
 def flush(self):
  self.target.flush()
  if self.frame:
   self.frame=False
   record('frame',state=session.capture(HOST,PANELS),modules=sorted(sys.modules))
sys.stdout=Output(sys.stdout)
sys.argv=[str(source),'--shell','--no-save','--no-local-services','--no-native','--session',str(folder/'session.json'),'--app-state',str(folder),'--control-socket',str(folder/'ui.sock')]
try:desktop.main()
finally:record('exit',state=session.capture(HOST,PANELS))
