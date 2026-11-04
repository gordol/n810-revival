"""Two native owner lifetimes through the shared service loop in one process."""
import os,sys,tempfile,threading,select,time,ctypes
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shell/vendor/apps/domains/reticulum'))
from native_session import NativeSession
from wire import exchange
import socket
with tempfile.TemporaryDirectory(prefix='p-native-session-',dir='/tmp') as directory:
 root=Path(directory);(root/'runtime').mkdir(mode=0o700);(root/'state').mkdir(mode=0o700);(root/'config').mkdir()
 server=socket.socket();server.bind(('127.0.0.1',0));server.listen(2);stop=threading.Event()
 def peer():
  while not stop.is_set():
   try:c,_=server.accept()
   except OSError:return
   def read(c=c):
    try:
     while c.recv(8192):pass
    except OSError:pass
    finally:c.close()
   threading.Thread(target=read,daemon=True).start()
 threading.Thread(target=peer,daemon=True).start()
 (root/'config/config').write_text('[interfaces]\n [[test]]\n type = TCPClientInterface\n target_host = 127.0.0.1\n target_port = '+str(server.getsockname()[1])+'\n')
 for index in range(3):
  r,w=os.pipe()
  session=NativeSession(root/'runtime/owner.sock',root/'state','test',root/'config','test','loopback',w);os.close(w)
  stamp_thread=None;stamp_errors=[]
  try:
   assert select.select([r],[],[],5)[0]
   assert os.read(r,1)==b'R',session.error;os.close(r)
   result=exchange(root/'runtime/owner.sock',dict(version=1,action='connect',request_id='test',payload=dict(station='test',radio='test')))
   assert result['job']['state'] in ('running','complete'),result
   state=exchange(root/'runtime/owner.sock',dict(version=1,action='snapshot'))
   assert state['backend']=='native-microreticulum' and state['radios'][0]['interface_online'],state
   assert 'RNS' not in sys.modules and 'LXMF' not in sys.modules, 'Native owner imported the Python stacks'
   if index in (1,2):
    owner=session.owner;rns=owner.RNS
    destination=rns.Destination(owner.identity,rns.Destination.OUT,rns.Destination.SINGLE,'lxmf','delivery')
    def stamp():
     try:owner.stack.call('lxmf_send',destination.handle,b'test',4,99999,255,ctypes.create_string_buffer(32768))
     except ValueError as error:stamp_errors.append(str(error))
    if index==1:
     stamp_thread=threading.Thread(target=stamp,daemon=True);stamp_thread.start();time.sleep(.03)
    else:
     assert owner.stack.call('lxmf_send',destination.handle,b'test',4,99999,0,ctypes.create_string_buffer(32768))>32

  finally:
   session.terminate();assert session.wait(12)==0,session.error
   if stamp_thread:
    stamp_thread.join(3);assert not stamp_thread.is_alive(), 'Stamp worker ignored cancellation'
    assert stamp_errors and any('cancel' in e or 'closing' in e for e in stamp_errors),stamp_errors
  assert not (root/'runtime/owner.sock').exists()
 stop.set()
 try:server.shutdown(socket.SHUT_RDWR)
 except OSError:pass
 server.close()
 print('PASS: native connect/close/reconnect, cancellable stamp work, no Python RNS/LXMF imports')
