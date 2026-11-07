import importlib.util,json,struct,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('live',Path(__file__).with_name('n810-radio-live.py'))
live=importlib.util.module_from_spec(spec);spec.loader.exec_module(live)

class Tests(unittest.TestCase):
    def test_read_only_requests(self):
        for cmd in (11,14,31,60):
            with self.assertRaises(ValueError):live.request(cmd)
    def test_pause_events_and_polling(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);sent=[];owner=live.Telemetry(sent.append,root/'state',root/'control')
            owner.tick(0);self.assertEqual(sent,[])
            live.enable(True,root/'control');owner.refresh_controls();owner.tick(1)
            self.assertEqual(len(sent),6)
            def reply(word,body):return b'\xff\1\0'+bytes([len(body)])+struct.pack('>HH',2,word)+body
            raw=bytes.fromhex('90017000')
            frame=reply(0x8014,b'\0'+raw)
            owner.feed(frame[:7]);owner.feed(frame[7:]);self.assertEqual(owner.state['status']['curr_region'],0)
            event=reply(9,b'\1'+raw);owner.feed(event);self.assertEqual(owner.state['events'],1)
            live.enable(False,root/'control');owner.refresh_controls();owner.tick(2);before=list(sent)
            owner.feed(event);owner.tick(99)
            self.assertEqual(sent,before);self.assertEqual(owner.state['events'],1)
            owner.close();self.assertFalse(live.read(root/'state')['connected'])
    def test_beacon_reply_has_no_extra_prefix(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);owner=live.Telemetry(lambda _:None,root/'state',root/'control');owner.state['enabled']=True
            body=b'\0'+bytes(50)
            owner.feed(b'\xff\1\0'+bytes([len(body)])+struct.pack('>HH',2,0x8021)+body)
            self.assertIn('should_share_location',owner.state['beacon'])

class OneShotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.sent=[]
        self.owner=live.Telemetry(self.sent.append,self.root/'state',self.root/'control',self.root/'gps')
    def start(self,ident='one',now=0):
        return self.owner.start_read(dict(version=1,operation='read_current',request_id=ident,requested_at=100,expires_at=125),now=now,wall=100)
    def reply(self,cmd,raw,status=0):
        body=bytes([status])+raw
        self.owner.feed(b'\xff\1\0'+bytes([len(body)])+struct.pack('>HH',2,0x8000|cmd)+body)
    def test_paused_reads_serial_and_atomic_published_progress(self):
        self.start();self.owner.tick(0)
        self.assertEqual(self.sent,[live.request(20)])
        for n,(cmd,raw) in enumerate(((20,bytes.fromhex('90017000')),(10,bytes(64)),(33,bytes(50)))):
            self.reply(cmd,raw)
            if n<2:self.owner.tick(n+1)
        progress=self.owner.read_progress('one')
        self.assertEqual((progress['state'],progress['completed']),('complete',3))
        self.assertEqual(live.read(self.root/'state')['read_request']['state'],'complete')
        self.assertFalse(self.owner.state['enabled']);self.assertEqual(len(self.sent),3)
        for name in ('status','settings','beacon'):self.assertIn(name,self.owner.state['fields'])
        self.start();self.owner.tick(20);self.assertEqual(len(self.sent),3)
    def test_cancel_drains_late_reply_without_freshening_fields(self):
        self.start();self.owner.tick(0);self.owner.cancel_read('one')
        with self.assertRaises(ValueError):self.start('two',1)
        self.reply(20,bytes.fromhex('90017000'))
        self.assertNotIn('status',self.owner.state['fields'])
        self.start('two',1);self.owner.tick(1);self.assertEqual(len(self.sent),2)
    def test_timeout_and_reply_error(self):
        self.start();self.owner.tick(0);self.owner.tick(5)
        self.assertEqual(self.owner.read_progress('one')['error'],'read_timeout')
        self.reply(20,bytes.fromhex('90017000'))
        self.start('two',6);self.owner.tick(6);self.reply(20,b'',status=1)
        self.assertEqual(self.owner.read_progress('two')['error'],'radio_reply_status_1')
    def test_periodic_reads_suspended_and_busy_rejected(self):
        self.start();live.enable(True,self.root/'control');self.owner.refresh_controls();self.owner.tick(0)
        commands=[int.from_bytes(v[6:8],'big') for v in self.sent]
        self.assertEqual(commands.count(20),1);self.assertNotIn(10,commands);self.assertNotIn(33,commands)
        with self.assertRaises(ValueError):self.start('two')
        self.owner.close();self.assertEqual(self.owner.read_progress('one')['error'],'radio_disconnected')
    def test_read_state_isolated_without_publish_or_clock_change(self):
        self.start();self.owner.tick(0);self.reply(20,bytes.fromhex('90017000'))
        before=(self.root/'state').read_bytes();heartbeat=self.owner.state['published_at']
        result=self.owner.read_state();result['fields']['status']=0
        result['status']['curr_region']=31;result['read_request']['results'].clear()
        self.assertEqual(self.owner.state['published_at'],heartbeat)
        self.assertNotEqual(self.owner.state['fields']['status'],0)
        self.assertEqual(self.owner.state['status']['curr_region'],0)
        self.assertTrue(self.owner.state['read_request']['results'])
        self.assertEqual((self.root/'state').read_bytes(),before)
        self.assertFalse(self.owner.read_state()['enabled'])
    def test_paused_periodic_pending_drains_without_refresh(self):
        self.owner.pending[20]=0
        with self.assertRaises(ValueError):self.start()
        self.reply(20,b'')
        self.assertIn(20,self.owner.pending)
        self.reply(20,bytes.fromhex('90017000'))
        self.assertNotIn(20,self.owner.pending);self.assertNotIn('status',self.owner.state['fields'])
        self.start();self.owner.tick(1)
        self.assertEqual(self.sent,[live.request(20)])
    def test_paused_error_reply_drains_existing_pending(self):
        self.owner.pending[10]=0;self.reply(10,b'',status=1)
        self.assertNotIn(10,self.owner.pending);self.assertNotIn('settings',self.owner.state['fields'])
    def test_expired_request_and_existing_pending_rejected(self):
        with self.assertRaises(ValueError):self.owner.start_read(dict(version=1,operation='read_current',request_id='old',requested_at=10,expires_at=20),now=0,wall=100)
        self.owner.pending[20]=0
        with self.assertRaises(ValueError):self.start()

if __name__=='__main__':unittest.main()
