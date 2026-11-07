"""Reviewed command owner: synthetic callbacks/socketpairs only, never radio."""
import copy
import datetime
import importlib.util
import json
from pathlib import Path
import socket
import unittest
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('message_owner_test',ROOT/'n810-messages-owner.py');o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)
spec=importlib.util.spec_from_file_location('owner_monitor_test',ROOT/'n810-packet-monitor.py');monitor=importlib.util.module_from_spec(spec);spec.loader.exec_module(monitor)
class Tests(unittest.TestCase):
 def setUp(self):
  self.now=[1000.];self.saved=[];self.sent=[]
  self.state=o.model.State('N0DEM',clock=lambda:'00:16:40')
  def persist(rows):self.saved.append(o.model.outbox_document(rows))
  def submit(row):self.sent.append(self.state.begin_submission(row,row['path']));self.state.submitted(row)
  self.owner=o.Owner(self.state,'home','radio1',persist,submit,True,lambda:True,lambda:self.now[0])
 def command(self,action,request_id,**values):return self.owner.handle(dict(action=action,request_id=request_id,**values))
 def draft(self):
  result=self.command('draft.save','draft1',source='N0DEM',to='W7DK',text='hello',path=[],protocol='aprs')
  self.assertTrue(result['ok'],result);return result['row']
 def review(self,row):
  result=self.command('review','review1',draft_id=row['draft_id'],expected_revision=row['revision'])
  self.assertTrue(result['ok'],result);return result
 def send(self,review):
  return dict(action='send',request_id='send1',review_token=review['review_token'],confirm=True,issued_at=self.now[0],station_id='home',radio_id='radio1',source='N0DEM')
 def test_compose_review_have_no_transport_effect_then_one_send(self):
  row=self.draft();review=self.review(row)
  self.assertEqual(self.sent,[]);self.assertEqual(review['row']['id'],row['id'])
  self.assertEqual(review['payload'],':W7DK     :hello{'+row['id'])
  result=self.owner.handle(self.send(review))
  self.assertTrue(result['ok']);self.assertTrue(result['accepted']);self.assertEqual(len(self.sent),1)
  self.assertEqual(result['row']['status'],'Submitted');self.assertNotIn('serial_written_at',result['row'])
  self.assertEqual(self.saved[-2]['outbox'][0]['status'],'Submitting')
  self.assertIn('command_id',self.saved[-2]['outbox'][0])
 def test_same_request_repeats_and_restart_do_not_requeue(self):
  request=self.send(self.review(self.draft()));first=self.owner.handle(request)
  self.assertEqual(self.owner.handle(request),first);self.assertEqual(len(self.sent),1)
  restored=o.model.State('N0DEM',outbox=self.saved[-1]['outbox'])
  restarted=o.Owner(restored,'home','radio1',lambda _:None,lambda _:self.fail('Never resend after restart'),True,lambda:True,lambda:1001)
  response=restarted.handle(request)
  self.assertTrue(response['ok']);self.assertTrue(response['duplicate'])
  self.assertEqual(response['row']['status'],'Unconfirmed')
 def test_request_id_reuse_with_changed_intent_is_conflict(self):
  request=self.send(self.review(self.draft()));self.owner.handle(request)
  result=self.owner.handle(dict(request,source='OTHER'))
  self.assertFalse(result['ok']);self.assertEqual(len(self.sent),1)
 def test_disabled_capability_no_submit(self):
  self.owner.allow_send=False;request=self.send(self.review(self.draft()))
  self.assertFalse(self.owner.handle(request)['ok']);self.assertEqual(self.sent,[])
  self.assertFalse(self.owner.snapshot()['capability']['send_enabled'])
 def test_expired_or_unconfirmed_intent_no_send(self):
  review=self.review(self.draft());request=self.send(review)
  self.assertFalse(self.owner.handle(dict(request,confirm=False))['ok'])
  self.now[0]=1061
  self.assertFalse(self.owner.handle(dict(request,issued_at=1061))['ok']);self.assertEqual(self.sent,[])
 def test_stale_revision_invalidates_review(self):
  row=self.draft();review=self.review(row)
  changed=self.command('draft.save','edit1',draft_id=row['draft_id'],expected_revision=1,source='N0DEM',to='W7DK',text='new text',path=[])
  self.assertTrue(changed['ok']);self.assertEqual(changed['row']['revision'],2)
  self.assertFalse(self.owner.handle(self.send(review))['ok']);self.assertEqual(self.sent,[])
 def test_identity_mismatch_and_bss_rejected(self):
  self.assertFalse(self.command('draft.save','bss1',protocol='bss',source='N0DEM',to='W7DK',text='test',path=[])['ok'])
  request=self.send(self.review(self.draft()))
  self.assertFalse(self.owner.handle(dict(request,radio_id='other'))['ok'])
  self.assertEqual(self.sent,[])
 def test_failed_intent_persistence_blocks_side_effect_and_consumes_review(self):
  request=self.send(self.review(self.draft()))
  self.owner.persist=lambda _:(_ for _ in ()).throw(OSError('disk full'))
  self.assertFalse(self.owner.handle(request)['ok']);self.assertEqual(self.sent,[])
  self.owner.persist=lambda _:None
  duplicate=self.owner.handle(request)
  self.assertTrue(duplicate['duplicate']);self.assertEqual(duplicate['row']['status'],'Unconfirmed')
  self.assertEqual(self.sent,[])
 def test_transport_ambiguity_never_retries(self):
  request=self.send(self.review(self.draft()));attempt=[]
  def submit(row):attempt.append(1);raise OSError('connection lost')
  self.owner.submit=submit
  result=self.owner.handle(request);self.assertEqual(result['row']['status'],'Unconfirmed')
  self.owner.handle(request);self.assertEqual(len(attempt),1)
 def record(self,frame,direction,epoch):
  return dict(frame=frame.hex(),direction=direction,time=datetime.datetime.fromtimestamp(epoch,datetime.timezone.utc).isoformat())
 def unescape(self,wire):return wire[1:-1].replace(b'\xdb\xdc',b'\xc0').replace(b'\xdb\xdd',b'\xdb')
 def test_actual_serial_write_then_exact_peer_ack_are_separate(self):
  result=self.owner.handle(self.send(self.review(self.draft())));row=self.state.outbox[0]
  self.assertNotIn('serial_written_at',row)
  tx=self.record(self.unescape(self.sent[0]),'host_to_radio_written',1001)
  self.owner.observe([tx],monitor.describe)
  self.assertEqual(row['status'],'Submitted');self.assertEqual(row['serial_written_at'],tx['time'])
  ack=o.model.kiss_frame('W7DK',[],'N0DEM','',row['id'],'ACK')
  rx=self.record(self.unescape(ack),'radio_to_host',1002)
  self.owner.observe([rx],monitor.describe)
  self.assertEqual(row['status'],'Acknowledged');self.assertEqual(row['ack_capture'],rx)
 def test_old_wrong_peer_and_bss_do_not_acknowledge(self):
  self.owner.handle(self.send(self.review(self.draft())));row=self.state.outbox[0]
  old=o.model.kiss_frame('W7DK',[],'N0DEM','',row['id'],'ACK')
  other=o.model.kiss_frame('OTHER',[],'N0DEM','',row['id'],'ACK')
  records=[self.record(self.unescape(old),'radio_to_host',999),self.record(self.unescape(other),'radio_to_host',1001),self.record(bytes.fromhex('000106204e3044454d0121052450494e47'),'radio_to_host',1001)]
  self.owner.observe(records,monitor.describe);self.assertEqual(row['status'],'Submitted')
 def test_in_memory_content_change_cannot_bypass_review(self):
  review=self.review(self.draft());self.state.outbox[0]['text']='changed behind review'
  self.assertFalse(self.owner.handle(self.send(review))['ok']);self.assertEqual(self.sent,[])
 def test_jsonl_service_adapter_snapshot_only(self):
  client,server=socket.socketpair()
  try:
   client.sendall(b'{"action":"snapshot","request_id":"snap1"}\n')
   o.serve_client(server,self.owner)
   result=json.loads(client.recv(65536));self.assertTrue(result['ok'])
   self.assertEqual(result['capability']['source'],'N0DEM');self.assertEqual(self.sent,[])
  finally:client.close();server.close()
if __name__=='__main__':unittest.main()
