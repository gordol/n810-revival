"""Wire ABI bounds and one-reader USB/RFCOMM multiplexing."""
import ctypes,os,pty,select,sys,threading,time,unittest,struct
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum'))
from native_rpc import Library,checked_info
from external_node import Connection,pack,unpack
from native_radio import Frames
from wire import encode,decode
INFO=dict(online=True,protocol=1,abi=2,identity='12'*16,features=['links','endpoints','resources','lxmf'],lease_seconds=3)
class RPCTests(unittest.TestCase):
 def test_allowlist_size_and_output_bounds(self):
  class Transport:
   def exchange(self,request):
    self.last=request
    if request.get('operation')=='key':return dict(result=65,outputs=[b'x'*65])
    return dict(result=0,outputs=[])
   def close(self):pass
  transport=Transport();lib=Library(transport,INFO)
  keys=b'a'*16+b'b'*16
  self.assertEqual(lib.invoke('handler',(1,b'/service',2,keys,2)),0)
  self.assertEqual(transport.last['arguments'][3],keys)
  with self.assertRaisesRegex(ValueError,'length'):lib.invoke('key',(1,0,ctypes.create_string_buffer(64),64))
 def test_incomplete_capabilities_and_unbounded_lease_rejected(self):
  for value in (dict(INFO,features=['links']),dict(INFO,abi=1),dict(INFO,lease_seconds=60),dict(INFO,identity='invalid')):
   with self.assertRaises(ValueError):checked_info(value)
 def test_unix_clock_is_sent_only_when_negotiated_and_only_on_open(self):
  class Transport:
   def __init__(self):self.requests=[]
   def exchange(self,request):
    self.requests.append(request)
    return dict(identity=INFO['identity']) if request['action']=='native_open' else dict(result=0,outputs=[])
   def subscribe(self,publish,stopped,session):publish(dict(session=session,ready=True));stopped.wait()
   def close(self):pass
  for clock in (None,'unix-ms-v1'):
   transport=Transport();lib=Library(transport,dict(INFO,clock=clock))
   try:
    with patch('native_rpc.time.time',return_value=1793210000.125):self.assertEqual(lib.invoke('init',(None,b'ignored')),0)
    self.assertEqual(transport.requests[0].get('unix_ms'),1793210000125 if clock else None)
    self.assertNotIn('unix_ms',transport.requests[1])
   finally:lib.close(released=True)
  for clock in ('uptime','unix-seconds',True):
   with self.assertRaisesRegex(ValueError,'clock'):checked_info(dict(INFO,clock=clock))
 def test_close_interrupts_pending_command_without_replay(self):
  master,slave=pty.openpty();errors=[]
  try:
   with Connection(os.ttyname(slave)) as connection:
    transport=connection.owner_transport()
    def request():
     try:transport.exchange(dict(version=1,action='native_call',operation='announce'))
     except ConnectionError as error:errors.append(str(error))
    worker=threading.Thread(target=request);worker.start()
    self.assertTrue(select.select([master],[],[],2)[0]);raw=os.read(master,4096)
    self.assertEqual(len(list(Frames(192,219).feed(raw))),1)
    transport.close();worker.join(1)
    self.assertFalse(worker.is_alive());self.assertEqual(len(errors),1)
    with self.assertRaises(ConnectionError):transport.exchange(dict(version=1,action='native_renew'))
    self.assertFalse(select.select([master],[],[],.05)[0])
  finally:os.close(master);os.close(slave)
 def test_unassociated_protocol_error_interrupts_request_without_replay(self):
  master,slave=pty.openpty();errors=[]
  try:
   with Connection(os.ttyname(slave)) as connection:
    transport=connection.owner_transport()
    def request():
     try:transport.exchange(dict(version=1,action='native_call',operation='announce'))
     except ConnectionError as error:errors.append(str(error))
    worker=threading.Thread(target=request);worker.start()
    self.assertTrue(select.select([master],[],[],2)[0]);os.read(master,4096)
    raw=encode(dict(version=1,channel=0,error='Invalid PS02 length',owner_online=True))
    os.write(master,b'\xc0\x88'+raw.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc')+b'\xc0')
    worker.join(1);self.assertFalse(worker.is_alive())
    self.assertEqual(errors,['External protocol error: Invalid PS02 length'])
    with self.assertRaisesRegex(ConnectionError,'External protocol error'):
     transport.exchange(dict(version=1,action='native_call',operation='announce'))
    self.assertFalse(select.select([master],[],[],.05)[0]);transport.close()
  finally:os.close(master);os.close(slave)
 def test_close_waits_for_inflight_lease_acknowledgement(self):
  class Transport:
   def close(self):pass
  lib=Library(Transport(),INFO);ack=threading.Event()
  def renew():
   ack.wait();lib.deadline=time.monotonic()+.05
  lib.renewer=threading.Thread(target=renew);lib.renewer.start()
  timer=threading.Timer(.02,ack.set);timer.start();start=time.monotonic()
  lib.close()
  self.assertGreaterEqual(time.monotonic()-start,.06)
  self.assertFalse(lib.renewer.is_alive())
 def test_provisioning_and_native_requests_share_one_serial_reader(self):
  master,slave=pty.openpty();address=os.ttyname(slave);stop=threading.Event();seen=[]
  def frame(command,raw):return b'\xc0'+bytes([command])+raw.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc')+b'\xc0'
  def server():
   decoder=Frames(192,219)
   while not stop.is_set():
    try:
     if not select.select([master],[],[],.1)[0]:continue
     data=os.read(master,4096)
    except OSError:return
    for message in decoder.feed(data):
     if message[0]==0x86:
      op,seq,payload=unpack(message[1:]);response=frame(0x87,pack([op,seq,{1:'microReticulum',2:2}]))
     else:
      value=decode(message[1:]);seen.append(value['channel'])
      response=frame(0x88,encode(dict(version=1,channel=value['channel'],value=value['payload'])))
     for index in range(0,len(response),3):os.write(master,response[index:index+3])
  worker=threading.Thread(target=server,daemon=True);worker.start()
  results=[];errors=[]
  try:
   with Connection(address) as connection:
    transport=connection.owner_transport()
    def request(n):
     try:results.append(transport.exchange(dict(version=1,action='echo',payload=bytes([n,192,219]))))
     except Exception as error:errors.append(str(error))
    clients=[threading.Thread(target=request,args=(n,)) for n in range(4)]
    for client in clients:client.start()
    self.assertEqual(connection.query(2,9,None)[1],'microReticulum')
    for client in clients:client.join(3)
    self.assertFalse(errors,errors);self.assertEqual(len(results),4)
    self.assertEqual(len(set(seen)),4)
    self.assertEqual({v['value'] for v in results},{bytes([n,192,219]) for n in range(4)})
  finally:
   stop.set();worker.join(1);os.close(master);os.close(slave)
class FragmentTests(unittest.TestCase):
 def test_interleaving_order_bounds_and_expiry(self):
  from node_transport import Fragments
  def frame(key,offset,total,data):return struct.pack('!IHH',key,offset,total)+data
  d=Fragments(256)
  self.assertIsNone(d.feed(frame(1,0,6,b'abc')))
  self.assertIsNone(d.feed(frame(2,0,4,b'12')))
  self.assertEqual(d.feed(frame(1,3,6,b'def')),b'abcdef')
  self.assertEqual(d.feed(frame(2,2,4,b'34')),b'1234')
  for raw in (b'short',frame(0,0,1,b'a'),frame(1,0,32769,b'a'),frame(1,0,1,b'ab'),frame(1,0,300,b'x'*257),frame(1,1,3,b'x')):
   with self.assertRaises(ValueError):Fragments(256).feed(raw)
  d=Fragments(256);d.feed(frame(1,0,4,b'ab'))
  for raw in (frame(1,0,4,b'ab'),frame(1,3,4,b'c'),frame(1,2,5,b'cd')):
   with self.assertRaises(ValueError):d.feed(raw)
  d=Fragments(256)
  for n in range(1,9):d.feed(frame(n,0,4,b'ab'))
  with self.assertRaises(ValueError):d.feed(frame(9,0,4,b'ab'))
  with patch('node_transport.time.monotonic',return_value=time.monotonic()+11):
   self.assertIsNone(d.feed(frame(9,0,4,b'ab')))
   self.assertEqual(len(d.pending),1)
 def test_fragmented_transfer_allows_control_and_provisioning_before_completion(self):
  from node_transport import Fragments
  master,slave=pty.openpty();stop=threading.Event();first=threading.Event();release=threading.Event();errors=[];results=[];events=[]
  payload=b'\xc0\xdb'*3000
  def framed(command,raw):return b'\xc0'+bytes([command])+raw.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc')+b'\xc0'
  def server():
   decoder=Frames(192,219);assembly=Fragments(256)
   while not stop.is_set():
    if not select.select([master],[],[],.1)[0]:continue
    try:data=os.read(master,4096)
    except OSError:return
    for message in decoder.feed(data):
     if message[0]==0x86:
      op,key,_=unpack(message[1:]);events.append('provision');os.write(master,framed(0x87,pack([op,key,{1:'status'}])));continue
     raw=assembly.feed(message[1:]) if message[0]==0x89 else message[1:]
     if raw is None:continue
     value=decode(raw);action=value['action'];events.append(action)
     response=encode(dict(version=1,channel=value['channel'],result=0,value=value.get('payload')))
     if len(response)>256:
      for offset in range(0,len(response),256):os.write(master,framed(0x89,struct.pack('!IHH',5001,offset,len(response))+response[offset:offset+256]))
     else:os.write(master,framed(0x88,response))
  thread=threading.Thread(target=server,daemon=True);thread.start()
  try:
   with Connection(os.ttyname(slave)) as connection:
    connection.fragment_size=256;transport=connection.owner_transport();original=connection.rpc.write_frame
    def paced(command,raw,priority,cancelled):
     original(command,raw,priority,cancelled)
     if command==0x89 and not first.is_set():first.set();release.wait(3)
    connection.rpc.write_frame=paced
    def bulk():
     try:results.append(transport.exchange(dict(version=1,action='echo',payload=payload)))
     except Exception as error:errors.append(str(error))
    worker=threading.Thread(target=bulk);worker.start();self.assertTrue(first.wait(2))
    try:
     self.assertEqual(transport.exchange(dict(version=1,action='native_renew'))['result'],0)
     self.assertEqual(connection.query(2,9,None)[1],'status')
     self.assertNotIn('echo',events)
    finally:release.set()
    worker.join(5);self.assertFalse(worker.is_alive());self.assertFalse(errors,errors)
    self.assertEqual(results[0]['value'],payload);self.assertEqual(events,['native_renew','provision','echo'])
  finally:release.set();stop.set();thread.join(1);os.close(master);os.close(slave)
 def test_busy_executor_remains_local_and_fragment_capability_is_validated(self):
  from external_node import probe,selection
  class Client:
   rpc=None;available=False;online=True;features=INFO['features']
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def query(self,operation,*args):
    if operation==2:return {1:'microReticulum',2:2,128:dict(INFO,available=self.available,online=self.online,features=self.features,framing='kiss-fragment-v1',fragment_size=1024)}
    return {1:{1:{1:True},107:{1:bytes.fromhex(INFO['identity'])},105:{}}}
  client=Client();state=probe('/dev/ttyFAKE',connection=lambda _:client)
  self.assertFalse(state['offload_ready']);self.assertEqual(selection('auto',state),'local');self.assertEqual(client.fragment_size,1024)
  client.available=True;client.online=False;client.features=[]
  state=probe('/dev/ttyFAKE',connection=lambda _:client)
  self.assertEqual(state['state'],'online');self.assertFalse(state['offload_ready']);self.assertEqual(state['identity'],INFO['identity'])
  self.assertTrue(state['reason'])
  for value in (dict(INFO,available=0),dict(INFO,framing='unknown'),dict(INFO,framing='kiss-fragment-v1',fragment_size=0),dict(INFO,framing='kiss-fragment-v1',fragment_size=32768)):
   with self.assertRaises(ValueError):checked_info(value)

if __name__=='__main__':unittest.main()
