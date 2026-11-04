"""Real local native ↔ external native handoff with a PTY radio and no hardware."""
import json,os,pty,select,socket,subprocess,sys,tempfile,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'shell/vendor/apps/domains/reticulum'))
from session_owner import SessionOwner
from owner import serve
from wire import exchange
from external_node import save
from native_radio import Frames
from rnode_protocol import KISS
from native_owner import installed_library
SessionOwner.NODE_INTERVAL=.1

def main():
 with tempfile.TemporaryDirectory(prefix='p-auto-',dir='/tmp') as tmp:
  root=Path(tmp);state=root/'state';state.mkdir(mode=0o700);runtime=root/'runtime';runtime.mkdir(mode=0o700)
  master,slave=pty.openpty();stop=threading.Event();owners=[];errors=[];executor=None;changes=[]
  def radio():
   decoder=Frames(192,219)
   while not stop.is_set():
    if not select.select([master],[],[],.1)[0]:continue
    try:data=os.read(master,4096)
    except OSError:return
    for frame in decoder.feed(data):
     command,value=frame[0],frame[1:]
     if command==8:value=b'F'
     elif command==0x50:value=b'\x01\x52'
     elif command==0x48:value=b'\x80'
     elif command not in range(1,7):continue
     os.write(master,bytes([192,command])+KISS.escape(value)+bytes([192]))
  radio_thread=threading.Thread(target=radio,daemon=True);radio_thread.start()
  server=socket.socket();server.bind(('127.0.0.1',0));server.listen(4)
  def discard():
   while not stop.is_set():
    try:client,_=server.accept()
    except OSError:return
    def read(client=client):
     try:
      while client.recv(4096):pass
     except OSError:pass
     finally:client.close()
    threading.Thread(target=read,daemon=True).start()
  threading.Thread(target=discard,daemon=True).start()
  config=root/'node-config';config.mkdir();(config/'config').write_text('[interfaces]\n [[node]]\n type = TCPClientInterface\n target_host = 127.0.0.1\n target_port = '+str(server.getsockname()[1])+'\n')
  node_state=root/'node-state';node_state.mkdir(mode=0o700);node_socket=root/'node.sock'
  save(state/'external-node.msgpack',dict(mode='auto',endpoint='unix://'+str(node_socket)))
  def factory(s,n):
   owner=SessionOwner(s,n,'radio','usb',os.ttyname(slave),2,2);owners.append(owner)
   owner.store.commit({'test':dict(id='test',label='Test',frequency=912345000,bandwidth=500000,txpower=2,spreadingfactor=7,codingrate=5)},'test')
   return owner
  def run():
   try:serve(runtime/'owner.sock',state,'test',factory,stopped=stop)
   except BaseException as error:errors.append(repr(error))
  thread=threading.Thread(target=run,daemon=True);thread.start()
  def call(action='snapshot',payload=None):return exchange(runtime/'owner.sock',dict(version=1,action=action,request_id=os.urandom(8).hex(),payload=payload or {}))
  def wait(predicate,label,seconds=15):
   deadline=time.monotonic()+seconds;last={}
   while time.monotonic()<deadline:
    try:
     last=call()
     if predicate(last):return last
    except (OSError,ValueError):pass
    if errors:raise AssertionError(errors)
    time.sleep(.02)
   raise AssertionError(label+': '+str(last))
  def start_node():
   return subprocess.Popen([sys.executable,str(ROOT/'tests/fixtures/native_executor.py'),str(node_socket),str(node_state),str(installed_library()),str(config)],stderr=open(root/'executor.log','ab'))
  def phase(backend):
   value=wait(lambda s:s['radio_state']=='online' and s['external_node']['selected']==backend,backend)
   changes.append(backend);return value
  try:
   wait(lambda s:s.get('owner_online'),'manager')
   call('connect',dict(station='test',radio='radio'));initial=phase('local');identity=initial['public_card']['public_key']
   executor=start_node();wait(lambda s:node_socket.exists(),'node socket')
   value=phase('external');assert value['public_card']['public_key']==identity
   assert value['backend']=='external-microreticulum';assert owners[0].child.owner.stack.lib.external
   executor.terminate();executor.wait(10);executor=None
   value=phase('local');assert value['public_card']['public_key']==identity
   executor=start_node();wait(lambda s:node_socket.exists(),'node return')
   value=phase('external');assert value['public_card']['public_key']==identity
   call('disconnect',dict(station='test',radio='radio'));wait(lambda s:s['radio_state']=='idle','disconnect')
   call('configure_node',dict(mode='disabled'));call('connect',dict(station='test',radio='radio'));phase('local')
   call('disconnect',dict(station='test',radio='radio'));wait(lambda s:s['radio_state']=='idle','disconnect')
   executor.terminate();executor.wait(10);executor=None
   call('configure_node',dict(mode='external-only'));call('connect',dict(station='test',radio='radio'))
   wait(lambda s:s['radio_state']=='error','external-only failure');assert owners[0].child is None
   executor=start_node();value=phase('external');assert value['public_card']['public_key']==identity
   call('disconnect',dict(station='test',radio='radio'));wait(lambda s:s['radio_state']=='idle','disconnect')
   owners[0].store.commit(owners[0].store.profiles,None)
   call('configure_node',dict(mode='auto'));wait(lambda s:s['external_node'].get('offload_ready'),'ready node without local profile')
   call('connect',dict(station='test',radio='radio'));phase('external')
   executor.terminate();executor.wait(10);executor=None
   wait(lambda s:s['radio_state']=='error' and s['owner_online'],'missing fallback remains actionable')
   executor=start_node();value=phase('external');assert value['public_card']['public_key']==identity
   assert 'RNS' not in sys.modules and 'LXMF' not in sys.modules
   print(json.dumps(dict(passed=True,transitions=changes,identity_preserved=True,external_only_local_starts=0,python_rns_imported=False,manual_recovery_actions=[],external_only_recovered=True,missing_local_profile_recovered=True)))
  finally:
   stop.set()
   if owners:owners[0].post(dict(kind='shutdown'))
   thread.join(15)
   if executor:executor.terminate();executor.wait(10)
   server.close();radio_thread.join(1);os.close(master);os.close(slave)
   assert not thread.is_alive(),errors
if __name__=='__main__':main()
