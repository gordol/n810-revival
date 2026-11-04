"""Real RNS client acceptance with a local simulated LoRa service, no RF."""
import sys,os,time,select,threading
from pathlib import Path
from collections import deque
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shell/vendor/apps/domains/meshcore'))
from rnode_adapter import Adapter
from hub_transport import Endpoint,Frame
import tempfile,RNS
runtime=tempfile.TemporaryDirectory()
Path(runtime.name,'config').write_text('[reticulum]\nshare_instance = No\n[interfaces]\n')
rns=RNS.Reticulum(configdir=runtime.name)
from RNS.Interfaces.RNodeInterface import RNodeInterface
class Link:
 def __init__(self):self.n=0;self.inbox=deque();self.sent=[]
 def send(self,s,o,data=b''):
  self.n+=1;self.sent.append((s,o,data));self.inbox.append(Frame(s,o|128,self.n,b'\0'))
  if o==4:self.inbox.append(Frame(3,0x90,0,b'\x9c\xff\x04'+data))
  return self.n
link=Link();ep=Endpoint('TEST_PORT');a=Adapter(link,ep);stop=threading.Event();errors=[]
def run():
 try:
  while not stop.is_set():
   r,_,_=select.select([ep.master],[],[],.02)
   if r:
    for cmd,data in a.decoder.feed(os.read(ep.master,4096)):a.command(cmd,data)
   while link.inbox:a.frame(link.inbox.popleft())
   a.tick();ep.flush()
 except BaseException as e:errors.append(e)
t=threading.Thread(target=run);t.start();received=[];iface=None
try:
 iface=RNodeInterface(SimpleNamespace(inbound=lambda data,interface:received.append(data)),dict(name='HTIT adapter test',port=os.ttyname(ep.slave),frequency=912345000,bandwidth=500000,txpower=2,spreadingfactor=7,codingrate=5,flow_control=True))
 assert iface.online, (errors,link.sent)
 for n in (1,254,255,500):
  payload=bytes(i%256 for i in range(n));iface.process_outgoing(payload)
  until=time.monotonic()+4
  while payload not in received and time.monotonic()<until:time.sleep(.05)
  assert payload in received,(n,errors,link.sent)
 print('PASS: real RNS RNodeInterface configure + 1/254/255/500 byte PTY roundtrips',flush=True)
finally:
 if iface:iface.detach()
 stop.set();t.join(2);ep.close()
