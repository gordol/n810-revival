"""Message protocol/state/transport checks. Local socket pairs; no Bluetooth or RF."""
import importlib.util,pathlib,tempfile,socket,unittest
from types import SimpleNamespace
from unittest.mock import patch
p=pathlib.Path(__file__).parent/'n810-aprs-messages.py';s=importlib.util.spec_from_file_location('messages',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class Tests(unittest.TestCase):
 def test_owner_transport_can_observe_raw_source_without_decoded_connect(self):
  state=m.model.State('N0DEM');tx=m.Transport(state,None,'unused',[])
  with patch.object(m.socket,'socket') as connect:
   self.assertFalse(tx.tick());connect.assert_not_called()
 def test_legacy_and_command_owner_store_lock_exclude_other_writers(self):
  with tempfile.TemporaryDirectory() as folder:
   store=folder+'/messages.json'
   with m.acquire_store(store):
    with self.assertRaises(OSError):m.acquire_store(store)
   with m.acquire_store(store):pass
 def test_bss_rendering_and_aprs_actions_are_receive_only(self):
  record=dict(frame='000106204e3044454d0121052450494e47',time='2026-10-17T19:45:40.092Z',direction='radio_to_host')
  class Win:
   def __init__(self):self.text=[];self.keys=iter(map(ord,'earq'))
   def getmaxyx(self):return 40,100
   def erase(self):pass
   def move(self,*args):pass
   def refresh(self):pass
   def timeout(self,*args):pass
   def keypad(self,*args):pass
   def getch(self):return next(self.keys)
   def addnstr(self,y,x,text,*args):self.text.append(text)
  owners=[]
  class PassiveTransport:
   def __init__(self,state,*args):owners.append(state);state.add_record(record)
   def tick(self):return False
   def close(self):pass
  with tempfile.TemporaryDirectory() as folder,patch.object(m,'Transport',PassiveTransport),patch.object(m,'save'),patch.object(m.style,'init_screen'),patch.object(m.curses,'curs_set'),patch.object(m,'composer_request',return_value=None):
   win=Win();m.run(win,SimpleNamespace(call='N0DEM',store=folder+'/messages.json',socket='unused',kiss='unused',path=[]))
   self.assertTrue(any('[BSS]' in text for text in win.text))
   self.assertIn('BSS / receive only',win.text)
   self.assertFalse(any('COMPOSE /' in text for text in win.text))
   self.assertEqual(owners[0].notice,'BSS receive only; APRS reply/ACK does not apply')
   self.assertEqual(owners[0].received[0]['to'],'')
 def test_bss_submission_does_not_acquire_transmit_socket(self):
  state=m.model.State('N0DEM')
  row=state.add_record(dict(frame='000106204e3044454d0121052450494e47',time=None,direction='radio_to_host'))
  tx=m.Transport(state,'unused','unused',[])
  with patch.object(m.socket,'socket') as connect:
   with self.assertRaises(ValueError):tx.submit(row)
   connect.assert_not_called()
 def test_tui_consumes_shared_model_without_parallel_business_logic(self):
  self.assertTrue(issubclass(m.State,m.model.State))
  self.assertIs(m.parse_message,m.model.parse_message)
  self.assertIs(m.payload_for,m.model.payload_for)
  with tempfile.TemporaryDirectory() as folder:
   state=m.State('N0DEM',folder+'/messages.json');row=state.draft('W7DK','hello')
   self.assertIs(state.rows(2)[0],row)
   m.save(state.outbox,state.store)
   self.assertEqual(m.json.loads(pathlib.Path(state.store).read_text()),m.model.outbox_document(state.outbox))
 def test_runtime_composer_request_uses_private_override(self):
  with tempfile.TemporaryDirectory() as folder, patch.dict(m.os.environ,{'N810_RUNTIME_DIR':folder}):
   target=m.runtime.write_json('n810-message-request.json',{'to':'W7DK-1','created':1000})
   self.assertEqual(m.composer_request(now=1001),'W7DK-1')
   self.assertFalse(target.exists())
 def test_bad_runtime_composer_request_is_graceful(self):
  with patch.dict(m.os.environ,{'N810_RUNTIME_DIR':'relative/not-valid'}):
   self.assertIsNone(m.composer_request(now=1001))
 def test_directory_request_is_draft_navigation_only(self):
  with tempfile.TemporaryDirectory() as folder:
   path=pathlib.Path(folder)/'request.json'
   path.write_text(m.json.dumps({'to':'W7DK-1','created':1000,'send':True,'text':'ignored'}))
   self.assertEqual(m.composer_request(path,1001),'W7DK-1')
   self.assertFalse(path.exists())
   for request in ({'to':'W7DK','created':1},{'to':'W7DK-16','created':1000},{'to':'W7DK','created':1002}):
    path.write_text(m.json.dumps(request));self.assertIsNone(m.composer_request(path,1001))
   path.write_text('[]');self.assertIsNone(m.composer_request(path,1001))
 def test_compose_screen_without_id(self):
  class Win:
   def getmaxyx(self):return 40,133
   def erase(self):pass
   def move(self,*args):pass
   def addnstr(self,*args):pass
  m.curses.curs_set=lambda n:None
  with tempfile.TemporaryDirectory() as d:
   state=m.State('N0DEM',d+'/messages.json')
   compose=dict(to='CQSRVR',text='?APRST',kind='MSG',id=None,field=1,phase='edit')
   m.draw(Win(),state,0,0,compose,['WIDE1-1','WIDE2-1'])
   compose['phase']='review';m.draw(Win(),state,0,0,compose,['WIDE1-1','WIDE2-1'])
 def test_message_formats(self):
  row=m.parse_message('23:00:00 GATE>APRS ctl=03 pid=f0 }W7DK>APRS,TCPIP*::N0DEM    :hello{A12}B2\\x0d')
  self.assertEqual((row['source'],row['to'],row['text'],row['id'],row['reply_ack']),('W7DK','N0DEM','hello','A12','B2'))
  self.assertEqual(m.parse_message('23:00:00 W7DK>APRS ctl=03 pid=f0 :N0DEM    :ackA12')['kind'],'ACK')
  self.assertIsNone(m.parse_message('23:00:00 W7DK>APRS ctl=03 pid=f0 >status'))
 def test_validation(self):
  self.assertEqual(m.payload_for('W7DK','hello','A12'),b':W7DK     :hello{A12')
  for text in ('','x'*68,'bad|text','bad~text','bad{text','café'):
   with self.assertRaises(ValueError):m.payload_for('W7DK',text,'A12')
  with self.assertRaises(ValueError):m.callsign('W7DK-16')
  self.assertEqual(m.callsign('w7dk-15'),'W7DK-15')
 def test_ax25_frame(self):
  frame=m.kiss_frame('N0DEM',['WIDE1-1','WIDE2-1'],'W7DK','hello','A12')
  self.assertEqual(frame[:2],b'\xc0\x00');self.assertEqual(frame[-1:],b'\xc0')
  raw=frame[2:-1].replace(b'\xdb\xdc',b'\xc0').replace(b'\xdb\xdd',b'\xdb')
  self.assertEqual(bytes(c>>1 for c in raw[:6]),b'APN810')
  self.assertTrue(raw[6]&0x80);self.assertTrue(raw[27]&1)
  self.assertEqual(raw[28:30],b'\x03\xf0');self.assertTrue(raw.endswith(b':W7DK     :hello{A12'))
 def test_ack_exact_peer_and_address(self):
  with tempfile.TemporaryDirectory() as d:
   state=m.State('N0DEM',d+'/messages.json');row=state.draft('W7DK','hello',identifier='A12');row['status']='Submitted'
   state.add('23:00:00 OTHER>APRS ctl=03 pid=f0 :N0DEM    :ackA12');self.assertEqual(row['status'],'Submitted')
   state.add('23:00:01 W7DK>APRS ctl=03 pid=f0 :N0DEM-1  :ackA12');self.assertEqual(row['status'],'Submitted')
   state.add('23:00:02 W7DK>APRS ctl=03 pid=f0 :N0DEM    :ackA12');self.assertEqual(row['status'],'Acknowledged')
 def test_replay_and_store(self):
  with tempfile.TemporaryDirectory() as d:
   file=d+'/messages.json';state=m.State('N0DEM',file)
   line='23:00:00 W7DK>APRS ctl=03 pid=f0 :N0DEM    :hello{A12'
   state.add(line);state.add(line);self.assertEqual(len(state.received),1)
   state.draft('W7DK','reply');m.save(state.outbox,file)
   restored=m.State('N0DEM',file);self.assertEqual(restored.outbox[0]['status'],'Draft')
   state.outbox[0]['status']='Submitted';m.save(state.outbox,file)
   self.assertEqual(m.State('N0DEM',file).outbox[0]['status'],'Unconfirmed')
 def test_transport_only_explicit_submit(self):
  with tempfile.TemporaryDirectory() as d:
   state=m.State('N0DEM',d+'/messages.json');tx=m.Transport(state,d+'/absent-feed',d+'/absent-radio',[])
   tx.tick();self.assertIsNone(tx.tx);self.assertFalse(tx.queue)
   a,b=socket.socketpair();a.setblocking(False);b.setblocking(False);tx.tx=a
   row=state.draft('W7DK','hello',identifier='A12');self.assertFalse(tx.queue)
   tx.submit(row);tx.tick();self.assertEqual(row['status'],'Submitted')
   sent=b.recv(4096)
   self.assertEqual(sent,m.kiss_frame('N0DEM',[],'W7DK','hello','A12'))
   self.assertEqual(row['wire_hex'],sent.hex())
   self.assertEqual(row['payload'],':W7DK     :hello{A12')
   self.assertEqual(row['source'],'N0DEM')
   tx.tick()
   with self.assertRaises(BlockingIOError):b.recv(4096) # No automatic retransmission
   b.close();tx.tick();self.assertIsNone(tx.tx);tx.close()

if __name__=='__main__':unittest.main()
